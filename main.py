import asyncio
import logging
import os
import threading

from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database import init_db
from handlers import start
from handlers import commands

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

BOT_COMMANDS = [
    BotCommand(command="start",   description="Start the bot"),
    BotCommand(command="plans",   description="View available plans"),
    BotCommand(command="status",  description="Check your subscription status"),
    BotCommand(command="help",    description="Help & usage guide"),
    BotCommand(command="contact", description="Contact support"),
]


async def main() -> None:
    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(commands.router)

    await bot.set_my_commands(BOT_COMMANDS)

    await dp.start_polling(bot)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Flask runs in a background daemon thread so it never blocks the bot.
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    asyncio.run(main())
