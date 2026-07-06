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


def payment_details_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Payment details screen — I Have Paid + Cancel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ I Have Paid", callback_data=f"paid:{order_id}")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_order:{order_id}")],
        ]
    )


def await_proof_keyboard() -> InlineKeyboardMarkup:
    """Awaiting payment proof — Cancel only."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_proof")],
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Post-submission confirmation — return to main menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
    )


def approve_reject_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Admin review channel — Approve / Reject buttons for a pending order."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"approve:{order_id}"),
                InlineKeyboardButton(text="❌ Reject",  callback_data=f"reject:{order_id}"),
            ]
        ]
    )
