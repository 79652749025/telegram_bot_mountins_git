from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger instance

router = Router()

class NewsForm(StatesGroup):
    title = State()
    content = State()

@router.message(Command("addnews"))
async def add_news_command(message: Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} started adding news.")
    await state.set_state(NewsForm.title)
    await message.answer("Введите заголовок новости:")

@router.message(NewsForm.title)
async def process_news_title(message: Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} entered news title: {message.text[:50]}...")
    await state.update_data(title=message.text)
    await state.set_state(NewsForm.content)
    await message.answer("Теперь введите текст новости:")

@router.message(NewsForm.content)
async def process_news_content(message: Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} entered news content.")
    data = await state.get_data()
    title = data.get("title")
    content = message.text

    # TODO: сохранить новость в базу данных
    # If you have a 'db' object available here (e.g., passed during handler registration),
    # you would save the news to the database here. Example:
    # await db.save_news(title, content)
    
    await message.answer(f"Новость добавлена!\n\n<b>{title}</b>\n{content}", parse_mode="HTML")
    await state.clear()
    logger.info(f"News '{title}' processed and state cleared for user {message.from_user.id}.")

# --- ADD THIS FUNCTION ---
def register_handlers(dp_or_router: Router):
    """Registers news handlers to the given Dispatcher or Router."""
    dp_or_router.include_router(router)
    logger.info("News handlers successfully registered.")