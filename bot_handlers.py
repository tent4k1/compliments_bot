from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

router = Router()


@router.message(Command("start"))
async def start_handler(message: Message):
    # Получаем scheduler из контекста
    scheduler = message.bot.get("scheduler")
    if not scheduler:
        return await message.answer("Ошибка инициализации бота")

    scheduler.user_ids.add(message.from_user.id)
    await message.answer("Теперь ты будешь получать комплименты 3 раза в день! ❤️")


@router.message(Command("stop"))
async def stop_handler(message: Message):
    scheduler = message.bot.get("scheduler")
    if not scheduler:
        return await message.answer("Ошибка инициализации бота")

    scheduler.user_ids.discard(message.from_user.id)
    await message.answer("Ты больше не будешь получать комплименты 😢")