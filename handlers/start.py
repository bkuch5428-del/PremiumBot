import asyncio
import logging

from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from config import SOURCE_CHANNEL_ID, DEMO_MESSAGE_IDS, QR_IMAGE_URL
from database import save_user
from keyboards.menu import product_keyboard, plan_keyboard, payment_keyboard, PLAN_BUTTON_TEXT

logger = logging.getLogger(__name__)

router = Router()

# ── Static texts ──────────────────────────────────────────────────────────────

WELCOME_TEXT = (
    "🎉 <b>Welcome to Premium Leaks Robot!</b>\n\n"
    "✨ Get exclusive access to premium content\n"
    "💰 Affordable plans starting at just ₹99\n"
    "✨ Content quality aisi ki dekhi nahi hogi\n"
    "✨ Only Premium Content\n"
    "✨ Daily New Uploads\n"
    "✨ C!p!, R!p!, Indi@n, Fore!gn, D@rk everything\n"
    "✨ 10000+ C!p! videos\n"
    "✨  25000+ R!p! videos\n"
    "✨  M0m $0n 5k Videos\n\n"
    "✨ <b>TRY OUR ANY PLAN FOR CHECKING THE QUALITY</b> ✨"
)

PRODUCT_TEXT = (
    "Hello, {first_name} 👋\n\n"
    "Choose a plan to get started 💋"
)

PLAN_TEXT = (
    "💦 Full Desi Indian content approx 40000+ videos💦\n\n"
    "🫦Buy now to get access🫦\n\n"
    "📦 💦 𝐑𝐞𝐚𝐥 𝐈𝐧𝐝!𝐚𝐧 𝐃ē𝐬𝐢 𝐏𝟎𝐫𝐧 🫦\n"
    "💰 Price: ₹49 | ⏳ 30 Days"
)

PAYMENT_CAPTION = (
    "📲 Scan the QR code above using any UPI app.\n\n"
    "💰 Amount: ₹49.00\n\n"
    "After completing the payment, tap the button below to verify your payment."
)

PAYMENT_TEXT = (
    "💳 <b>Payment Details</b>\n\n"
    "📦 Plan: 💦 𝐑𝐞𝐚𝐥 𝐈𝐧𝐝!𝐚𝐧 𝐃ē𝐬𝐢 𝐏𝟎𝐫𝐧 🫦\n"
    "💰 Amount: ₹49.00\n"
    "⏳ Validity: 30 Days\n\n"
    "📲 Scan the QR code using any UPI app.\n\n"
    "After completing the payment, tap the button below to verify your payment."
)


# ── Demo video sender ─────────────────────────────────────────────────────────

async def send_demo_videos(bot: Bot, chat_id: int) -> None:
    """
    Copy each demo message from the private channel to the user.
    Each copy is tried independently — one failure never stops the rest.
    """
    print("SOURCE_CHANNEL_ID:", SOURCE_CHANNEL_ID)
    print("DEMO_MESSAGE_IDS:", DEMO_MESSAGE_IDS)

    if not SOURCE_CHANNEL_ID:
        print("SOURCE_CHANNEL_ID not set, skipping demo video")
        logger.warning("SOURCE_CHANNEL_ID is not set — skipping demo videos.")
        return

    for message_id in DEMO_MESSAGE_IDS:
        try:
            await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=SOURCE_CHANNEL_ID,
                message_id=message_id,
            )
        except Exception:
            logger.exception(
                "Failed to copy message %s from channel %s",
                message_id,
                SOURCE_CHANNEL_ID,
            )
        # Always wait between copies — even after a failure — for stability
        await asyncio.sleep(0.25)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    print("Received command: /start")
    logger.info("Received command: /start from user %s", message.from_user.id)
    user = message.from_user

    try:
        await save_user(user.id, user.username, user.first_name)
    except Exception:
        logger.exception("Failed to save user %s", user.id)

    await send_demo_videos(bot, message.chat.id)
    await message.answer(WELCOME_TEXT)
    await message.answer(
        PRODUCT_TEXT.format(first_name=user.first_name),
        reply_markup=product_keyboard(),
    )


@router.callback_query(lambda c: c.data == "plan")
async def callback_plan(call: CallbackQuery, bot: Bot) -> None:
    """User tapped the plan button — send demo videos then plan details."""
    await call.answer()
    await send_demo_videos(bot, call.message.chat.id)
    await call.message.answer(PLAN_TEXT, reply_markup=plan_keyboard())


@router.callback_query(lambda c: c.data == "buy")
async def callback_buy(call: CallbackQuery, bot: Bot) -> None:
    """User tapped Buy Now — send QR (if configured) + payment instructions."""
    await call.answer()
    if QR_IMAGE_URL:
        await bot.send_photo(
            chat_id=call.message.chat.id,
            photo=QR_IMAGE_URL,
            caption=PAYMENT_CAPTION,
            reply_markup=payment_keyboard(),
        )
    else:
        await call.message.answer(PAYMENT_TEXT, reply_markup=payment_keyboard())


@router.callback_query(lambda c: c.data == "back")
async def callback_back(call: CallbackQuery) -> None:
    """User tapped Back — return to product screen."""
    await call.answer()
    await call.message.answer(
        PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=product_keyboard(),
    )


@router.callback_query(lambda c: c.data == "check_payment")
async def callback_check_payment(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        "Payment verification system will be added in the next update."
    )


@router.callback_query(lambda c: c.data == "cancel_payment")
async def callback_cancel_payment(call: CallbackQuery) -> None:
    """User cancelled payment — return to product screen."""
    await call.answer()
    await call.message.answer(
        PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=product_keyboard(),
    )
