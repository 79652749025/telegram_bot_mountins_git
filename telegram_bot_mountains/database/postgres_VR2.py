import asyncpg
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, user, password, database, host, port):
        self.user = user
        self.password = password
        self.database = database
        self.host = host
        self.port = port
        self.pool = None # Initialize pool to None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            user=self.user,
            password=self.password,
            database=self.database,
            host=self.host,
            port=self.port
        )
        logger.info("Пул подключений к БД создан.")

    async def disconnect(self):
        """Closes the database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed.") # Use logger for consistency
        else:
            logger.warning("No database connection pool to close.") # Use logger for consistency

    async def execute(self, query, *args):
        """Выполнение SQL запроса"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query, *args):
        """Получение записей из базы данных"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query, *args):
        """Получение одной записи из базы данных"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query, *args):
        """Получение одного значения из базы данных"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def get_news_by_type(self, news_type: str, offset: int, limit: int):
        """
        Получает новости по типу с пагинацией и общее количество новостей для этого типа.
        """
        async with self.pool.acquire() as conn:
            # Запрос для получения новостей для текущей страницы
            news_items = await conn.fetch("""
                SELECT id, title, telegram_url, news_type, created_at
                FROM news
                WHERE news_type = $1
                ORDER BY created_at DESC, id DESC -- Сортировка по дате создания и ID
                LIMIT $2 OFFSET $3
            """, news_type, limit, offset)

            # Запрос для получения общего количества новостей данного типа
            total_news = await conn.fetchval("""
                SELECT COUNT(*) FROM news WHERE news_type = $1
            """, news_type)

            return news_items, total_news

