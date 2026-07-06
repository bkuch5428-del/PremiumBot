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

# Channel where new-user and activity events are logged.
LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "-1003923230922"))

# Channel where payment screenshots / UTRs are forwarded for admin review.
PAYMENT_REVIEW_CHANNEL_ID: int = int(os.getenv("PAYMENT_REVIEW_CHANNEL_ID", "-1003290863151"))

# Active plan details — single source of truth used across all handlers.
PLAN_NAME: str = "💦 𝐑𝐞𝐚𝐥 𝐈𝐧𝐝!𝐚𝐧 𝐃ē𝐬𝐢 𝐏𝟎𝐫𝐧 🫦"
PLAN_PRICE: str = "49"
PLAN_VALIDITY: str = "30 Days"

# Public channel link sent to users after plan activation.
PUBLIC_CHANNEL_URL: str = os.getenv("PUBLIC_CHANNEL_URL", "https://t.me/MoviesMasterUpdates")
