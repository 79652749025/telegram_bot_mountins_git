import os
from logging import getLogger
from urllib.parse import unquote
import logging
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.postgres_VR2 import Database
from dotenv import load_dotenv
from aiogram.enums import ParseMode
from urllib.parse import unquote
import qrcode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from handlers import news_handlers # Убедитесь, что этот импорт корректен
from urllib.parse import unquote, quote_plus 


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# Определение состояний для FSM (Finite State Machine)
class SearchStates(StatesGroup):
    waiting_for_post_keyword = State()
    waiting_for_news_keyword = State() # Новое состояние для поиска новостей

class TelegramBot:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.db = None
        self.setup_database()

    @staticmethod
    def generate_qr(post_data: dict):
        """Генерирует QR-код для поста с прямой ссылкой на бота"""
        # post_data['qr_id'] должен быть уникальным ID поста из вашей базы данных

        # Параметр 'start' должен быть URL-кодирован.
        # Например, если qr_data = "mountain:p0001", то закодированная версия будет "mountain%3Ap0001"
        qr_content_data = f"mountain:{post_data['qr_id']}"
        encoded_qr_data = quote_plus(qr_content_data) # Используйте quote_plus для кодирования пробелов как '+'

        # Формируем полную ссылку на бота с параметром 'start'
        # Замените 'YourBotUsername' на реальное имя пользователя вашего бота без '@'
        bot_username = os.getenv('BOT_USERNAME') # Убедитесь, что у вас есть BOT_USERNAME в .env
        if not bot_username:
            logger.error("BOT_USERNAME не найден в .env. QR-ссылки будут недействительны.")
            # Вернуть что-то, что позволит избежать ошибки, или подставить заглушку
            bot_username = "your_bot_username_placeholder" 

        full_qr_link = f"https://t.me/{bot_username}?start={encoded_qr_data}"

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(full_qr_link) # Теперь QR-код содержит полную ссылку
        qr.make()
        img = qr.make_image(fill_color="black", back_color="white")
        filename = f"qr_{post_data['qr_id']}.png"
        img.save(filename)
        logger.info(f"QR-код для '{post_data['qr_id']}' сгенерирован: {full_qr_link}")
        return filename, full_qr_link
        
    async def setup_database(self):
        """Настройка подключения к базе данных"""
        db_config = {
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DB_NAME', 'vershinyrossii2'),
            'host': os.getenv('DB_HOST', '127.0.0.1'),
            'port': int(os.getenv('DB_PORT', 5433)),
        }
    
        try:
            self.db = Database(**db_config)
            await self.db.connect()
            await self.check_connection()
            await self.init_tables()
            logger.info("База данных готова")
        except Exception as e:
            logger.error(f"Ошибка настройки БД: {e}")
            raise
        
    async def check_connection(self):
        try:
            async with self.db.pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                logger.info(f"Подключено к: {version}")
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
        
    async def init_tables(self):
        """Создание таблиц в базе данных"""
        try:
            async with self.db.pool.acquire() as conn:
                # Таблица постов
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS posts (
                        id SERIAL PRIMARY KEY,
                        qr_id VARCHAR(50) UNIQUE NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        description TEXT NOT NULL,
                        image_url VARCHAR(255) NOT NULL,
                        content_url VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица новостей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS news (
                        id SERIAL PRIMARY KEY,
                        link TEXT NOT NULL,
                        news_type TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        title TEXT -- Добавил поле title для новостей
                    )
                ''')

                # Таблица для отслеживания взаимодействий пользователей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_interactions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        last_name VARCHAR(255),
                        qr_id VARCHAR(50),
                        post_id INTEGER REFERENCES posts(id),
                        interaction_type VARCHAR(50) NOT NULL, -- 'qr_scan', 'post_view', 'search'
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            logger.info("Таблицы успешно созданы")
        except Exception as e:
            logger.error(f"Ошибка создания таблиц: {e}")
            raise
        
    async def add_sample_post(self):
        """Добавление тестового поста"""
        async with self.db.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO posts (qr_id, title, description, image_url)
                VALUES ($1, $2, $3, $4)
            ''', 
            "p0001", 
            "Гора Эльбрус", 
            "Высочайшая вершина России и Европы (5642 м)", 
            "https://example.com/elbrus.jpg")
            logger.info("Тестовый пост добавлен в базу данных")

    async def handle_qr_url(self, message: types.Message, qr_data: str):
        """Обработка данных из QR-кода"""
        try:
            logger.info(f"Обработка QR данных: {qr_data}")
            
            if qr_data.startswith('mountain:'):
                qr_id = qr_data.split(':', 1)[1]  # Используем maxsplit=1 для корректного разделения
                post = await self.get_post_by_qr_id(qr_id)
            
                if post:
                    # Записываем взаимодействие пользователя
                    await self.log_user_interaction(
                        message.from_user, 
                        'qr_scan', 
                        qr_id=qr_id, 
                        post_id=post['id']
                    )
                    
                    # Приветственное сообщение с информацией из QR-кода
                    welcome_msg = (
                        f"🏔️ <b>Добро пожаловать!</b>\n\n"
                        f"Вы отсканировали QR-код и попали в наш бот!\n"
                        f"📍 Сейчас откроется информация о: <b>{post['title']}</b>\n\n"
                        f"Присоединяйтесь к нашему сообществу любителей гор России! 👇"
                    )
                    
                    # Кнопки для перехода в группу и канал
                    welcome_markup = types.InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                types.InlineKeyboardButton(
                                    text="💬 Общий чат", 
                                    url="https://t.me/topofrussia"
                                ),
                                types.InlineKeyboardButton(
                                    text="📢 Наш канал", 
                                    url="https://t.me/TopRussiaBrand"
                                )
                            ]
                        ]
                    )
                    
                    await message.answer(welcome_msg, reply_markup=welcome_markup, parse_mode=ParseMode.HTML)
                    
                    # Небольшая задержка для лучшего UX
                    await asyncio.sleep(1)
                    
                    # Показываем пост
                    await self.show_post(message, post)
                else:
                    await message.answer(
                        "🚫 К сожалению, информация по этому QR-коду не найдена.\n"
                        "Возможно, код устарел или поврежден.",
                        reply_markup=types.InlineKeyboardMarkup(
                            inline_keyboard=[
                                [types.InlineKeyboardButton(
                                    text="🏠 Главное меню", 
                                    callback_data="main_menu"
                                )]
                            ]
                        )
                    )
            else:
                await message.answer(
                    "🔍 Этот QR-код не предназначен для нашего бота.\n"
                    "Попробуйте отсканировать QR-код с информацией о горах России.",
                    reply_markup=types.InlineKeyboardMarkup(
                        inline_keyboard=[
                            [types.InlineKeyboardButton(
                                text="🏠 Главное меню", 
                                callback_data="main_menu"
                            )]
                        ]
                    )
                )
            
        except Exception as e:
            logger.error(f"QR Error: {e}")
            await message.answer(
                "⚠️ Произошла ошибка при обработке QR-кода.\n"
                "Попробуйте еще раз или обратитесь в поддержку.",
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(
                            text="🏠 Главное меню", 
                            callback_data="main_menu"
                        )]
                    ]
                )
            )

    async def log_user_interaction(self, user, interaction_type, qr_id=None, post_id=None):
        """Логирование взаимодействий пользователя"""
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO user_interactions 
                    (user_id, username, first_name, last_name, qr_id, post_id, interaction_type)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''', 
                user.id, 
                user.username, 
                user.first_name, 
                user.last_name, 
                qr_id, 
                post_id, 
                interaction_type)
        except Exception as e:
            logger.error(f"Ошибка логирования взаимодействия: {e}")
            
    async def get_post_by_qr_id(self, qr_id: str):
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM posts WHERE qr_id = $1 AND is_active = TRUE", 
                qr_id
            )

    async def get_all_news(self, limit=20):
        try:
            async with self.db.pool.acquire() as conn:
                return await conn.fetch("SELECT * FROM news ORDER BY id LIMIT $1;", limit)
        except Exception as e:
            logger.error(f"Ошибка при получении новостей: {e}")
            return []

    async def start_command(self, message: Message):
        """Обработчик команды /start с поддержкой QR-параметров"""
        args = message.text.split()
        
        # Если есть параметр start (от QR-кода)
        if len(args) > 1:
            # Декодируем URL из параметра start
            qr_url = unquote(args[1])
            await self.handle_qr_url(message, qr_url)
        else:
            # Обычное приветствие без QR-кода
            msg = (
                "🏔️ Добро пожаловать в бот \"Вершины России\"!\n\n"
                "Этот бот поможет вам узнать больше о горах России через QR-коды "
                "и получить актуальные новости о восхождениях и экспедициях.\n\n"
                "🔍 <b>Как использовать:</b>\n"
                "• Отсканируйте QR-код рядом с информацией о горе\n"
                "• Используйте команды для поиска новостей\n"
                "• Присоединяйтесь к нашему сообществу\n\n"
                "📱 <b>Доступные команды:</b>\n"
                "/start - Показать это сообщение\n"
                "/news - Показать список новостей\n"
                "/help - Подробная справка\n"
                "/qr [id] - Сгенерировать QR-код для поста (только для админов)"
            )
            
            markup = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text="💬 Общий чат", 
                            url="https://t.me/topofrussia"
                        ),
                        types.InlineKeyboardButton(
                            text="📢 Наш канал", 
                            url="https://t.me/TopRussiaBrand"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="🔍 Поиск информации", 
                            callback_data="search_posts"
                        )
                    ]
                ]
            )
            
            await message.answer(msg, reply_markup=markup, parse_mode=ParseMode.HTML)

    async def get_post_by_id(self, item_id: str):
        """Получаем пост из базы данных по ID"""
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM posts WHERE qr_id = $1", 
                item_id
            )

    async def show_post(self, message: types.Message, post):
        """Показываем пост с кнопками действий"""
        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="💬 Обсудить в чате", 
                    url="https://t.me/topofrussia"
                ),
                types.InlineKeyboardButton(
                    text="📢 Больше новостей", 
                    url="https://t.me/TopRussiaBrand"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="➡️ Следующий пост", 
                    callback_data=f"next_{post['id']}"
                ),
                types.InlineKeyboardButton(
                    text="🔍 Найти похожее", 
                    callback_data="search_posts"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🌟 Официальный сайт", 
                    url="https://вершина-россии.рф"
                )
            ]
        ])
        
        try:
            # Пытаемся отправить как фото
            await message.answer_photo(
                photo=post['image_url'],
                caption=f"<b>{post['title']}</b>\n\n{post['description']}",
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            # Если не удается отправить фото, отправляем текст
            logger.error(f"Ошибка отправки фото: {e}")
            await message.answer(
                f"<b>{post['title']}</b>\n\n{post['description']}\n\n🖼️ Изображение: {post['image_url']}",
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )

    async def generate_qr_command(self, message: Message):
        """Команда для генерации QR-кода (только для админов)"""
        # Проверяем, является ли пользователь админом
        admin_id = os.getenv('ADMIN_ID')
        if not admin_id or str(message.from_user.id) != admin_id:
            await message.answer("❌ У вас нет прав для выполнения этой команды.")
            return

        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /qr <qr_id>\nПример: /qr p0001")
            return

        qr_id = args[1]
        post = await self.get_post_by_qr_id(qr_id)
        
        if not post:
            await message.answer(f"❌ Пост с ID '{qr_id}' не найден.")
            return

        try:
            filename, qr_link = self.generate_qr({'qr_id': qr_id})
            
            # Отправляем QR-код как фото
            with open(filename, 'rb') as qr_file:
                await message.answer_photo(
                    photo=qr_file,
                    caption=(
                        f"📱 <b>QR-код для: {post['title']}</b>\n\n"
                        f"🔗 Ссылка: <code>{qr_link}</code>\n\n"
                        f"При сканировании этого QR-кода пользователи попадут "
                        f"прямо к информации о {post['title']} в боте."
                    ),
                    parse_mode=ParseMode.HTML
                )
            
            # Удаляем временный файл
            os.remove(filename)
            
        except Exception as e:
            logger.error(f"Ошибка генерации QR: {e}")
            await message.answer(f"❌ Ошибка при генерации QR-кода: {e}")

    async def help_command(self, message: Message):
        msg = (
            "📖 <b>Подробная справка по боту \"Вершины России\"</b>\n\n"
            
            "🔍 <b>Основные функции:</b>\n"
            "• Получение информации о горах через QR-коды\n"
            "• Поиск новостей и статей о восхождениях\n"
            "• Доступ к сообществу любителей гор\n\n"
            
            "📱 <b>Команды:</b>\n"
            "/start - Приветствие и главное меню\n"
            "/news - Последние новости о горах\n"
            "/help - Эта справка\n\n"
            
            "🎯 <b>Как работать с QR-кодами:</b>\n"
            "1. Найдите QR-код рядом с информацией о горе\n"
            "2. Отсканируйте его камерой телефона\n"
            "3. Нажмите на ссылку - откроется этот бот\n"
            "4. Получите подробную информацию\n\n"
            
            "💬 <b>Сообщество:</b>\n"
            "• Общий чат: https://t.me/topofrussia\n"
            "• Канал новостей: https://t.me/TopRussiaBrand\n"
            "• Официальный сайт: https://вершина-россии.рф\n\n"
            
            "❓ <b>Нужна помощь?</b> Задайте вопрос в общем чате!"
        )
        await message.answer(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        
    async def show_main_menu(self, message: types.Message):
        """Главное меню с кнопками"""
        await message.answer(
            "🏔️ Главное меню\n"
            "Выберите действие:",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text="💬 Общий чат", 
                            url="https://t.me/topofrussia"
                        ),
                        types.InlineKeyboardButton(
                            text="📢 Наш канал", 
                            url="https://t.me/TopRussiaBrand"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="🔍 Поиск информации", 
                            callback_data="search_posts"
                        ),
                        types.InlineKeyboardButton(
                            text="📰 Новости", 
                            callback_data="show_news"
                        )
                    ]
                ]
            )
        )
    
    async def text_message_handler(self, message: Message, state: FSMContext):
        """Обработка текстовых сообщений"""        
        # Если бот находится в состоянии ожидания ключевого слова для поиска новостей
        current_state = await state.get_state()
        if current_state == SearchStates.waiting_for_news_keyword:
            await self.process_news_search_keyword(message, state)
            return
        elif current_state == SearchStates.waiting_for_post_keyword:
            await self.process_post_search_keyword(message, state)
            return

        if message.text.startswith('/'):
            # Игнорируем команды
            return
        
        # Проверяем, есть ли в тексте ссылка на бота (возможно, от QR-кода)
        bot_username = os.getenv('BOT_USERNAME', 'vershiny_rossii_bot')
        if f'https://t.me/{bot_username}?start=' in message.text:
            qr_url = message.text.split(f'https://t.me/{bot_username}?start=')[-1]
            decoded_qr_url = unquote(qr_url)
            await self.handle_qr_url(message, decoded_qr_url)
        else:
            # Предлагаем воспользоваться меню
            await message.answer(
                "🤖 Я не понимаю обычные сообщения, но могу помочь через меню!\n"
                "Используйте кнопки ниже или команды.",
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(
                            text="🏠 Главное меню", 
                            callback_data="main_menu"
                        )]
                    ]
                )
            )
    
    async def get_news_by_type(self, news_type: str):
        """Получаем новости по типу"""
        async with self.db.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM news WHERE news_type = $1 ORDER BY id DESC", 
                news_type
            )
    
    async def news_command(self, message: Message):
        news_rows = await self.get_all_news()
        if not news_rows:
            await message.answer("📰 Новости не найдены.")
            return

        news_by_type = {}
        for row in news_rows:
            news_by_type.setdefault(row['news_type'], []).append(row)

        message_parts = ["📰 <b>Новости о вершинах России:</b>\n"]
        for news_type, news_list in news_by_type.items():
            message_parts.append(f"\n📂 <b>{news_type}</b>:")
            for news in news_list[:5]:
                title_to_display = news.get('title', f"Новость #{news['id']}")
                message_parts.append(f"  • <a href='{news['link']}'>{title_to_display}</a>")
            if len(news_list) > 5:
                message_parts.append(f"  ... и еще {len(news_list) - 5} новостей")

        full_message = "\n".join(message_parts)
        for part in self.split_message(full_message, 4000):
            await message.answer(part, disable_web_page_preview=True)

    def split_message(self, text, max_length):
        parts, current_part = [], ""
        for line in text.split('\n'):
            if len(current_part) + len(line) + 1 <= max_length:
                current_part += line + '\n'
            else:
                parts.append(current_part.strip())
                current_part = line + '\n'
        if current_part:
            parts.append(current_part.strip())
        return parts
    
    async def insert_test_data(self):
        async with self.db.pool.acquire() as conn:
            # Проверяем, есть ли уже посты
            if await conn.fetchval("SELECT COUNT(*) FROM posts") == 0:
                await conn.execute('''
                    INSERT INTO posts (qr_id, title, description, image_url)
                    VALUES ($1, $2, $3, $4)
                ''', "p0001", "Гора Эльбрус", "Высочайшая вершина России и Европы (5642 м)", 
                "https://t.me/TopRussiaBrand/1")
                
                await conn.execute('''
                    INSERT INTO posts (qr_id, title, description, image_url)
                    VALUES ($1, $2, $3, $4)
                ''', "p0002", "Казбек", "Вулкан на границе Грузии и России", 
                "https://t.me/TopRussiaBrand/2")
                
                await conn.execute('''
                    INSERT INTO posts (qr_id, title, description, image_url)
                    VALUES ($1, $2, $3, $4)
                ''', "p0003", "Белуха", "Высочайшая точка Алтайских гор", 
                "https://t.me/TopRussiaBrand/3")
                
                logger.info("Тестовые посты добавлены.")

            # Проверяем, есть ли уже новости
            if await conn.fetchval("SELECT COUNT(*) FROM news") == 0:
                # Пример тестовых новостей
                news_samples = [
                        ("https://t.me/TopRussiaBrand/288", "История восхождений и экспедиций", "Восхождение на Эльбрус"),
                        ("https://t.me/TopRussiaBrand/289", "История восхождений и экспедиций", "Новые маршруты"),
                        ("https://t.me/TopRussiaBrand/290", "История восхождений и экспедиций", "Экспедиция 2024"),   
                        ("https://t.me/TopRussiaBrand/292", "Культурное и историческое значение горы", "Эльбрус в культуре"),   
                        ("https://t.me/TopRussiaBrand/293", "Культурное и историческое значение горы", "Легенды Кавказа"),   
                        ("https://t.me/TopRussiaBrand/294", "История восхождений и экспедиций", "Первовосходители"),   
                        ("https://t.me/TopRussiaBrand/296", "История восхождений и экспедиций", "Рекорды восхождений"),   
                        ("https://t.me/TopRussiaBrand/297", "Природа и экология Эльбруса", "Флора и фауна"),   
                        ("https://t.me/TopRussiaBrand/298", "История восхождений и экспедиций", "Альпинизм"),   
                        ("https://t.me/TopRussiaBrand/299", "Природа и экология Эльбруса", "Экологические инициативы"),   
                        ("https://t.me/TopRussiaBrand/300", "История восхождений и экспедиций", "Горнолыжный спорт"),
                        ("https://t.me/TopRussiaBrand/301", "Культурное и историческое значение горы", "Мифология гор"),
                        ("https://t.me/TopRussiaBrand/302", "Природа и экология Эльбруса", "Климат и погода"),
                        ("https://t.me/TopRussiaBrand/303", "История восхождений и экспедиций", "Женские восхождения"),
                        ("https://t.me/TopRussiaBrand/304", "Культурное и историческое значение горы", "Фольклор"),
                        ("https://t.me/TopRussiaBrand/305", "Природа и экология Эльбруса", "Геология"),
                ]

                for link, news_type, title in news_samples:
                    await conn.execute('''
                        INSERT INTO news (link, news_type, title)
                        VALUES ($1, $2, $3)
                    ''', link, news_type, title)
                
                logger.info("Тестовые новости добавлены.")

    async def callback_handler(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработчик инлайн кнопок"""
        try:
            if callback.data == "main_menu":
                await self.show_main_menu(callback.message)
                await callback.answer()
                
            elif callback.data == "search_posts":
                await callback.message.answer(
                    "🔍 <b>Поиск информации о горах</b>\n\n"
                    "Введите название горы или ключевое слово для поиска:",
                    parse_mode=ParseMode.HTML
                )
                await state.set_state(SearchStates.waiting_for_post_keyword)
                await callback.answer()
                
            elif callback.data == "show_news":
                await self.show_news_categories(callback.message)
                await callback.answer()
                
            elif callback.data.startswith("news_category_"):
                category = callback.data.replace("news_category_", "")
                await self.show_news_by_category(callback.message, category)
                await callback.answer()
                
            elif callback.data == "search_news":
                await callback.message.answer(
                    "🔍 <b>Поиск новостей</b>\n\n"
                    "Введите ключевое слово для поиска новостей:",
                    parse_mode=ParseMode.HTML
                )
                await state.set_state(SearchStates.waiting_for_news_keyword)
                await callback.answer()
                
            elif callback.data.startswith("next_"):
                post_id = int(callback.data.replace("next_", ""))
                await self.show_next_post(callback.message, post_id)
                await callback.answer()
                
            else:
                await callback.answer("Неизвестная команда")
                
        except Exception as e:
            logger.error(f"Ошибка в callback_handler: {e}")
            await callback.answer("Произошла ошибка")

    async def show_news_categories(self, message: types.Message):
        """Показать категории новостей"""
        try:
            async with self.db.pool.acquire() as conn:
                categories = await conn.fetch(
                    "SELECT DISTINCT news_type, COUNT(*) as count FROM news GROUP BY news_type ORDER BY count DESC"
                )
            
            if not categories:
                await message.answer("📰 Новости не найдены.")
                return
            
            buttons = []
            for category in categories:
                buttons.append([
                    types.InlineKeyboardButton(
                        text=f"📂 {category['news_type']} ({category['count']})",
                        callback_data=f"news_category_{category['news_type']}"
                    )
                ])
            
            buttons.append([
                types.InlineKeyboardButton(
                    text="🔍 Поиск новостей",
                    callback_data="search_news"
                )
            ])
            
            buttons.append([
                types.InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="main_menu"
                )
            ])
            
            markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await message.answer(
                "📰 <b>Категории новостей:</b>\n\n"
                "Выберите интересующую вас категорию:",
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Ошибка в show_news_categories: {e}")
            await message.answer("Произошла ошибка при загрузке категорий новостей.")

    async def show_news_by_category(self, message: types.Message, category: str):
        """Показать новости по категории"""
        try:
            news_list = await self.get_news_by_type(category)
            
            if not news_list:
                await message.answer(f"📰 Новости в категории '{category}' не найдены.")
                return
            
            msg_parts = [f"📰 <b>Новости: {category}</b>\n"]
            
            for i, news in enumerate(news_list[:10], 1):  # Показываем первые 10
                title = news.get('title', f"Новость #{news['id']}")
                msg_parts.append(f"{i}. <a href='{news['link']}'>{title}</a>")
            
            if len(news_list) > 10:
                msg_parts.append(f"\n... и еще {len(news_list) - 10} новостей")
            
            markup = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="💬 Обсудить в чате",
                        url="https://t.me/topofrussia"
                    ),
                    types.InlineKeyboardButton(
                        text="📢 Канал новостей",
                        url="https://t.me/TopRussiaBrand"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="◀️ Назад к категориям",
                        callback_data="show_news"
                    ),
                    types.InlineKeyboardButton(
                        text="🏠 Главное меню",
                        callback_data="main_menu"
                    )
                ]
            ])
            
            full_message = "\n".join(msg_parts)
            await message.answer(
                full_message,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Ошибка в show_news_by_category: {e}")
            await message.answer("Произошла ошибка при загрузке новостей.")

    async def process_news_search_keyword(self, message: types.Message, state: FSMContext):
        """Обработка поискового запроса по новостям"""
        try:
            keyword = message.text.strip().lower()
            
            async with self.db.pool.acquire() as conn:
                # Ищем по title и news_type
                results = await conn.fetch("""
                    SELECT * FROM news 
                    WHERE LOWER(title) LIKE $1 OR LOWER(news_type) LIKE $1
                    ORDER BY id DESC
                    LIMIT 15
                """, f"%{keyword}%")
            
            await state.clear()  # Сбрасываем состояние
            
            if not results:
                await message.answer(
                    f"🔍 По запросу '<b>{message.text}</b>' новости не найдены.\n\n"
                    "Попробуйте другое ключевое слово или просмотрите все категории.",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(
                            text="📰 Все категории",
                            callback_data="show_news"
                        )],
                        [types.InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="main_menu"
                        )]
                    ]),
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Группируем результаты по типу
            results_by_type = {}
            for result in results:
                news_type = result['news_type']
                if news_type not in results_by_type:
                    results_by_type[news_type] = []
                results_by_type[news_type].append(result)
            
            msg_parts = [f"🔍 <b>Результаты поиска по запросу '{message.text}':</b>\n"]
            
            for news_type, news_list in results_by_type.items():
                msg_parts.append(f"\n📂 <b>{news_type}</b>:")
                for news in news_list[:5]:  # Показываем по 5 из каждой категории
                    title = news.get('title', f"Новость #{news['id']}")
                    msg_parts.append(f"  • <a href='{news['link']}'>{title}</a>")
                
                if len(news_list) > 5:
                    msg_parts.append(f"  ... и еще {len(news_list) - 5} в этой категории")
            
            markup = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="💬 Обсудить в чате",
                        url="https://t.me/topofrussia"
                    ),
                    types.InlineKeyboardButton(
                        text="📢 Канал новостей",
                        url="https://t.me/TopRussiaBrand"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="🔍 Новый поиск",
                        callback_data="search_news"
                    ),
                    types.InlineKeyboardButton(
                        text="🏠 Главное меню",
                        callback_data="main_menu"
                    )
                ]
            ])
            
            full_message = "\n".join(msg_parts)
            # Разбиваем длинное сообщение если нужно
            for part in self.split_message(full_message, 3500):
                await message.answer(
                    part,
                    reply_markup=markup if part == self.split_message(full_message, 3500)[-1] else None,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            
        except Exception as e:
            logger.error(f"Ошибка в process_news_search_keyword: {e}")
            await message.answer("Произошла ошибка при поиске новостей.")
            await state.clear()

    async def process_post_search_keyword(self, message: types.Message, state: FSMContext):
        """Обработка поискового запроса по постам"""
        try:
            keyword = message.text.strip().lower()
            
            async with self.db.pool.acquire() as conn:
                # Ищем по title и description
                results = await conn.fetch("""
                    SELECT * FROM posts 
                    WHERE (LOWER(title) LIKE $1 OR LOWER(description) LIKE $1) 
                    AND is_active = TRUE
                    ORDER BY id
                    LIMIT 10
                """, f"%{keyword}%")
            
            await state.clear()  # Сбрасываем состояние
            
            if not results:
                await message.answer(
                    f"🔍 По запросу '<b>{message.text}</b>' информация не найдена.\n\n"
                    "Попробуйте другое ключевое слово или отсканируйте QR-код.",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(
                            text="🔍 Новый поиск",
                            callback_data="search_posts"
                        )],
                        [types.InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="main_menu"
                        )]
                    ]),
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Записываем взаимодействие пользователя
            await self.log_user_interaction(message.from_user, 'search', qr_id=keyword)
            
            # Если найден только один результат, показываем его сразу
            if len(results) == 1:
                await self.show_post(message, results[0])
                return
            
            # Если найдено несколько результатов, показываем список
            msg_parts = [f"🔍 <b>Найдено {len(results)} результатов по запросу '{message.text}':</b>\n"]
            
            buttons = []
            for i, post in enumerate(results, 1):
                msg_parts.append(f"{i}. <b>{post['title']}</b>\n   {post['description'][:100]}{'...' if len(post['description']) > 100 else ''}\n")
                
                buttons.append([
                    types.InlineKeyboardButton(
                        text=f"📍 {post['title']}",
                        callback_data=f"show_post_{post['qr_id']}"
                    )
                ])
            
            buttons.append([
                types.InlineKeyboardButton(
                    text="🔍 Новый поиск",
                    callback_data="search_posts"
                ),
                types.InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="main_menu"
                )
            ])
            
            markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
            
            full_message = "\n".join(msg_parts)
            await message.answer(
                full_message[:4000],  # Ограничиваем длину сообщения
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Ошибка в process_post_search_keyword: {e}")
            await message.answer("Произошла ошибка при поиске информации.")
            await state.clear()

    async def show_next_post(self, message: types.Message, current_post_id: int):
        """Показать следующий пост"""
        try:
            async with self.db.pool.acquire() as conn:
                next_post = await conn.fetchrow("""
                    SELECT * FROM posts 
                    WHERE id > $1 AND is_active = TRUE 
                    ORDER BY id LIMIT 1
                """, current_post_id)
                
                if not next_post:
                    # Если следующего нет, берем первый
                    next_post = await conn.fetchrow("""
                        SELECT * FROM posts 
                        WHERE is_active = TRUE 
                        ORDER BY id LIMIT 1
                    """)
            
            if next_post:
                await self.show_post(message, next_post)
            else:
                await message.answer("📍 Больше постов не найдено.")
                
        except Exception as e:
            logger.error(f"Ошибка в show_next_post: {e}")
            await message.answer("Произошла ошибка при загрузке следующего поста.")

    async def run(self):
        """Запуск бота"""
        try:
            # Проверяем наличие токена
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            if not bot_token:
                logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
                raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env файле")
            
            # Инициализация бота
            self.bot = Bot(
                token=bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            self.dp = Dispatcher()
            
            # Настройка базы данных
            await self.setup_database()
            await self.insert_test_data()
            
            # Регистрация обработчиков
            self.dp.message.register(self.start_command, Command('start'))
            self.dp.message.register(self.help_command, Command('help'))
            self.dp.message.register(self.news_command, Command('news'))
            self.dp.message.register(self.generate_qr_command, Command('qr'))
            
            # Обработчик текстовых сообщений (должен быть последним среди message handlers)
            self.dp.message.register(self.text_message_handler)
            
            # Обработчик callback'ов
            self.dp.callback_query.register(self.callback_handler)
            
            # Подключение новостных хэндлеров
            try:
                news_handlers.register_handlers(self.dp, self.db)
                logger.info("Новостные хэндлеры подключены")
            except Exception as e:
                logger.warning(f"Не удалось подключить новостные хэндлеры: {e}")
            
            logger.info("Бот запущен")
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            raise
        finally:
            # Закрытие соединений
            if self.bot:
                await self.bot.session.close()
            if self.db:
                await self.db.close()

async def main():
    """Главная функция"""
    bot = TelegramBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")

if __name__ == '__main__':
    asyncio.run(main())