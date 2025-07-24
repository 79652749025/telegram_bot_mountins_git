import asyncpg
import logging

class Database:
    def __init__(self, user='postgres', password='022020_mgddT', host='127.0.0.1', port=5432, database='vershinyrossii'):
        self.connection_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        self.pool = None

    async def connect(self):
        """Установка соединения с базой данных"""
        try:
            self.pool = await asyncpg.create_pool(self.connection_url)
            print(f"Успешное подключение к {self.connection_url}")
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            raise

    async def register_user(self, tg_user):
        """Регистрация пользователя в базе данных"""
        if not self.pool:
            await self.connect()
            
        async with self.pool.acquire() as connection:
            await connection.execute('''
                INSERT INTO users (telegram_id, username) 
                VALUES ($1, $2) 
                ON CONFLICT (telegram_id) DO NOTHING
            ''', tg_user.id, tg_user.username)

    async def close(self):
        """Закрытие соединения с базой данных"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            print("Соединение с базой данных закрыто")

    async def __aenter__(self):
        """Поддержка контекстного менеджера"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие при выходе из контекста"""
        await self.close()