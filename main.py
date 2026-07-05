import asyncio
import logging
import os
import threading

from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database import init_db
from handlers import start

logging.basicConfig(level=logging.INFO)

# ── Flask health-check server ─────────────────────────────────────────────────

flask_app = Flask(__name__)


@flask_app.route("/")
def index():
    return "Bot is running"


def run_flask() -> None:
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


# ── Telegram bot ──────────────────────────────────────────────────────────────

async def main() -> None:
    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(start.router)

    await dp.start_polling(bot)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Flask runs in a background daemon thread so it never blocks the bot.
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    asyncio.run(main())
