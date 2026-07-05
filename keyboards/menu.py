from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def product_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👀 Demo", callback_data="demo"),
                InlineKeyboardButton(text="💳 Buy Now", callback_data="buy"),
            ]
        ]
    )
