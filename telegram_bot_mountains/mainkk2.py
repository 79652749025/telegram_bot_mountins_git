# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import hashlib
from urllib.parse import unquote, quote_plus
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder # Импортируем InlineKeyboardBuilder для удобства
from database.postgres_VR2 import Database 
from dotenv import load_dotenv
import qrcode
import hashlib
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram import F

ADMIN_IDS = (709108561, 7637004765)
# --- Настройка логирования ---
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

# --- Состояния для FSM ---
class SearchStates(StatesGroup):
    waiting_for_post_keyword = State()
    waiting_for_news_keyword = State()

# --- Константы ---
NEWS_PER_PAGE = 5 # Количество новостей на одной странице


# --- Основной класс бота ---
class TelegramBot:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.db = None
        self.bot_username = os.getenv('BOT_USERNAME', 'vershiny_rossii_bot')
        self.admin_id = os.getenv('ADMIN_ID')

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
            await self.db.connect() # Предполагаем, что у вашего класса Database есть метод connect()
            await self.init_tables()
            await self.insert_test_data()
            logger.info("База данных готова")
        except Exception as e:
            logger.error(f"Ошибка настройки БД: {e}")
            raise

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

                # Таблица новостей (добавлен UNIQUE CONFLICT на telegram_url для on_conflict)
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS news (
                        id SERIAL PRIMARY KEY,
                        telegram_url TEXT UNIQUE NOT NULL, -- Добавлено UNIQUE
                        news_type TEXT NOT NULL,
                        title TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица взаимодействий пользователей
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_interactions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        last_name VARCHAR(255),
                        qr_id VARCHAR(50),
                        post_id INTEGER REFERENCES posts(id),
                        interaction_type VARCHAR(50) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            logger.info("Таблицы успешно созданы")
        except Exception as e:
            logger.error(f"Ошибка создания таблиц: {e}")
            raise

    async def on_join(message: Message):
        if message.new_chat_members:
            for user in message.new_chat_members:
                await message.reply(f"Привет, {user.full_name} 👋 Добро пожаловать!")
    
    async def broadcast_message(application, text: str):
        async with application.bot_data["db"].pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id FROM subscribers")

        for row in rows:
            try:
                await application.bot.send_message(chat_id=row["user_id"], text=text)
                await asyncio.sleep(0.05)
            except Exception as e:
                logging.warning(f"Ошибка при отправке {row['user_id']}: {e}")



            
    async def insert_test_data(self):
        """Добавление тестовых данных"""
        async with self.db.pool.acquire() as conn:
            # Проверяем, есть ли уже тестовые новости
            if await conn.fetchval("SELECT COUNT(*) FROM news WHERE news_type = 'История восхождений и экспедиций'") < 10:
                news_data = [
                        ('https://t.me/TopRussiaBrand/288', 'История восхождений и экспедиций', 'Новость #1'),
                        ('https://t.me/TopRussiaBrand/289', 'История восхождений и экспедиций', 'Новость #2'),
                        ('https://t.me/TopRussiaBrand/290', 'История восхождений и экспедиций', 'Новость #3'),
                        ('https://t.me/TopRussiaBrand/292', 'Культурное и историческое значение горы', 'Новость #4'),
                        ('https://t.me/TopRussiaBrand/293', 'Культурное и историческое значение горы', 'Новость #5'),
                        ('https://t.me/TopRussiaBrand/294', 'История восхождений и экспедиций', 'Новость #6'),
                        ('https://t.me/TopRussiaBrand/296', 'История восхождений и экспедиций', 'Новость #7'),
                        ('https://t.me/TopRussiaBrand/297', 'Природа и экология Эльбруса', 'Новость #8'),
                        ('https://t.me/TopRussiaBrand/298', 'История восхождений и экспедиций', 'Новость #9'),
                        ('https://t.me/TopRussiaBrand/299', 'Природа и экология Эльбруса', 'Новость #10'),
                        ('https://t.me/TopRussiaBrand/300', 'История восхождений и экспедиций', 'Новость #11'),
                        ('https://t.me/TopRussiaBrand/301', 'История восхождений и экспедиций', 'Новость #12'),
                        ('https://t.me/TopRussiaBrand/303', 'Культурное и историческое значение горы', 'Новость #13'),
                        ('https://t.me/TopRussiaBrand/304', 'Культурное и историческое значение горы', 'Новость #14'),
                        ('https://t.me/TopRussiaBrand/306', 'Культурное и историческое значение горы', 'Новость #15'),
                        ('https://t.me/TopRussiaBrand/307', 'Культурное и историческое значение горы', 'Новость #16'),
                        ('https://t.me/TopRussiaBrand/308', 'История восхождений и экспедиций', 'Новость #17'),
                        ('https://t.me/TopRussiaBrand/309', 'История восхождений и экспедиций', 'Новость #18'),
                        ('https://t.me/TopRussiaBrand/311', 'Культурное и историческое значение горы', 'Новость #19'),
                        ('https://t.me/TopRussiaBrand/312', 'Культурное и историческое значение горы', 'Новость #20'),
                        ('https://t.me/TopRussiaBrand/313', 'Культурное и историческое значение горы', 'Новость #21'),
                        ('https://t.me/TopRussiaBrand/314', 'История восхождений и экспедиций', 'Новость #22'),
                        ('https://t.me/TopRussiaBrand/315', 'Природа и экология Эльбруса', 'Новость #23'),
                        ('https://t.me/TopRussiaBrand/317', 'История восхождений и экспедиций', 'Новость #24'),
                        ('https://t.me/TopRussiaBrand/318', 'Культурное и историческое значение горы', 'Новость #25'),
                        ('https://t.me/TopRussiaBrand/320', 'Культурное и историческое значение горы', 'Новость #26'),
                        ('https://t.me/TopRussiaBrand/321', 'История восхождений и экспедиций', 'Новость #27'),
                        ('https://t.me/TopRussiaBrand/322', 'История восхождений и экспедиций', 'Новость #28'),
                        ('https://t.me/TopRussiaBrand/323', 'История восхождений и экспедиций', 'Новость #29'),
                        ('https://t.me/TopRussiaBrand/325', 'История восхождений и экспедиций', 'Новость #30'),
                        ('https://t.me/TopRussiaBrand/326', 'История восхождений и экспедиций', 'Новость #31'),
                        ('https://t.me/TopRussiaBrand/327', 'Культурное и историческое значение горы', 'Новость #32'),
                        ('https://t.me/TopRussiaBrand/328', 'Культурное и историческое значение горы', 'Новость #33'),
                        ('https://t.me/TopRussiaBrand/329', 'Культурное и историческое значение горы', 'Новость #34'),
                        ('https://t.me/TopRussiaBrand/330', 'Культурное и историческое значение горы', 'Новость #35'),
                        ('https://t.me/TopRussiaBrand/333', 'История восхождений и экспедиций', 'Новость #36'),
                        ('https://t.me/TopRussiaBrand/334', 'История восхождений и экспедиций', 'Новость #37'),
                        ('https://t.me/TopRussiaBrand/335', 'Культурное и историческое значение горы', 'Новость #38'),
                        ('https://t.me/TopRussiaBrand/336', 'История восхождений и экспедиций', 'Новость #39'),
                        ('https://t.me/TopRussiaBrand/337', 'Культурное и историческое значение горы', 'Новость #40'),
                        ('https://t.me/TopRussiaBrand/339', 'История восхождений и экспедиций', 'Новость #41'),
                        ('https://t.me/TopRussiaBrand/340', 'История восхождений и экспедиций', 'Новость #42'),
                        ('https://t.me/TopRussiaBrand/341', 'История восхождений и экспедиций', 'Новость #43'),
                        ('https://t.me/TopRussiaBrand/342', 'История восхождений и экспедиций', 'Новость #44'),
                        ('https://t.me/TopRussiaBrand/343', 'История восхождений и экспедиций', 'Новость #45'),
                        ('https://t.me/TopRussiaBrand/346', 'Культурное и историческое значение горы', 'Новость #46'),
                        ('https://t.me/TopRussiaBrand/347', 'Природа и экология Эльбруса', 'Новость #47'),
                        ('https://t.me/TopRussiaBrand/348?single', 'Культурное и историческое значение горы', 'Новость #48'),
                        ('https://t.me/TopRussiaBrand/351', 'История восхождений и экспедиций', 'Новость #49'),
                        ('https://t.me/TopRussiaBrand/352', 'Культурное и историческое значение горы', 'Новость #50'),
                        ('https://t.me/TopRussiaBrand/353', 'История восхождений и экспедиций', 'Новость #51'),
                        ('https://t.me/TopRussiaBrand/354', 'История восхождений и экспедиций', 'Новость #52'),
                        ('https://t.me/TopRussiaBrand/355', 'История восхождений и экспедиций', 'Новость #53'),
                        ('https://t.me/TopRussiaBrand/356', 'История восхождений и экспедиций', 'Новость #54'),
                        ('https://t.me/TopRussiaBrand/357', 'Природа и экология Эльбруса', 'Новость #55'),
                        ('https://t.me/TopRussiaBrand/358', 'Культурное и историческое значение горы', 'Новость #56'),
                        ('https://t.me/TopRussiaBrand/359', 'Культурное и историческое значение горы', 'Новость #57'),
                        ('https://t.me/TopRussiaBrand/360', 'История восхождений и экспедиций', 'Новость #58'),
                        ('https://t.me/TopRussiaBrand/361', 'История восхождений и экспедиций', 'Новость #59'),
                        ('https://t.me/TopRussiaBrand/362', 'Культурное и историческое значение горы', 'Новость #60'),
                        ('https://t.me/TopRussiaBrand/363', 'Природа и экология Эльбруса', 'Новость #61'),
                        ('https://t.me/TopRussiaBrand/364', 'История восхождений и экспедиций', 'Новость #62'),
                        ('https://t.me/TopRussiaBrand/365', 'История восхождений и экспедиций', 'Новость #63'),
                        ('https://t.me/TopRussiaBrand/366', 'Культурное и историческое значение горы', 'Новость #64'),
                        ('https://t.me/TopRussiaBrand/367', 'Природа и экология Эльбруса', 'Новость #65'),
                        ('https://t.me/TopRussiaBrand/368', 'Культурное и историческое значение горы', 'Новость #66'),
                        ('https://t.me/TopRussiaBrand/369', 'Культурное и историческое значение горы', 'Новость #67'),
                        ('https://t.me/TopRussiaBrand/370', 'История восхождений и экспедиций', 'Новость #68'),
                        ('https://t.me/TopRussiaBrand/371', 'История восхождений и экспедиций', 'Новость #69'),
                        ('https://t.me/TopRussiaBrand/372', 'История восхождений и экспедиций', 'Новость #70'),
                        ('https://t.me/TopRussiaBrand/373', 'История восхождений и экспедиций', 'Новость #71'),
                        ('https://t.me/TopRussiaBrand/374', 'История восхождений и экспедиций', 'Новость #72'),
                        ('https://t.me/TopRussiaBrand/375', 'Культурное и историческое значение горы', 'Новость #73'),
                        ('https://t.me/TopRussiaBrand/376', 'Культурное и историческое значение горы', 'Новость #74'),
                        ('https://t.me/TopRussiaBrand/377', 'Культурное и историческое значение горы', 'Новость #75'),
                        ('https://t.me/TopRussiaBrand/378', 'Культурное и историческое значение горы', 'Новость #76'),
                        ('https://t.me/TopRussiaBrand/380', 'Культурное и историческое значение горы', 'Новость #77'),
                        ('https://t.me/TopRussiaBrand/381', 'Культурное и историческое значение горы', 'Новость #78'),
                        ('https://t.me/TopRussiaBrand/382?single', 'Культурное и историческое значение горы', 'Новость #79'),
                        ('https://t.me/TopRussiaBrand/384', 'Культурное и историческое значение горы', 'Новость #80'),
                        ('https://t.me/TopRussiaBrand/386', 'Культурное и историческое значение горы', 'Новость #81'),
                        ('https://t.me/TopRussiaBrand/387', 'Культурное и историческое значение горы', 'Новость #82'),
                        ('https://t.me/TopRussiaBrand/388', 'История восхождений и экспедиций', 'Новость #83'),
                        ('https://t.me/TopRussiaBrand/389', 'История восхождений и экспедиций', 'Новость #84'),
                        ('https://t.me/TopRussiaBrand/390', 'История восхождений и экспедиций', 'Новость #85'),
                        ('https://t.me/TopRussiaBrand/392', 'История восхождений и экспедиций', 'Новость #86'),
                        ('https://t.me/TopRussiaBrand/393', 'История восхождений и экспедиций', 'Новость #87'),
                        ('https://t.me/TopRussiaBrand/394', 'Культурное и историческое значение горы', 'Новость #88'),
                        ('https://t.me/TopRussiaBrand/395', 'История восхождений и экспедиций', 'Новость #89'),
                        ('https://t.me/TopRussiaBrand/396', 'Природа и экология Эльбруса', 'Новость #90'),
                        ('https://t.me/TopRussiaBrand/397', 'Культурное и историческое значение горы', 'Новость #91'),
                        ('https://t.me/TopRussiaBrand/398', 'Природа и экология Эльбруса', 'Новость #92'),
                        ('https://t.me/TopRussiaBrand/399', 'Культурное и историческое значение горы', 'Новость #93'),
                        ('https://t.me/TopRussiaBrand/400', 'Культурное и историческое значение горы', 'Новость #94'),
                        ('https://t.me/TopRussiaBrand/401', 'Культурное и историческое значение горы', 'Новость #95'),
                        ('https://t.me/TopRussiaBrand/402', 'Культурное и историческое значение горы', 'Новость #96'),
                        ('https://t.me/TopRussiaBrand/403', 'Культурное и историческое значение горы', 'Новость #97'),
                        ('https://t.me/TopRussiaBrand/404', 'Природа и экология Эльбруса', 'Новость #98'),
                        ('https://t.me/TopRussiaBrand/405?single', 'Культурное и историческое значение горы', 'Новость #99'),
                        ('https://t.me/TopRussiaBrand/407', 'История восхождений и экспедиций', 'Новость #100'),
                        ('https://t.me/TopRussiaBrand/408', 'История восхождений и экспедиций', 'Новость #101'),
                        ('https://t.me/TopRussiaBrand/409', 'Культурное и историческое значение горы', 'Новость #102'),
                        ('https://t.me/TopRussiaBrand/410', 'История восхождений и экспедиций', 'Новость #103'),
                        ('https://t.me/TopRussiaBrand/412', 'История восхождений и экспедиций', 'Новость #104'),
                        ('https://t.me/TopRussiaBrand/413', 'Природа и экология Эльбруса', 'Новость #105'),
                        ('https://t.me/TopRussiaBrand/414', 'История восхождений и экспедиций', 'Новость #106'),
                        ('https://t.me/TopRussiaBrand/415', 'История восхождений и экспедиций', 'Новость #107'),
                        ('https://t.me/TopRussiaBrand/416', 'Культурное и историческое значение горы', 'Новость #108'),
                        ('https://t.me/TopRussiaBrand/417', 'Культурное и историческое значение горы', 'Новость #109'),
                        ('https://t.me/TopRussiaBrand/418', 'История восхождений и экспедиций', 'Новость #110'),
                        ('https://t.me/TopRussiaBrand/423', 'История восхождений и экспедиций', 'Новость #111'),
                        ('https://t.me/TopRussiaBrand/424', 'Культурное и историческое значение горы', 'Новость #112'),
                        ('https://t.me/TopRussiaBrand/426', 'Природа и экология Эльбруса', 'Новость #113'),
                        ('https://t.me/TopRussiaBrand/427', 'Культурное и историческое значение горы', 'Новость #114'),
                        ('https://t.me/TopRussiaBrand/428', 'История восхождений и экспедиций', 'Новость #115'),
                        ('https://t.me/TopRussiaBrand/429', 'Культурное и историческое значение горы', 'Новость #116'),
                        ('https://t.me/TopRussiaBrand/430', 'Культурное и историческое значение горы', 'Новость #117'),
                        ('https://t.me/TopRussiaBrand/431', 'Культурное и историческое значение горы', 'Новость #118'),
                        ('https://t.me/TopRussiaBrand/432', 'Культурное и историческое значение горы', 'Новость #119'),
                        ('https://t.me/TopRussiaBrand/433', 'Культурное и историческое значение горы', 'Новость #120'),
                        ('https://t.me/TopRussiaBrand/435', 'История восхождений и экспедиций', 'Новость #121'),
                        ('https://t.me/TopRussiaBrand/436', 'Культурное и историческое значение горы', 'Новость #122'),
                        ('https://t.me/TopRussiaBrand/437', 'Культурное и историческое значение горы', 'Новость #123'),
                        ('https://t.me/TopRussiaBrand/438', 'Культурное и историческое значение горы', 'Новость #124'),
                        ('https://t.me/TopRussiaBrand/439', 'Культурное и историческое значение горы', 'Новость #125'),
                        ('https://t.me/TopRussiaBrand/440', 'История восхождений и экспедиций', 'Новость #126'),
                        ('https://t.me/TopRussiaBrand/442', 'Культурное и историческое значение горы', 'Новость #127'),
                        ('https://t.me/TopRussiaBrand/443', 'Культурное и историческое значение горы', 'Новость #128'),
                        ('https://t.me/TopRussiaBrand/444', 'Культурное и историческое значение горы', 'Новость #129'),
                        ('https://t.me/TopRussiaBrand/445', 'Культурное и историческое значение горы', 'Новость #130'),
                        ('https://t.me/TopRussiaBrand/446', 'Культурное и историческое значение горы', 'Новость #131'),
                        ('https://t.me/TopRussiaBrand/447', 'Культурное и историческое значение горы', 'Новость #132'),
                        ('https://t.me/TopRussiaBrand/448', 'Культурное и историческое значение горы', 'Новость #133'),
                        ('https://t.me/TopRussiaBrand/449', 'Культурное и историческое значение горы', 'Новость #134'),
                        ('https://t.me/TopRussiaBrand/450', 'История восхождений и экспедиций', 'Новость #135'),
                        ('https://t.me/TopRussiaBrand/451', 'История восхождений и экспедиций', 'Новость #136'),
                        ('https://t.me/TopRussiaBrand/452', 'История восхождений и экспедиций', 'Новость #137'),
                        ('https://t.me/TopRussiaBrand/453', 'История восхождений и экспедиций', 'Новость #138'),
                        ('https://t.me/TopRussiaBrand/454', 'Культурное и историческое значение горы', 'Новость #139'),
                        ('https://t.me/TopRussiaBrand/455', 'История восхождений и экспедиций', 'Новость #140'),
                        ('https://t.me/TopRussiaBrand/456', 'Природа и экология Эльбруса', 'Новость #141'),
                        ('https://t.me/TopRussiaBrand/458', 'Природа и экология Эльбруса', 'Новость #142'),
                        ('https://t.me/TopRussiaBrand/459', 'История восхождений и экспедиций', 'Новость #143'),
                        ('https://t.me/TopRussiaBrand/460', 'История восхождений и экспедиций', 'Новость #144'),
                        ('https://t.me/TopRussiaBrand/461', 'Культурное и историческое значение горы', 'Новость #145'),
                        ('https://t.me/TopRussiaBrand/462', 'Культурное и историческое значение горы', 'Новость #146'),
                        ('https://t.me/TopRussiaBrand/463', 'Культурное и историческое значение горы', 'Новость #147'),
                        ('https://t.me/TopRussiaBrand/467', 'Культурное и историческое значение горы', 'Новость #148'),
                        ('https://t.me/TopRussiaBrand/468', 'История восхождений и экспедиций', 'Новость #149'),
                        ('https://t.me/TopRussiaBrand/469', 'Культурное и историческое значение горы', 'Новость #150'),
                        ('https://t.me/TopRussiaBrand/470', 'Современные достижения связанные с Эльбрусом', 'Новость #151'),
                        ('https://t.me/TopRussiaBrand/471', 'Современные достижения связанные с Эльбрусом', 'Новость #152'),
                        ('https://t.me/TopRussiaBrand/472', 'Современные достижения связанные с Эльбрусом', 'Новость #153'),
                        ('https://t.me/TopRussiaBrand/474', 'Современные достижения связанные с Эльбрусом', 'Новость #154'),
                        ('https://t.me/TopRussiaBrand/475', 'Современные достижения связанные с Эльбрусом', 'Новость #155'),
                        ('https://t.me/TopRussiaBrand/476', 'Культурное и историческое значение горы', 'Новость #156'),
                        ('https://t.me/TopRussiaBrand/477', 'Современные достижения связанные с Эльбрусом', 'Новость #157'),
                        ('https://t.me/TopRussiaBrand/478', 'Современные достижения связанные с Эльбрусом', 'Новость #158'),
                        ('https://t.me/TopRussiaBrand/479', 'Современные достижения связанные с Эльбрусом', 'Новость #159'),
                        ('https://t.me/TopRussiaBrand/480', 'Современные достижения связанные с Эльбрусом', 'Новость #160'),
                        ('https://t.me/TopRussiaBrand/481', 'Современные достижения связанные с Эльбрусом', 'Новость #161'),
                        ('https://t.me/TopRussiaBrand/482', 'Современные достижения связанные с Эльбрусом', 'Новость #162'),
                        ('https://t.me/TopRussiaBrand/483', 'Современные достижения связанные с Эльбрусом', 'Новость #163'),
                        ('https://t.me/TopRussiaBrand/484', 'Современные достижения связанные с Эльбрусом', 'Новость #164'),
                        ('https://t.me/TopRussiaBrand/485', 'Современные достижения связанные с Эльбрусом', 'Новость #165'),
                        ('https://t.me/TopRussiaBrand/488', 'История восхождений и экспедиций', 'Новость #166'),
                        ('https://t.me/TopRussiaBrand/489', 'Современные достижения связанные с Эльбрусом', 'Новость #167'),
                        ('https://t.me/TopRussiaBrand/490', 'Современные достижения связанные с Эльбрусом', 'Новость #168'),
                        ('https://t.me/TopRussiaBrand/491', 'История восхождений и экспедиций', 'Новость #169'),
                        ('https://t.me/TopRussiaBrand/492', 'Современные достижения связанные с Эльбрусом', 'Новость #170'),
                        ('https://t.me/TopRussiaBrand/493', 'Современные достижения связанные с Эльбрусом', 'Новость #171'),
                        ('https://t.me/TopRussiaBrand/494', 'Современные достижения связанные с Эльбрусом', 'Новость #172'),
                        ('https://t.me/TopRussiaBrand/495', 'Современные достижения связанные с Эльбрусом', 'Новость #173'),
                        ('https://t.me/TopRussiaBrand/496', 'Современные достижения связанные с Эльбрусом', 'Новость #174'),
                        ('https://t.me/TopRussiaBrand/497', 'Современные достижения связанные с Эльбрусом', 'Новость #175'),
                        ('https://t.me/TopRussiaBrand/498', 'История восхождений и экспедиций', 'Новость #176'),
                        ('https://t.me/TopRussiaBrand/499', 'Современные достижения связанные с Эльбрусом', 'Новость #177'),
                        ('https://t.me/TopRussiaBrand/500', 'Современные достижения связанные с Эльбрусом', 'Новость #178'),
                        ('https://t.me/TopRussiaBrand/501', 'Современные достижения связанные с Эльбрусом', 'Новость #179'),
                        ('https://t.me/TopRussiaBrand/502', 'История восхождений и экспедиций', 'Новость #180'),
                        ('https://t.me/TopRussiaBrand/503', 'Современные достижения связанные с Эльбрусом', 'Новость #181'),
                        ('https://t.me/TopRussiaBrand/504', 'Современные достижения связанные с Эльбрусом', 'Новость #182'),
                        ('https://t.me/TopRussiaBrand/505', 'Культурное и историческое значение горы', 'Новость #183'),
                        ('https://t.me/TopRussiaBrand/506', 'Современные достижения связанные с Эльбрусом', 'Новость #184'),
                        ('https://t.me/TopRussiaBrand/507', 'Современные достижения связанные с Эльбрусом', 'Новость #185'),
                        ('https://t.me/TopRussiaBrand/508', 'Современные достижения связанные с Эльбрусом', 'Новость #186'),
                        ('https://t.me/TopRussiaBrand/509', 'Современные достижения связанные с Эльбрусом', 'Новость #187'),
                        ('https://t.me/TopRussiaBrand/510', 'Современные достижения связанные с Эльбрусом', 'Новость #188'),
                        ('https://t.me/TopRussiaBrand/511', 'Современные достижения связанные с Эльбрусом', 'Новость #189'),
                        ('https://t.me/TopRussiaBrand/512', 'Культурное и историческое значение горы', 'Новость #190'),
                        ('https://t.me/TopRussiaBrand/513', 'Природа и экология Эльбруса', 'Новость #191'),
                        ('https://t.me/TopRussiaBrand/514', 'Современные достижения связанные с Эльбрусом', 'Новость #192'),
                        ('https://t.me/TopRussiaBrand/515', 'Природа и экология Эльбруса', 'Новость #193'),
                        ('https://t.me/TopRussiaBrand/517', 'Современные достижения связанные с Эльбрусом', 'Новость #194'),
                        ('https://t.me/TopRussiaBrand/519', 'Современные достижения связанные с Эльбрусом', 'Новость #195'),
                        ('https://t.me/TopRussiaBrand/520', 'Современные достижения связанные с Эльбрусом', 'Новость #196'),
                        ('https://t.me/TopRussiaBrand/521', 'Современные достижения связанные с Эльбрусом', 'Новость #197'),
                        ('https://t.me/TopRussiaBrand/524', 'Культурное и историческое значение горы', 'Новость #198'),
                        ('https://t.me/TopRussiaBrand/525', 'Современные достижения связанные с Эльбрусом', 'Новость #199'),
                        ('https://t.me/TopRussiaBrand/527', 'Культурное и историческое значение горы', 'Новость #200'),
                        ('https://t.me/TopRussiaBrand/528', 'Культурное и историческое значение горы', 'Новость #201'),
                        ('https://t.me/TopRussiaBrand/529', 'Культурное и историческое значение горы', 'Новость #202'),
                        ('https://t.me/TopRussiaBrand/532', 'Природа и экология Эльбруса', 'Новость #203'),
                        ('https://t.me/TopRussiaBrand/533', 'Культурное и историческое значение горы', 'Новость #204'),
                        ('https://t.me/TopRussiaBrand/534', 'Современные достижения связанные с Эльбрусом', 'Новость #205'),
                        ('https://t.me/TopRussiaBrand/536', 'Современные достижения связанные с Эльбрусом', 'Новость #206'),
                        ('https://t.me/TopRussiaBrand/538', 'Природа и экология Эльбруса', 'Новость #207'),
                        ('https://t.me/TopRussiaBrand/542', 'Современные достижения связанные с Эльбрусом', 'Новость #208'),
                        ('https://t.me/TopRussiaBrand/543', 'Современные достижения связанные с Эльбрусом', 'Новость #209'),
                        ('https://t.me/TopRussiaBrand/549', 'Современные достижения связанные с Эльбрусом', 'Новость #210'),
                        ('https://t.me/TopRussiaBrand/551', 'Культурное и историческое значение горы', 'Новость #211'),
                        ('https://t.me/TopRussiaBrand/552', 'История восхождений и экспедиций', 'Новость #212'),
                        ('https://t.me/TopRussiaBrand/553', 'Природа и экология Эльбруса', 'Новость #213'),
                        ('https://t.me/TopRussiaBrand/554', 'Природа и экология Эльбруса', 'Новость #214'),
                        ('https://t.me/TopRussiaBrand/555', 'Культурное и историческое значение горы', 'Новость #215'),
                        ('https://t.me/TopRussiaBrand/556', 'Культурное и историческое значение горы', 'Новость #216'),
                        ('https://t.me/TopRussiaBrand/557', 'Культурное и историческое значение горы', 'Новость #217'),
                        ('https://t.me/TopRussiaBrand/558', 'История восхождений и экспедиций', 'Новость #218'),
                        ('https://t.me/TopRussiaBrand/562', 'Современные достижения связанные с Эльбрусом', 'Новость #219'),
                        ('https://t.me/TopRussiaBrand/563', 'История восхождений и экспедиций', 'Новость #220'),
                        ('https://t.me/TopRussiaBrand/568', 'Современные достижения связанные с Эльбрусом', 'Новость #221'),
                        ('https://t.me/TopRussiaBrand/569', 'Культурное и историческое значение горы', 'Новость #222'),
                        ('https://t.me/TopRussiaBrand/570', 'Современные достижения связанные с Эльбрусом', 'Новость #223'),
                        ('https://t.me/TopRussiaBrand/571?single', 'Современные достижения связанные с Эльбрусом', 'Новость #224'),
                        ('https://t.me/TopRussiaBrand/575', 'Современные достижения связанные с Эльбрусом', 'Новость #225'),
                        ('https://t.me/TopRussiaBrand/576', 'Современные достижения связанные с Эльбрусом', 'Новость #226'),
                        ('https://t.me/TopRussiaBrand/577', 'Природа и экология Эльбруса', 'Новость #227'),
                        ('https://t.me/TopRussiaBrand/578', 'Природа и экология Эльбруса', 'Новость #228'),
                        ('https://t.me/TopRussiaBrand/579', 'Современные достижения связанные с Эльбрусом', 'Новость #229'),
                        ('https://t.me/TopRussiaBrand/580', 'Современные достижения связанные с Эльбрусом', 'Новость #230'),
                        ('https://t.me/TopRussiaBrand/581', 'Современные достижения связанные с Эльбрусом', 'Новость #231'),
                        ('https://t.me/TopRussiaBrand/582', 'Современные достижения связанные с Эльбрусом', 'Новость #232'),
                        ('https://t.me/TopRussiaBrand/583', 'Современные достижения связанные с Эльбрусом', 'Новость #233'),
                        ('https://t.me/TopRussiaBrand/584', 'Современные достижения связанные с Эльбрусом', 'Новость #234'),
                        ('https://t.me/TopRussiaBrand/585', 'Современные достижения связанные с Эльбрусом', 'Новость #235'),
                        ('https://t.me/TopRussiaBrand/586', 'Природа и экология Эльбруса', 'Новость #236'),
                        ('https://t.me/TopRussiaBrand/587', 'Современные достижения связанные с Эльбрусом', 'Новость #237'),
                        ('https://t.me/TopRussiaBrand/588', 'Современные достижения связанные с Эльбрусом', 'Новость #238'),
                        ('https://t.me/TopRussiaBrand/589', 'Современные достижения связанные с Эльбрусом', 'Новость #239'),
                        ('https://t.me/TopRussiaBrand/590', 'История восхождений и экспедиций', 'Новость #240'),
                        ('https://t.me/TopRussiaBrand/591', 'Культурное и историческое значение горы', 'Новость #241'),
                        ('https://t.me/TopRussiaBrand/593', 'Современные достижения связанные с Эльбрусом', 'Новость #242'),
                        ('https://t.me/TopRussiaBrand/597', 'Культурное и историческое значение горы', 'Новость #243'),
                        ('https://t.me/TopRussiaBrand/598', 'Культурное и историческое значение горы', 'Новость #244'),
                        ('https://t.me/TopRussiaBrand/599', 'Культурное и историческое значение горы', 'Новость #245'),
                        ('https://t.me/TopRussiaBrand/600', 'Современные достижения связанные с Эльбрусом', 'Новость #246'),
                        ('https://t.me/TopRussiaBrand/601', 'Современные достижения связанные с Эльбрусом', 'Новость #247'),
                        ('https://t.me/TopRussiaBrand/602', 'Культурное и историческое значение горы', 'Новость #248'),
                        ('https://t.me/TopRussiaBrand/603', 'Культурное и историческое значение горы', 'Новость #249'),
                        ('https://t.me/TopRussiaBrand/604', 'Современные достижения связанные с Эльбрусом', 'Новость #250')
                                                    ]

                for telegram_url, news_type, title in news_data:
                    # Убедитесь, что у вас есть UNIQUE constraint на telegram_url в вашей таблице news,
                    # чтобы ON CONFLICT DO NOTHING работал корректно.
                    await conn.execute('''
                        INSERT INTO news (telegram_url, news_type, title)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (telegram_url) DO NOTHING;
                    ''', telegram_url, news_type, title)
                
                logger.info("Тестовые новости добавлены (если их было меньше 10).")
            else:
                logger.info("Тестовые новости уже существуют в достаточном количестве.")


    def generate_qr(self, qr_id: str):
        """Генерирует QR-код для поста"""
        qr_content_data = f"mountain:{qr_id}"
        encoded_qr_data = quote_plus(qr_content_data)
        full_qr_link = f"https://t.me/{self.bot_username}?start={encoded_qr_data}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(full_qr_link)
        qr.make()
        img = qr.make_image(fill_color="black", back_color="white")
        filename = f"qr_{qr_id}.png"
        img.save(filename)
        logger.info(f"QR-код для '{qr_id}' сгенерирован: {full_qr_link}")
        return filename, full_qr_link

    async def log_user_interaction(self, user, interaction_type, qr_id=None, post_id=None):
        """Логирование взаимодействий пользователя"""
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO user_interactions 
                    (user_id, username, first_name, last_name, qr_id, post_id, interaction_type)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''', user.id, user.username, user.first_name, user.last_name, qr_id, post_id, interaction_type)
        except Exception as e:
            logger.error(f"Ошибка логирования взаимодействия: {e}")

    # --- Методы для работы с БД (ОБНОВЛЕНО!) ---
    async def get_post_by_qr_id(self, qr_id: str):
        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM posts WHERE qr_id = $1 AND is_active = TRUE", qr_id)

    async def get_news_by_type(self, news_type: str, offset: int = 0, limit: int = NEWS_PER_PAGE):
        """
        Получает новости по типу с заданным смещением и лимитом.
        Возвращает список новостей и общее количество новостей для этой категории.
        """
        try:
            async with self.db.pool.acquire() as conn:
                news = await conn.fetch(
                    "SELECT telegram_url, news_type, title FROM news WHERE news_type = $1 ORDER BY id DESC OFFSET $2 LIMIT $3",
                    news_type, offset, limit
                )
                total_news = await conn.fetchval(
                    "SELECT COUNT(*) FROM news WHERE news_type = $1",
                    news_type
                )
                return news, total_news
        except Exception as e:
            logger.error(f"Ошибка при получении новостей по типу: {e}")
            return [], 0 # Возвращаем пустой список и 0 при ошибке

    async def get_all_news(self, offset: int = 0, limit: int = 20): # Добавляем offset и делаем limit по умолчанию
        """
        Получает все новости с заданным смещением и лимитом.
        Возвращает список новостей и общее количество всех новостей.
        """
        try:
            async with self.db.pool.acquire() as conn:
                news = await conn.fetch("SELECT telegram_url, news_type, title FROM news ORDER BY id DESC OFFSET $1 LIMIT $2", offset, limit)
                total_news = await conn.fetchval("SELECT COUNT(*) FROM news")
                return news, total_news
        except Exception as e:
            logger.error(f"Ошибка при получении всех новостей: {e}")
            return [], 0


    # --- Создание кнопок ---
    def create_main_menu_markup(self):
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 Общий чат", url="https://t.me/topofrussia"),
                InlineKeyboardButton(text="📢 Наш канал", url="https://t.me/TopRussiaBrand")
            ],
            [
                InlineKeyboardButton(text="📸 Фотомарафон", url="https://t.me/TopRussiaBrand/618"), # Закомментировано по запросу
                InlineKeyboardButton(text="📰 Новости", callback_data="show_news")
            ],
            [
                InlineKeyboardButton(text="🌟 Официальный сайт", url="https://xn--80adjmba6ajodma8f.xn--p1ai/")
            ]
        ])

    def create_post_markup(self, post_id):
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 Обсудить в чате", url="https://t.me/topofrussia"),
                InlineKeyboardButton(text="📢 Больше новостей", url="https://t.me/TopRussiaBrand")
            ],
            [
                #InlineKeyboardButton(text="➡️ Следующий пост", callback_data=f"next_{post_id}"),
                #InlineKeyboardButton(text="🔍 Найти похожее", callback_data="search_posts")
            ],
            [
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ]
        ])

    # --- Обработчики команд ---
    async def start_command(self, message: Message):
        """Обработчик команды /start с поддержкой QR-параметров"""
        args = message.text.split()
        
        if len(args) > 1:
            qr_url = unquote(args[1])
            await self.handle_qr_url(message, qr_url)
        else:
            msg = (
                "🏔️ <b>Добро пожаловать в бот сообщества \"Вершина России\"!</b>\n\n"
                "Этот бот поможет вам узнать больше о горах России через QR-коды "
                "и получить актуальные новости о восхождениях и экспедициях.\n\n"
                "🔍 <b>Возможности:</b>\n"
                "• Сканирование QR-кодов для получения информации о горах\n"
                "• Поиск новостей и статей\n"
                "• Доступ к сообществу любителей гор\n\n"
                "📱 <b>Команды:</b>\n"
                "/start - Главное меню\n"
                "/news - Последние новости\n"
                "/help - Подробная справка"
            )
            
            await message.answer(msg, reply_markup=self.create_main_menu_markup(), parse_mode=ParseMode.HTML)

    async def help_command(self, message: Message):
        msg = (
            "📖 <b>Справка по боту \"Вершины России\"</b>\n\n"
            "🔍 <b>Основные функции:</b>\n"
            "• Получение информации о горах через QR-коды\n"
            "• Поиск новостей и статей о восхождениях\n"
            "• Доступ к сообществу любителей гор\n\n"
            "🎯 <b>Как работать с QR-кодами:</b>\n"
            "1. Найдите QR-код рядом с информацией о горе\n"
            "2. Отсканируйте его камерой телефона\n"
            "3. Нажмите на ссылку - откроется этот бот\n"
            "4. Получите подробную информацию\n\n"
            "💬 <b>Сообщество:</b>\n"
            "• Общий чат: https://t.me/topofrussia\n"
            "• Канал новостей: https://t.me/TopRussiaBrand\n"
            "• Официальный сайт: https://xn--80adjmba6ajodma8f.xn--p1ai/"
        )
        await message.answer(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    async def news_command(self, message: Message, state: FSMContext):
        """Показать последние новости (категории)"""
        await self.show_news_categories(message, state)

    async def generate_qr_command(self, message: Message):
        """Команда для генерации QR-кода (только для админов)"""
        if not self.admin_id or str(message.from_user.id) != self.admin_id:
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
            filename, qr_link = self.generate_qr(qr_id)
            
            with open(filename, 'rb') as qr_file:
                await message.answer_photo(
                    photo=qr_file,
                    caption=(
                        f"📱 <b>QR-код для: {post['title']}</b>\n\n"
                        f"🔗 Ссылка: <code>{qr_link}</code>\n\n"
                        f"При сканировании пользователи попадут к информации о {post['title']}."
                    ),
                    parse_mode=ParseMode.HTML
                )
            
            os.remove(filename)
            
        except Exception as e:
            logger.error(f"Ошибка генерации QR: {e}")
            await message.answer(f"❌ Ошибка при генерации QR-кода: {e}")

    # --- Обработчики QR и постов ---
    async def handle_qr_url(self, message: types.Message, qr_data: str):
        """Обработка данных из QR-кода"""
        try:
            if qr_data.startswith('mountain:'):
                qr_id = qr_data.split(':', 1)[1]
                post = await self.get_post_by_qr_id(qr_id)
            
                if post:
                    await self.log_user_interaction(message.from_user, 'qr_scan', qr_id=qr_id, post_id=post['id'])
                    
                    welcome_msg = (
                        f"🏔️ <b>Добро пожаловать!</b>\n\n"
                        f"Вы отсканировали QR-код!\n"
                        f"📍 Информация о: <b>{post['title']}</b>\n\n"
                        f"Присоединяйтесь к нашему сообществу! 👇"
                    )
                    
                    await message.answer(welcome_msg, reply_markup=self.create_main_menu_markup(), parse_mode=ParseMode.HTML)
                    await asyncio.sleep(1) # Небольшая задержка, чтобы сообщения не слипались
                    await self.show_post(message, post)
                else:
                    await self.log_user_interaction(message.from_user, 'qr_scan_not_found', qr_id=qr_id) # Логируем, что QR не найден
                    await message.answer(
                        "🚫 Информация по этому QR-коду не найдена.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                        ])
                    )
            else:
                await message.answer(
                    "👋 Привет! Вы перешли по ссылке в бота сообщества Вершина России!",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                    ])
                )
            
        except Exception as e:
            logger.error(f"QR Error: {e}")
            await message.answer(
                "⚠️ Произошла ошибка при обработке QR-кода.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ])
            )

    async def show_post(self, message: types.Message, post):
        """Показываем пост с кнопками действий"""
        try:
            await message.answer_photo(
                photo=post['image_url'],
                caption=f"<b>{post['title']}</b>\n\n{post['description']}",
                reply_markup=self.create_post_markup(post['id']),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            # Отправляем сообщение без фото, если фото не загрузилось
            await message.answer(
                f"<b>{post['title']}</b>\n\n{post['description']}\n\n🖼️ Изображение: {post['image_url']}",
                reply_markup=self.create_post_markup(post['id']),
                parse_mode=ParseMode.HTML
            )

    # --- Обработчики новостей (ОБНОВЛЕНО!) ---
    async def show_news_categories(self, message: types.Message, state: FSMContext):
        """Показать категории новостей"""
        try:
            async with self.db.pool.acquire() as conn:
                categories_db = await conn.fetch(
                    "SELECT DISTINCT news_type, COUNT(*) as count FROM news GROUP BY news_type ORDER BY count DESC"
                )

            if not categories_db:
                await message.answer("📰 Новости не найдены.")
                return

            builder = InlineKeyboardBuilder()
            # Сохраняем маппинг в FSMContext
            category_slug_map = {} 

            for category in categories_db:
                category_hash = hashlib.md5(category['news_type'].encode('utf-8')).hexdigest()[:16] 
                category_slug_map[category_hash] = category['news_type']

                builder.button(
                    text=f"📂 {category['news_type']} ({category['count']})",
                    callback_data=f"news_category:{category_hash}" # Используем хеш и новый префикс
                )
            
            builder.adjust(1) # По одной кнопке в ряд
            await state.update_data(category_slug_map=category_slug_map) # Сохраняем map в FSMContext

            builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
            
            await message.answer(
                "📰 <b>Категории новостей:</b>\n\nВыберите интересующую категорию:",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"Ошибка в show_news_categories: {e}")
            await message.answer("Произошла ошибка при загрузке категорий новостей.")

    # Эта функция теперь будет отправлять пагинированные новости
    async def send_paginated_news(self, message_or_callback_query: Message | CallbackQuery, news_type: str, offset: int):
        """
        Отправляет страницу новостей с кнопками навигации.
        Используется как для первого показа, так и для навигации.
        """

        is_callback = isinstance(message_or_callback_query, CallbackQuery)
        message = message_or_callback_query.message if is_callback else message_or_callback_query

    # Генерируем хэш для news_type, чтобы использовать его в callback_data
    # Это гарантирует, что callback_data останется короткой
        news_type_hash = hashlib.md5(news_type.encode('utf-8')).hexdigest()[:16]

        news_items, total_news = await self.db.get_news_by_type(news_type, offset, NEWS_PER_PAGE)

        if not news_items:
            if is_callback:
                await message_or_callback_query.answer("Новостей на этой странице больше нет.")
            else:
                await message.edit_text("Новостей в этой категории пока нет.", reply_markup=self.create_main_menu_markup(), parse_mode=ParseMode.HTML)
            return

        message_text = f"--- \n<b>{news_type}:</b>\n---\n"
        for i, item in enumerate(news_items):
            title = item.get('title', f"Новость #{item['id']}")
            message_text += f"{offset + i + 1}. <a href='{item['telegram_url']}'>{title}</a>\n"

        remaining_news = total_news - (offset + len(news_items))
        if remaining_news > 0:
            message_text += f"\n... и ещё {remaining_news} новостей"

        builder = InlineKeyboardBuilder()

    # Кнопка "Назад"
        if offset > 0:
        # Используем хэш в callback_data
            builder.button(text="⬅️ Назад", callback_data=f"news_nav:{news_type_hash}:{offset - NEWS_PER_PAGE}")

    # Кнопка "Вперёд"
        if offset + NEWS_PER_PAGE < total_news:
        # Используем хэш в callback_data
            builder.button(text="Вперёд ➡️", callback_data=f"news_nav:{news_type_hash}:{offset + NEWS_PER_PAGE}")

        if offset > 0 and offset + NEWS_PER_PAGE < total_news:
            builder.adjust(2)
        else:
            builder.adjust(1)

        builder.row(InlineKeyboardButton(text="◀️ В меню категорий", callback_data="show_categories_menu"))
        builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))

        try:
            if is_callback:
                await message.edit_text(
                    message_text,
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                await message_or_callback_query.answer()
            else:
                await message.answer(
                    message_text,
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке/редактировании пагинированных новостей: {e}")
            if is_callback:
                await message_or_callback_query.answer("Произошла ошибка при обновлении новостей.")


    # --- Обработчики поиска --- (Не менялись, так как запрос был только про кнопки навигации в новостях)
    async def process_search_keyword(self, message: types.Message, state: FSMContext, search_type: str):
        """Универсальная функция для поиска"""
        try:
            keyword = message.text.strip().lower()
            await state.clear() # Сбрасываем состояние после получения ключевого слова
            
            if search_type == "news":
                await self.search_news(message, keyword)
            else: # search_type == "posts"
                await self.search_posts(message, keyword)
                
        except asyncio.exceptions.CancelledError:
            logger.warning("Задача поиска отменена (например, из-за нового сообщения).")
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            await message.answer("Произошла ошибка при поиске.")
            await state.clear()

    async def search_news(self, message: types.Message, keyword: str):
        """Поиск новостей"""
        async with self.db.pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT telegram_url, news_type, title FROM news 
                WHERE LOWER(title) LIKE $1 OR LOWER(news_type) LIKE $1
                ORDER BY id DESC LIMIT 15
            """, f"%{keyword}%")
        
        if not results:
            await message.answer(
                f"🔍 По запросу '<b>{message.text}</b>' новости не найдены.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📰 Все категории", callback_data="show_news")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ]),
                parse_mode=ParseMode.HTML
            )
            return
        
        msg_parts = ["---", f"<b>Результаты поиска по запросу '{message.text}':</b>", "---", ""]
        
        display_limit = 5
        total_displayed = 0

        for i, result in enumerate(results):
            title = result.get('title', f"Новость #{result['id']}")
            msg_parts.append(f"{i + 1}. <a href='{result['telegram_url']}'>{title}</a>")
            total_displayed += 1
            if total_displayed >= display_limit and len(results) > display_limit:
                break

        if len(results) > display_limit:
            msg_parts.append(f"\n... и ещё {len(results) - display_limit} результатов")
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Новый поиск", callback_data="search_news"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ]
        ])
        
        await message.answer(
            "\n".join(msg_parts)[:4000],
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    async def search_posts(self, message: types.Message, keyword: str):
        """Поиск постов"""
        async with self.db.pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT * FROM posts 
                WHERE (LOWER(title) LIKE $1 OR LOWER(description) LIKE $1) AND is_active = TRUE
                ORDER BY id LIMIT 10
            """, f"%{keyword}%")
        
        if not results:
            await message.answer(
                f"🔍 По запросу '<b>{message.text}</b>' информация не найдена.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Новый поиск", callback_data="search_posts")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ]),
                parse_mode=ParseMode.HTML
            )
            return
        
        await self.log_user_interaction(message.from_user, 'search', qr_id=keyword) 
        
        if len(results) == 1:
            await self.show_post(message, results[0])
            return
        
        msg_parts = [f"🔍 <b>Найдено {len(results)} результатов:</b>\n"]
        buttons = []
        
        for i, post in enumerate(results, 1):
            msg_parts.append(f"{i}. <b>{post['title']}</b>\n   {post['description'][:100]}{'...' if len(post['description']) > 100 else ''}\n")
            buttons.append([
                InlineKeyboardButton(
                    text=f"📍 {post['title']}",
                    callback_data=f"show_post_{post['qr_id']}"
                )
            ])
        
        buttons.extend([
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer(
            "\n".join(msg_parts)[:4000],
            reply_markup=markup,
            parse_mode=ParseMode.HTML
        )
    from telegram import Update
    from telegram.ext import ContextTypes

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if args:
            if args[0] == 'from_channel':
                await update.message.reply_text("👋 Привет! Вы перешли по ссылке на канал Вершина России!")
            else:
                await update.message.reply_text(f"🔍 Получен параметр: {args[0]}")
        else:
            await update.message.reply_text("Привет! Просто /start без параметров.")

    async def get_channel_id(message: Message):
        await message.answer(f"ID чата: {message.chat.id}")
    
    # --- Обработчики сообщений ---
    async def text_message_handler(self, message: Message, state: FSMContext):
        """Обработка текстовых сообщений"""
        current_state = await state.get_state()
        logger.info(f"Получено текстовое сообщение: '{message.text}'. Текущее состояние: {current_state}")
        
        if current_state == SearchStates.waiting_for_news_keyword:
            await self.process_search_keyword(message, state, "news")
        elif current_state == SearchStates.waiting_for_post_keyword:
            await self.process_search_keyword(message, state, "posts")
        elif message.text.startswith('/'):
            return # Пропускаем, если это команда, чтобы она была обработана соответствующим хендлером
        elif f'https://t.me/{self.bot_username}?start=' in message.text:
            qr_url = message.text.split(f'https://t.me/{self.bot_username}?start=')[-1]
            await self.handle_qr_url(message, unquote(qr_url))
        else:
            await message.answer(
                "🤖 Добро пожаловать на канал Вершина России! Используйте кнопки меню для навигации.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ])
            )

    async def callback_handler(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработчик инлайн кнопок"""
        try:
            # Добавляем логирование для отладки
            logger.info(f"Получен callback: {callback.data}")
            
            if callback.data == "main_menu":
                await state.clear() # Очищаем состояние при возврате в главное меню
                await callback.message.edit_text( # Используем edit_text для обновления
                    "🏔️ Главное меню\nВыберите действие:",
                    reply_markup=self.create_main_menu_markup()
                )
                await callback.answer() # Отвечаем на коллбэк после редактирования
            
            elif callback.data == "show_news":
                # Это кнопка "Новости" из главного меню, ведет к категориям
                await self.show_news_categories(callback.message, state) 
                await callback.answer() 

            elif callback.data == "show_categories_menu":
                # Это кнопка "Назад в меню категорий" из просмотра новостей
                await self.show_news_categories(callback.message, state)
                await callback.answer()
            
            elif callback.data.startswith("news_category:"): # ОБНОВЛЕНО: новый префикс и двоеточие
                category_hash = callback.data.split(":")[1] # Парсим хеш
                logger.info(f"Парсим категорию, хеш: {category_hash}")
                current_data = await state.get_data()
                category_slug_map = current_data.get('category_slug_map', {})
                full_category_name = category_slug_map.get(category_hash)
                logger.info(f"Найдена категория: {full_category_name}")
                
                if full_category_name:
                    logger.info(f"Получена категория через хеш: {full_category_name}")
                    # При первом показе категории начинаем с offset=0
                    await self.send_paginated_news(callback, full_category_name, 0)
                else:
                    await callback.message.edit_text("К сожалению, категория не найдена. Возможно, данные устарели.")
                    await callback.answer("Категория не найдена.")
            
            elif callback.data.startswith("news_nav:"): # НОВЫЙ ОБРАБОТЧИК ДЛЯ НАВИГАЦИИ
                logger.info(f"Обрабатываем навигацию: {callback.data}")
                parts = callback.data.split(':')
                news_type_hash = parts[1]  # Исправлено: переименована переменная
                offset = int(parts[2])
                
                current_data = await state.get_data()
                category_slug_map = current_data.get('category_slug_map', {})
               
                # Разрешаем хэш обратно в полное название категории
                full_news_type = category_slug_map.get(news_type_hash)  # Исправлено: используется правильная переменная
                logger.info(f"Навигация: хеш={news_type_hash}, полное название={full_news_type}")

                if full_news_type:
                    # Передаем ПОЛНОЕ название категории в send_paginated_news
                    await self.send_paginated_news(callback, full_news_type, offset)
                else:
                    # Обрабатываем случай, когда карта категорий потеряна (например, бот перезапущен)
                    await callback.message.edit_text(
                        "К сожалению, категория новостей не найдена. "
                        "Пожалуйста, вернитесь в главное меню и попробуйте снова.",
                        reply_markup=self.create_main_menu_markup() # Предоставляем путь назад
                    )
                    await callback.answer("Категория не найдена.")
            
            elif callback.data == "search_news":
                await callback.message.edit_text( # Используем edit_text
                    "🔍 <b>Поиск новостей</b>\n\nВведите ключевое слово:",
                    parse_mode=ParseMode.HTML
                )
                await state.set_state(SearchStates.waiting_for_news_keyword)
                await callback.answer()

            elif callback.data.startswith("next_"):
                # Эта логика теперь не нужна, так как пагинация для новостей реализована через news_nav
                await callback.message.answer("Функция 'Следующий пост' в разработке.") # Заглушка
                await callback.answer()
            
            elif callback.data.startswith("show_post_"):
                qr_id = callback.data.replace("show_post_", "")
                post = await self.get_post_by_qr_id(qr_id)
                if post:
                    # Важно: если это редактирование существующего сообщения,
                    # то post['image_url'] должен быть Telegram file_id, а не URL.
                    # Если URL, то нужно отправить новое фото.
                    try:
                        await callback.message.edit_media(
                            media=types.InputMediaPhoto(media=post['image_url'], caption=f"<b>{post['title']}</b>\n\n{post['description']}", parse_mode=ParseMode.HTML),
                            reply_markup=self.create_post_markup(post['id'])
                        )
                    except Exception as media_e:
                        logger.warning(f"Не удалось отредактировать медиа, отправляю новое сообщение: {media_e}")
                        await callback.message.delete() # Удаляем старое сообщение, чтобы не было дублей
                        await self.show_post(callback.message, post)
                    
                    await callback.answer()
                else:
                    await callback.message.answer("Информация по этому посту не найдена.")
                    await callback.answer("Пост не найден.")
            
            # Обработка других коллбэков, если они есть
            else:
                logger.warning(f"Неизвестный callback: {callback.data}")
                await callback.answer("Неизвестное действие.")

        except asyncio.exceptions.CancelledError:
            logger.warning("Задача callback_handler отменена.")
        except Exception as e:
            logger.error(f"Ошибка в callback_handler: {e}")
            await callback.message.answer("Произошла ошибка при обработке запроса.")
            await state.clear()
            await callback.answer("Произошла ошибка.")


    async def on_startup(self):
        """Выполняется при запуске бота"""
        logger.info("Бот запускается...")
        try:
            await self.setup_database()
            logger.info("База данных подключена и инициализирована.")
        except Exception as e:
            logger.critical(f"Критическая ошибка при запуске: Не удалось подключиться к базе данных. {e}")
            exit(1)

    async def on_shutdown(self):
        """Выполняется при остановке бота"""
        logger.info("Бот останавливается...")
        if self.db:
            await self.db.disconnect() # Предполагаем, что у вашего класса Database есть метод disconnect()
            logger.info("Соединение с базой данных закрыто.")
        logger.info("Бот остановлен.")

    async def run(self):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения.")
            return

        self.bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()

        # Регистрация обработчиков команд
        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.help_command, Command("help"))
        self.dp.message.register(self.news_command, Command("news"))
        self.dp.message.register(self.generate_qr_command, Command("qr"))

        # Регистрация обработчика текстовых сообщений (после команд)
        self.dp.message.register(self.text_message_handler)

        self.dp.callback_query.register(self.callback_handler)
        self.dp.startup.register(self.on_startup)
        self.dp.shutdown.register(self.on_shutdown)
        # регистрация
        self.dp.message.register(self.on_join, F.new_chat_members)
        try:
            await self.dp.start_polling(self.bot)
        except asyncio.exceptions.CancelledError:
            logger.info("Запуск бота отменен.")
        except KeyboardInterrupt:
            logger.info("Бот остановлен пользователем (KeyboardInterrupt).")
        except Exception as e:
            logger.critical(f"Непредвиденная ошибка при запуске polling: {e}")
        finally:
            if self.bot:
                await self.bot.session.close() # Закрываем сессию бота

if __name__ == "__main__":
    bot_app = TelegramBot()
    
    try:
        asyncio.run(bot_app.run())
    except (asyncio.exceptions.CancelledError, KeyboardInterrupt):
        logger.info("Приложение завершило работу корректно.")
    except Exception as e:
        logger.critical(f"Критическая ошибка вне цикла polling: {e}")