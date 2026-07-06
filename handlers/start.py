import asyncio
import logging

from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from config import SOURCE_CHANNEL_ID, DEMO_MESSAGE_IDS
from database import save_user
from keyboards.menu import product_keyboard, plan_keyboard, PLAN_BUTTON_TEXT
from handlers.log_channel import log_new_user, log_plan_selected

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



# ── Demo video sender ─────────────────────────────────────────────────────────

async def send_demo_videos(bot: Bot, chat_id: int) -> None:
    """
    Copy demo messages from the private channel to the user as a single album.

    Uses copy_messages() (Bot API 7.0 / aiogram 3.4+) which copies all
    message IDs in one call and re-groups them as an album when the originals
    were part of a media group. Falls back to individual copy_message() calls
    if the batch call fails for any reason.
    """
    print("SOURCE_CHANNEL_ID:", SOURCE_CHANNEL_ID)
    print("DEMO_MESSAGE_IDS:", DEMO_MESSAGE_IDS)

    if not SOURCE_CHANNEL_ID:
        print("SOURCE_CHANNEL_ID not set, skipping demo video")
        logger.warning("SOURCE_CHANNEL_ID is not set — skipping demo videos.")
        return

    # ── Primary: send as a single album ──────────────────────────────────────
    try:
        await bot.copy_messages(
            chat_id=chat_id,
            from_chat_id=SOURCE_CHANNEL_ID,
            message_ids=DEMO_MESSAGE_IDS,
        )
        return
    except Exception:
        logger.exception("copy_messages() failed — falling back to individual sends")

    # ── Fallback: send one by one ─────────────────────────────────────────────
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
        await asyncio.sleep(0.25)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    print("Received command: /start")
    logger.info("Received command: /start from user %s", message.from_user.id)
    user = message.from_user

    try:
        is_new = await save_user(user.id, user.username, user.first_name)
    except Exception:
        logger.exception("Failed to save user %s", user.id)
        is_new = False

    if is_new:
        await log_new_user(bot, user.id, user.first_name, user.username)

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
    await log_plan_selected(bot, call.from_user.id, call.from_user.first_name)
    await send_demo_videos(bot, call.message.chat.id)
    await call.message.answer(PLAN_TEXT, reply_markup=plan_keyboard())


@router.callback_query(lambda c: c.data == "back")
async def callback_back(call: CallbackQuery) -> None:
    """User tapped Back — return to product screen."""
    await call.answer()
    await call.message.answer(
        PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=product_keyboard(),
    )


