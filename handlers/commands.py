import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import SUPPORT_GROUP_URL

logger = logging.getLogger(__name__)

router = Router()

# ── Plan definitions ──────────────────────────────────────────────────────────
# Add new plans here as dicts. The /plans command renders them dynamically.

PLANS = [
    {
        "name": "💦 𝐑𝐞𝐚𝐥 𝐈𝐧𝐝!@𝐧 𝐃ē𝐬𝐢 𝐏𝟎4𝐧 🫦",
        "price": "₹49",
        "validity": "30 Days",
        "callback": "buy",
    },
]


# ── /plans ────────────────────────────────────────────────────────────────────

@router.message(Command("plans"))
async def cmd_plans(message: Message) -> None:
    for plan in PLANS:
        text = (
            f"{plan['name']}\n"
            f"💰 {plan['price']} / {plan['validity']}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Buy Now", callback_data=plan["callback"])]
            ]
        )
        await message.answer(text, reply_markup=keyboard)


# ── /status ───────────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    # Placeholder — replace with real subscription lookup when payment is integrated.
    await message.answer("❌ No active subscription found.")


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "❓ <b>Help Center</b>\n\n"
        "• Use /plans to view available plans.\n"
        "• Select a plan and complete payment.\n"
        "• After payment, check your subscription status using /status.\n"
        "• If you face any issue, use /contact."
    )


# ── /contact ──────────────────────────────────────────────────────────────────

@router.message(Command("contact"))
async def cmd_contact(message: Message) -> None:
    await message.answer(
        "📞 <b>Support</b>\n\n"
        "Need help?\n\n"
        f"Join our official support group:\n\n"
        f"{SUPPORT_GROUP_URL}"
    )
