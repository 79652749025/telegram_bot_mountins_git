import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from urllib.parse import unquote
import asyncpg
from dotenv import load_dotenv

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

class TelegramBot:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.db_pool = None
        
    async def setup_database(self):
        """Настройка подключения к базе данных"""
        db_uri = os.getenv('DB_URI')
        if not db_uri:
            # Формируем URI из отдельных параметров
            user = os.getenv('DB_USER', 'postgres')
            password = os.getenv('DB_PASSWORD')
            database = os.getenv('DB_NAME', 'vershinyrossii2')
            host = os.getenv('DB_HOST', '127.0.0.1')
            port = os.getenv('DB_PORT', '5433')
            
            if not password:
                raise ValueError("DB_PASSWORD не найден в .env")
            
            db_uri = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        
        self.db_pool = await asyncpg.create_pool(db_uri)
        await self.init_tables()
        await self.insert_test_data()
        logger.info("База данных подключена.")

    async def init_tables(self):
        """Создание таблиц в базе данных"""
        try:
            async with self.db_pool.acquire() as conn:
                # Таблица постов
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS posts (
                        id SERIAL PRIMARY KEY,
                        qr_id VARCHAR(50) UNIQUE,
                        image_url TEXT NOT NULL,
                        content_url TEXT NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        description TEXT NOT NULL,
                        url VARCHAR(255),
                        code VARCHAR(50),
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица новостей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS news (
                        id SERIAL PRIMARY KEY,
                        qr_id VARCHAR(50) UNIQUE,
                        image_url TEXT,
                        content_url TEXT,
                        link TEXT NOT NULL,
                        news_type TEXT NOT NULL,
                        title VARCHAR(255) DEFAULT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица пользовательских чатов
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_chats (
                        user_id BIGINT PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица статистики использования
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS usage_stats (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        action VARCHAR(100),
                        post_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                logger.info("Все таблицы успешно созданы/проверены")
        except Exception as e:
            logger.error(f"Ошибка создания таблиц: {e}")
            raise

    async def log_user_action(self, user_id: int, action: str, post_id: int = None):
        """Логирование действий пользователя"""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO usage_stats (user_id, action, post_id) VALUES ($1, $2, $3)",
                    user_id, action, post_id
                )
        except Exception as e:
            logger.error(f"Ошибка логирования действия пользователя: {e}")

    async def save_user_chat(self, user_id: int, chat_id: int):
        """Сохранение информации о чате пользователя"""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO user_chats (user_id, chat_id) 
                       VALUES ($1, $2) 
                       ON CONFLICT (user_id) DO UPDATE SET chat_id = $2""",
                    user_id, chat_id
                )
        except Exception as e:
            logger.error(f"Ошибка сохранения чата пользователя: {e}")

    async def get_all_news(self, news_type=None, limit=50):
        """Получение всех новостей с фильтрацией по типу"""
        try:
            async with self.db_pool.acquire() as conn:
                if news_type and news_type != "all":
                    # Маппинг типов новостей
                    type_mapping = {
                        "history": "История восхождений и экспедиций",
                        "nature": "Природа и экология Эльбруса",
                        "culture": "Культурное и историческое значение горы"
                    }
                    filter_type = type_mapping.get(news_type)
                    if filter_type:
                        return await conn.fetch(
                            "SELECT * FROM news WHERE news_type = $1 ORDER BY created_at DESC LIMIT $2", 
                            filter_type, limit
                        )
                
                return await conn.fetch("SELECT * FROM news ORDER BY created_at DESC LIMIT $1", limit)
        except Exception as e:
            logger.error(f"Ошибка при получении новостей: {e}")
            return []

    async def get_post_by_id(self, item_id: str):
        """Получение поста по ID"""
        try:
            async with self.db_pool.acquire() as conn:
                return await conn.fetchrow("SELECT * FROM posts WHERE qr_id = $1 AND is_active = TRUE", item_id)
        except Exception as e:
            logger.error(f"Ошибка получения поста: {e}")
            return None

    async def get_next_post(self, current_post_id: int):
        """Получение следующего поста"""
        try:
            async with self.db_pool.acquire() as conn:
                return await conn.fetchrow(
                    "SELECT * FROM posts WHERE id > $1 AND is_active = TRUE ORDER BY id LIMIT 1", 
                    current_post_id
                )
        except Exception as e:
            logger.error(f"Ошибка получения следующего поста: {e}")
            return None

    async def get_previous_post(self, current_post_id: int):
        """Получение предыдущего поста"""
        try:
            async with self.db_pool.acquire() as conn:
                return await conn.fetchrow(
                    "SELECT * FROM posts WHERE id < $1 AND is_active = TRUE ORDER BY id DESC LIMIT 1", 
                    current_post_id
                )
        except Exception as e:
            logger.error(f"Ошибка получения предыдущего поста: {e}")
            return None

    def create_main_menu_keyboard(self):
        """Создание главного меню с инлайн клавиатурой"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 Общий чат", url="https://t.me/topofrussia"),
                InlineKeyboardButton(text="📢 Наш канал", url="https://t.me/TopRussiaBrand")
            ],
            [
                InlineKeyboardButton(text="📰 Новости", callback_data="show_news"),
                InlineKeyboardButton(text="🔍 Поиск постов", callback_data="search_posts")
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats"),
                InlineKeyboardButton(text="ℹ️ Помощь", callback_data="show_help")
            ]
        ])
        return keyboard

    def create_post_keyboard(self, post_id: int):
        """Создание клавиатуры для поста"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Предыдущий", callback_data=f"prev_post_{post_id}"),
                InlineKeyboardButton(text="➡️ Следующий", callback_data=f"next_post_{post_id}")
            ],
            [
                InlineKeyboardButton(text="🔔 Подписаться", url="https://t.me/TopRussiaBrand"),
                InlineKeyboardButton(text="💬 Обсудить", url="https://t.me/topofrussia")
            ],
            [
                InlineKeyboardButton(text="🌟 Сайт", url="https://вершина-россии.рф"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ]
        ])
        return keyboard

    def create_news_keyboard(self, current_type="all"):
        """Создание клавиатуры для новостей"""
        keyboard_buttons = [
            [
                InlineKeyboardButton(text="🏔️ История восхождений", callback_data="news_type_history"),
                InlineKeyboardButton(text="🌿 Природа и экология", callback_data="news_type_nature")
            ],
            [
                InlineKeyboardButton(text="🏛️ Культурное значение", callback_data="news_type_culture"),
                InlineKeyboardButton(text="📊 Все новости", callback_data="news_type_all")
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"news_type_{current_type}"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ]
        ]
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    async def start_command(self, message: Message):
        """Обработка команды /start"""
        # Сохраняем информацию о пользователе
        await self.save_user_chat(message.from_user.id, message.chat.id)
        await self.log_user_action(message.from_user.id, "start_command")
        
        args = message.text.split()
        
        if len(args) > 1:
            # Обработка QR-кода из параметра start
            qr_param = unquote(args[1])
            await self.handle_qr_url(message, qr_param)
        else:
            await self.show_main_menu(message)

    async def show_main_menu(self, message: Message):
        """Показ главного меню"""
        text = (
            "🏔️ <b>Добро пожаловать в бот 'Вершины России'!</b>\n\n"
            "🔹 Сканируйте QR-коды для доступа к контенту\n"
            "🔹 Читайте свежие новости о горах России\n"
            "🔹 Присоединяйтесь к сообществу путешественников\n\n"
            "Выберите действие:"
        )
        
        try:
            # Удаляем предыдущее сообщение если это callback
            if hasattr(message, 'message_id'):
                await message.edit_text(
                    text, 
                    reply_markup=self.create_main_menu_keyboard(),
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.answer(
                    text, 
                    reply_markup=self.create_main_menu_keyboard(),
                    parse_mode=ParseMode.HTML
                )
        except Exception:
            # Если не удалось отредактировать, отправляем новое сообщение
            await message.answer(
                text, 
                reply_markup=self.create_main_menu_keyboard(),
                parse_mode=ParseMode.HTML
            )

    async def handle_qr_url(self, message: Message, qr_url: str):
        """Обработка URL из QR-кода"""
        try:
            # Извлекаем идентификатор из URL
            item_id = qr_url.split('/')[-1].split('.')[0]
            
            post = await self.get_post_by_id(item_id)
            
            if post:
                await self.log_user_action(message.from_user.id, "qr_scan", post['id'])
                await self.show_post(message, post)
            else:
                await message.answer(
                    "🔍 Контент по этому QR-коду не найден",
                    reply_markup=self.create_main_menu_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Ошибка обработки QR-кода: {e}")
            await message.answer(
                "⚠️ Ошибка обработки QR-кода",
                reply_markup=self.create_main_menu_keyboard()
            )

    async def show_post(self, message: Message, post):
        """Показ поста"""
        try:
            caption = f"<b>{post['title']}</b>\n\n{post['description']}"
            
            if post['url']:
                caption += f"\n\n🔗 <a href='{post['url']}'>Подробнее</a>"
            
            if post['image_url']:
                await message.answer_photo(
                    photo=post['image_url'],
                    caption=caption,
                    reply_markup=self.create_post_keyboard(post['id']),
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.answer(
                    caption,
                    reply_markup=self.create_post_keyboard(post['id']),
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Ошибка показа поста: {e}")
            await message.answer("Ошибка загрузки контента")

    async def news_command(self, message: Message):
        """Обработка команды /news"""
        await self.log_user_action(message.from_user.id, "news_command")
        await self.show_news(message)

    async def show_news(self, message: Message, news_type: str = "all"):
        """Показ новостей в улучшенном формате"""
        try:
            # Получаем все новости
            all_news = await self.get_all_news()
            
            if not all_news:
                text = "📰 Новости не найдены."
                keyboard = self.create_main_menu_keyboard()
            else:
                # Фильтруем новости по типу если нужно
                if news_type != "all":
                    type_mapping = {
                        "history": "История восхождений и экспедиций",
                        "nature": "Природа и экология Эльбруса",
                        "culture": "Культурное и историческое значение горы"
                    }
                    filter_type = type_mapping.get(news_type)
                    if filter_type:
                        filtered_news = [n for n in all_news if n['news_type'] == filter_type]
                        text = await self.format_filtered_news(filtered_news, filter_type)
                    else:
                        text = await self.format_all_news(all_news)
                else:
                    text = await self.format_all_news(all_news)
                
                keyboard = self.create_news_keyboard(news_type)
            
            # Отправляем или редактируем сообщение
            try:
                if hasattr(message, 'edit_text'):
                    await message.edit_text(
                        text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                else:
                    await message.answer(
                        text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
            except Exception:
                # Если редактирование не удалось, отправляем новое сообщение
                await message.answer(
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                
        except Exception as e:
            logger.error(f"Ошибка показа новостей: {e}")
            await message.answer("Ошибка загрузки новостей")

    async def format_all_news(self, news_rows):
        """Форматирование всех новостей по типам"""
        # Группировка по типам
        news_by_type = {}
        for row in news_rows:
            news_type = row['news_type']
            if news_type not in news_by_type:
                news_by_type[news_type] = []
            news_by_type[news_type].append(row)

        # Формирование сообщения
        message_parts = ["📰 <b>Новости о вершинах России:</b>\n"]
        
        # Определяем порядок отображения категорий
        type_order = [
            "История восхождений и экспедиций",
            "Культурное и историческое значение горы", 
            "Природа и экология Эльбруса"
        ]
        
        for news_type in type_order:
            if news_type in news_by_type:
                news_list = news_by_type[news_type]
                message_parts.append(f"\n📂 <b>{news_type}</b>:")
                
                # Показываем первые 5 новостей
                displayed_count = 0
                for news in news_list[:5]:
                    displayed_count += 1
                    # Извлекаем номер поста из ссылки
                    post_number = news['link'].split('/')[-1] if '/' in news['link'] else str(news['id'])
                    title = news['title'] if news['title'] else f"Новость #{news['id']}"
                    message_parts.append(f"  • <a href='{news['link']}'>{title}</a>")
                
                # Показываем количество оставшихся новостей
                remaining = len(news_list) - displayed_count
                if remaining > 0:
                    message_parts.append(f"  ... и еще {remaining} новостей")
        
        # Добавляем другие типы, если есть
        for news_type, news_list in news_by_type.items():
            if news_type not in type_order:
                message_parts.append(f"\n📂 <b>{news_type}</b>:")
                for news in news_list[:5]:
                    title = news['title'] if news['title'] else f"Новость #{news['id']}"
                    message_parts.append(f"  • <a href='{news['link']}'>{title}</a>")
                
                remaining = len(news_list) - 5
                if remaining > 0:
                    message_parts.append(f"  ... и еще {remaining} новостей")

        return "\n".join(message_parts)

    async def format_filtered_news(self, news_list, news_type):
        """Форматирование отфильтрованных новостей"""
        message_parts = [f"📰 <b>{news_type}:</b>\n"]
        
        for i, news in enumerate(news_list, 1):
            title = news['title'] if news['title'] else f"Новость #{news['id']}"
            message_parts.append(f"{i}. <a href='{news['link']}'>{title}</a>")
        
        if not news_list:
            message_parts.append("Новости данного типа не найдены.")
        
        return "\n".join(message_parts)

    async def show_stats(self, message: Message):
        """Показ статистики использования бота"""
        try:
            async with self.db_pool.acquire() as conn:
                # Общая статистика
                total_users = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM user_chats")
                total_posts = await conn.fetchval("SELECT COUNT(*) FROM posts WHERE is_active = TRUE")
                total_news = await conn.fetchval("SELECT COUNT(*) FROM news")
                total_actions = await conn.fetchval("SELECT COUNT(*) FROM usage_stats")
                
                # Популярные действия
                popular_actions = await conn.fetch("""
                    SELECT action, COUNT(*) as count 
                    FROM usage_stats 
                    GROUP BY action 
                    ORDER BY count DESC 
                    LIMIT 5
                """)
                
                stats_text = (
                    "📊 <b>Статистика бота 'Вершины России'</b>\n\n"
                    f"👥 Всего пользователей: <b>{total_users}</b>\n"
                    f"📝 Активных постов: <b>{total_posts}</b>\n"
                    f"📰 Новостей: <b>{total_news}</b>\n"
                    f"🎯 Всего действий: <b>{total_actions}</b>\n\n"
                )
                
                if popular_actions:
                    stats_text += "🔥 <b>Популярные действия:</b>\n"
                    action_names = {
                        "start_command": "Запуск бота",
                        "news_command": "Просмотр новостей",
                        "qr_scan": "Сканирование QR",
                        "show_help": "Справка"
                    }
                    
                    for action in popular_actions:
                        action_name = action_names.get(action['action'], action['action'])
                        stats_text += f"  • {action_name}: {action['count']}\n"
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ])
                
                if hasattr(message, 'edit_text'):
                    await message.edit_text(
                        stats_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.answer(
                        stats_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
                    
        except Exception as e:
            logger.error(f"Ошибка показа статистики: {e}")
            await message.answer("Ошибка загрузки статистики")

    async def help_command(self, message: Message):
        """Обработка команды /help"""
        await self.log_user_action(message.from_user.id, "show_help")
        
        help_text = (
            "📖 <b>Помощь по использованию бота</b>\n\n"
            "🔹 <b>/start</b> - Главное меню\n"
            "🔹 <b>/news</b> - Список новостей\n"
            "🔹 <b>/help</b> - Эта справка\n"
            "🔹 <b>/stats</b> - Статистика бота\n\n"
            "💡 <b>Как пользоваться:</b>\n"
            "• Сканируйте QR-коды на плакатах\n"
            "• Используйте кнопки для навигации\n"
            "• Подписывайтесь на наш канал для обновлений\n"
            "• Участвуйте в обсуждениях в группе\n\n"
            "📺 <b>Наш канал:</b> @TopRussiaBrand\n"
            "💬 <b>Общий чат:</b> @topofrussia\n"
            "🌐 <b>Сайт:</b> вершина-россии.рф"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        try:
            if hasattr(message, 'edit_text'):
                await message.edit_text(
                    help_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.answer(
                    help_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
        except Exception:
            await message.answer(
                help_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )

    async def stats_command(self, message: Message):
        """Обработка команды /stats"""
        await self.show_stats(message)

    async def add_news_command(self, message: Message):
        """Добавление новости (только для админов)"""
        try:
            parts = message.text.split(maxsplit=3)
            if len(parts) < 3:
                await message.answer("❌ Использование: /addnews ссылка тип_новости [заголовок]")
                return
                
            link = parts[1]
            news_type = parts[2]
            title = parts[3] if len(parts) > 3 else None
            
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO news (link, news_type, title) VALUES ($1, $2, $3)",
                    link, news_type, title
                )
            
            await message.answer("✅ Новость успешно добавлена!")
        except Exception as e:
            logger.error(f"Ошибка добавления новости: {e}")
            await message.answer(f"❌ Ошибка добавления новости: {e}")

    async def handle_callback_query(self, callback: CallbackQuery):
        """Обработка инлайн кнопок"""
        try:
            data = callback.data
            user_id = callback.from_user.id
            
            if data == "main_menu":
                await self.show_main_menu(callback.message)
                
            elif data == "show_news":
                await self.log_user_action(user_id, "show_news")
                await self.show_news(callback.message)
                
            elif data == "show_help":
                await self.log_user_action(user_id, "show_help")
                await self.help_command(callback.message)
                
            elif data == "show_stats":
                await self.log_user_action(user_id, "show_stats")
                await self.show_stats(callback.message)
                
            elif data.startswith("next_post_"):
                post_id = int(data.split("_")[-1])
                next_post = await self.get_next_post(post_id)
                if next_post:
                    await self.log_user_action(user_id, "next_post", next_post['id'])
                    await self.show_post(callback.message, next_post)
                else:
                    await callback.answer("Это последний пост!", show_alert=True)
                    
            elif data.startswith("prev_post_"):
                post_id = int(data.split("_")[-1])
                prev_post = await self.get_previous_post(post_id)
                if prev_post:
                    await self.log_user_action(user_id, "prev_post", prev_post['id'])
                    await self.show_post(callback.message, prev_post)
                else:
                    await callback.answer("Это первый пост!", show_alert=True)
                    
            elif data.startswith("news_type_"):
                news_type = data.split("_")[-1]
                await self.log_user_action(user_id, f"news_filter_{news_type}")
                await self.show_news(callback.message, news_type)
                
            elif data == "search_posts":
                search_text = (
                    "🔍 <b>Поиск постов</b>\n\n"
                    "Для поиска постов:\n"
                    "• Сканируйте QR-коды на плакатах\n"
                    "• Отправьте ссылку на пост\n"
                    "• Используйте команды бота\n\n"
                    "📺 Все материалы публикуются в канале @TopRussiaBrand"
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Перейти к каналу", url="https://t.me/TopRussiaBrand")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ])
                
                try:
                    await callback.message.edit_text(
                        search_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    await callback.message.answer(
                        search_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
            
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
            await callback.message.answer("⚠️ Ошибка обработки запроса. Попробуйте позже.")
            await callback.answer("⚠️ Ошибка", show_alert=True)
    async def run(self):
        """Запуск бота"""
        logger.info("Запуск Telegram-бота...")
        try:
            await self.setup_database()
            await self.setup_bot()
            
            logger.info("Бот запущен. Нажмите Ctrl+C для остановки...")
            await self.dp.start_polling(self.bot)
            
        except asyncio.CancelledError:
            logger.info("Получен сигнал завершения...")
        except Exception as e:
            logger.error(f"Ошибка в работе бота: {e}")
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Очистка ресурсов"""
        logger.info("Очистка ресурсов...")
        if self.bot:
            await self.bot.session.close()
        if self.db_pool:
            await self.db_pool.close()
        logger.info("Бот завершен.")

if __name__ == '__main__':
    bot = TelegramBot()
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")