from .models import News
from .db import async_session

async def add_news(title: str, content: str):
    async with async_session() as session:
        news_item = News(title=title, content=content)
        session.add(news_item)
        await session.commit()
async def get_news():
    async with async_session() as session:
        result = await session.execute("SELECT * FROM news")
        news_items = result.scalars().all()
        return news_items