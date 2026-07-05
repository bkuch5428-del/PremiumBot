import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from database import save_user
from keyboards.menu import product_keyboard

logger = logging.getLogger(__name__)

router = Router()

PRODUCT_TEXT = (
    "🥵 <b>Premium Material</b>\n"
    "💰 Price: <b>₹99</b>"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    try:
        await save_user(user.id, user.username, user.first_name)
    except Exception:
        logger.exception("Failed to save user %s", user.id)

    await message.answer(PRODUCT_TEXT, reply_markup=product_keyboard())


@router.callback_query(lambda c: c.data == "demo")
async def callback_demo(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer("Demo videos will be added here.")


@router.callback_query(lambda c: c.data == "buy")
async def callback_buy(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer("Payment integration will be added later.")
