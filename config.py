import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set. Check your .env file.")

SOURCE_CHANNEL_ID: str = os.getenv("SOURCE_CHANNEL_ID", "-1004483132545")
DEMO_MESSAGE_IDS: list[int] = [2, 3, 4, 5, 6]
