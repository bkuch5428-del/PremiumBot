import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set. Check your .env file.")

SOURCE_CHANNEL_ID: str = os.getenv("SOURCE_CHANNEL_ID", "-1004483132545")
DEMO_MESSAGE_IDS: list[int] = [2, 3, 4, 5, 6]

# Set this to your UPI QR code image URL to show it in the payment screen.
# Leave empty to show payment details as text only.
QR_IMAGE_URL: str = os.getenv("QR_IMAGE_URL", "")

SUPPORT_GROUP_URL: str = os.getenv("SUPPORT_GROUP_URL", "https://t.me/+i7Ox197t4205MTQ1")
