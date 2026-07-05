from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

PLAN_BUTTON_TEXT = "💦 𝐑𝐞𝐚𝐥 𝐈𝐧𝐝!@𝐧 𝐃ē𝐬𝐢 𝐏𝟎4𝐧 🫦 – ₹49 / 30 Days"


def product_keyboard() -> InlineKeyboardMarkup:
    """Main product screen — one plan button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=PLAN_BUTTON_TEXT, callback_data="plan")]
        ]
    )


def plan_keyboard() -> InlineKeyboardMarkup:
    """Plan detail screen — Buy Now + Back."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Buy Now", callback_data="buy")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")],
        ]
    )


def payment_keyboard() -> InlineKeyboardMarkup:
    """Payment screen — Check Payment Status + Cancel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Check Payment Status", callback_data="check_payment")],
            [InlineKeyboardButton(text="❌ Cancel Payment", callback_data="cancel_payment")],
        ]
    )
