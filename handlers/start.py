import asyncio
import logging

from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from config import SOURCE_CHANNEL_ID, DEMO_MESSAGE_IDS
from database import save_user
from keyboards.menu import product_keyboard

logger = logging.getLogger(__name__)

router = Router()

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
    "Choose a plan to get started.\n\n"
    "━━━━━━━━━━━━━━\n\n"
    "🥵 PREMIUM MAAL\n"
    "💰 ₹49 / 30 Days\n\n"
    "━━━━━━━━━━━━━━"
)

AUTO_DELETE_DELAY = 300  # seconds


# ── Auto-delete helper ────────────────────────────────────────────────────────

async def _delete_after(bot: Bot, chat_id: int, msg_ids: list[int]) -> None:
    """Wait AUTO_DELETE_DELAY seconds, then silently delete each tracked message."""
    await asyncio.sleep(AUTO_DELETE_DELAY)
    for msg_id in msg_ids:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass


def _schedule_delete(bot: Bot, chat_id: int, msg_ids: list[int]) -> None:
    """Fire-and-forget: schedule deletion without blocking the handler."""
    asyncio.create_task(_delete_after(bot, chat_id, msg_ids))


# ── Demo video sender ─────────────────────────────────────────────────────────

async def send_demo_videos(bot: Bot, chat_id: int) -> list[int]:
    """
    Copy each demo message from the private channel to the user.
    Returns a list of the sent message IDs for auto-deletion tracking.
    Each copy is tried independently — one failure never stops the rest.
    """
    print("SOURCE_CHANNEL_ID:", SOURCE_CHANNEL_ID)
    print("DEMO_MESSAGE_IDS:", DEMO_MESSAGE_IDS)

    if not SOURCE_CHANNEL_ID:
        print("SOURCE_CHANNEL_ID not set, skipping demo video")
        logger.warning("SOURCE_CHANNEL_ID is not set — skipping demo videos.")
        return []

    sent_ids: list[int] = []
    for message_id in DEMO_MESSAGE_IDS:
        try:
            msg = await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=SOURCE_CHANNEL_ID,
                message_id=message_id,
            )
            sent_ids.append(msg.message_id)
        except Exception:
            logger.exception(
                "Failed to copy message %s from channel %s",
                message_id,
                SOURCE_CHANNEL_ID,
            )
        # Always wait between copies — even after a failure — for stability
        await asyncio.sleep(0.25)
    return sent_ids


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    user = message.from_user

    try:
        await save_user(user.id, user.username, user.first_name)
    except Exception:
        logger.exception("Failed to save user %s", user.id)

    tracked: list[int] = []

    tracked.extend(await send_demo_videos(bot, message.chat.id))

    welcome_msg = await message.answer(WELCOME_TEXT)
    tracked.append(welcome_msg.message_id)

    product_msg = await message.answer(
        PRODUCT_TEXT.format(first_name=user.first_name),
        reply_markup=product_keyboard(),
    )
    tracked.append(product_msg.message_id)

    _schedule_delete(bot, message.chat.id, tracked)


@router.callback_query(lambda c: c.data == "demo")
async def callback_demo(call: CallbackQuery, bot: Bot) -> None:
    await call.answer()
    sent_ids = await send_demo_videos(bot, call.message.chat.id)
    if sent_ids:
        _schedule_delete(bot, call.message.chat.id, sent_ids)


@router.callback_query(lambda c: c.data == "buy")
async def callback_buy(call: CallbackQuery) -> None:
    await call.answer()
    msg = await call.message.answer("Payment system will be added in the next update.")
    _schedule_delete(call.bot, call.message.chat.id, [msg.message_id])
