import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import config
import handlers

# ── Логування: консоль + файл ─────────────────────────────────────────────────
def setup_logging():
    fmt     = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)

    # Файл: макс 5 МБ, зберігаємо 3 останніх файли
    file_handler = RotatingFileHandler(
        "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler)

setup_logging()
logger = logging.getLogger(__name__)
# ──────────────────────────────────────────────────────────────────────────────

BOT_COMMANDS = [
    BotCommand(command="mark",    description="Відмітити відсутніх на парі"),
    BotCommand(command="history", description="Переглянути останні 5 пар"),
    BotCommand(command="edit",    description="Виправити помилкову відмітку"),
    BotCommand(command="status",  description="Перевірити підключення до таблиці"),
    BotCommand(command="cancel",  description="Скасувати поточну дію"),
    BotCommand(command="start",   description="Головне меню"),
]


async def main():
    bot = Bot(token=config.BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(handlers.router)

    await bot.set_my_commands(BOT_COMMANDS)

    logger.info("✅ Бот запущено!")
    logger.info(f"   Дозволені користувачі: {config.ALLOWED_USERS}")
    if config.WEEK_A_START:
        logger.info(f"   Чергування тижнів: увімкнено (тиждень А від {config.WEEK_A_START})")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
