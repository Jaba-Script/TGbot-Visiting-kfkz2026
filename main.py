import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import config
import handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

BOT_COMMANDS = [
    BotCommand(command="mark",   description="Відмітити відсутніх на парі"),
    BotCommand(command="cancel", description="Скасувати поточну дію"),
    BotCommand(command="start",     description="Головне меню"),
]


async def main():
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(handlers.router)

    await bot.set_my_commands(BOT_COMMANDS)

    print("✅ Бот запущено!")
    print(f"   Дозволені користувачі: {config.ALLOWED_USERS}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
