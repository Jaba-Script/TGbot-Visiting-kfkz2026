import asyncio
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from logging.handlers import RotatingFileHandler
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import config
import handlers

# ── Логування ─────────────────────────────────────────────────────────────────
def setup_logging():
    fmt     = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
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

# ── Фіктивний HTTP-сервер (для Koyeb/Render) ─────────────────────────────────
# Koyeb вимагає щоб сервіс слухав HTTP-порт, інакше вважає його впалим.
# Цей мінімальний сервер просто відповідає 200 OK на будь-який запит.

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # не засмічувати лог healthcheck-запитами


def start_health_server():
    port = int(os.getenv("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Health server запущено на порту {port}")
    server.serve_forever()

# ──────────────────────────────────────────────────────────────────────────────

# ── Middleware: ігноруємо застарілі повідомлення ──────────────────────────────
MAX_MESSAGE_AGE_SEC = 30  # повідомлення старші за 30 сек ігноруємо

class AntiFloodMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.date:
            now = datetime.now(timezone.utc)
            age = (now - event.date).total_seconds()
            if age > MAX_MESSAGE_AGE_SEC:
                return  # мовчки ігноруємо
        return await handler(event, data)
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
    dp.message.middleware(AntiFloodMiddleware())
    dp.include_router(handlers.router)

    await bot.set_my_commands(BOT_COMMANDS)

    logger.info("✅ Бот запущено!")
    logger.info(f"   Дозволені користувачі: {config.ALLOWED_USERS}")
    if config.WEEK_A_START:
        logger.info(f"   Чергування тижнів: увімкнено (тиждень А від {config.WEEK_A_START})")

    await dp.start_polling(bot)


if __name__ == "__main__":
    # Запускаємо health server у окремому потоці
    thread = threading.Thread(target=start_health_server, daemon=True)
    thread.start()

    asyncio.run(main())
