import asyncio
import logging

from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from database import save_user, get_all_plans, get_plan, get_setting
from keyboards.menu import plans_list_keyboard, plan_detail_keyboard, main_menu_keyboard
from handlers.log_channel import log_new_user, log_plan_selected

logger = logging.getLogger(__name__)

router = Router()

# ── Fallback texts (used only when DB setting is empty) ───────────────────────

_DEFAULT_WELCOME = (
    "🎉 <b>Welcome to Premium Bot!</b>\n\n"
    "✨ Get exclusive access to premium content\n"
    "💰 Affordable plans available\n"
    "✨ Daily New Uploads\n"
    "✨ High Quality Content\n\n"
    "✨ <b>SELECT A PLAN TO GET STARTED</b> ✨"
)

PRODUCT_TEXT = "Hello, {first_name} 👋\n\nChoose a plan to get started 💫"

NO_PLANS_TEXT = (
    "⚠️ No plans are available right now.\n\n"
    "Please check back later or contact support."
)


# ── Demo video sender ─────────────────────────────────────────────────────────

async def send_demo_videos(bot: Bot, chat_id: int, plan: dict) -> None:
    """
    Copy demo messages from the plan's source channel to the user.
    Stores only message IDs — no media is downloaded locally.
    """
    source = plan.get("source_channel_id", "")
    msg_ids = plan.get("demo_message_ids", [])

    if not source or not msg_ids:
        logger.warning("Plan id=%s has no demo videos configured.", plan.get("id"))
        return

    # Primary: batch copy as album
    try:
        await bot.copy_messages(
            chat_id=chat_id,
            from_chat_id=source,
            message_ids=msg_ids,
        )
        return
    except Exception:
        logger.exception("copy_messages() failed — falling back to individual sends")

    # Fallback: one-by-one
    for message_id in msg_ids:
        try:
            await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=source,
                message_id=message_id,
            )
        except Exception:
            logger.exception(
                "Failed to copy message %s from channel %s", message_id, source
            )
        await asyncio.sleep(0.25)


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    logger.info("/start from user %s", message.from_user.id)
    user = message.from_user

    try:
        is_new = await save_user(user.id, user.username, user.first_name)
    except Exception:
        logger.exception("Failed to save user %s", user.id)
        is_new = False

    if is_new:
        await log_new_user(bot, user.id, user.first_name, user.username)

    plans = await get_all_plans()

    if not plans:
        welcome_text = (await get_setting("welcome_message")) or _DEFAULT_WELCOME
        await message.answer(welcome_text)
        await message.answer(NO_PLANS_TEXT)
        return

    # Send demo videos from the first plan
    await send_demo_videos(bot, message.chat.id, plans[0])
    welcome_text = (await get_setting("welcome_message")) or _DEFAULT_WELCOME
    await message.answer(welcome_text)
    await message.answer(
        PRODUCT_TEXT.format(first_name=user.first_name),
        reply_markup=plans_list_keyboard(plans),
    )


# ── Show plans (from "View Plans" button fallback) ────────────────────────────

@router.callback_query(lambda c: c.data == "show_plans")
async def cb_show_plans(call: CallbackQuery, bot: Bot) -> None:
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.answer(NO_PLANS_TEXT)
        return
    await call.message.answer(
        PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=plans_list_keyboard(plans),
    )


# ── Plan selected (plan:{plan_id}) ────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("plan:"))
async def callback_plan(call: CallbackQuery, bot: Bot) -> None:
    """User tapped a plan button — send demo videos then plan detail."""
    await call.answer()
    try:
        plan_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.message.answer("⚠️ Invalid plan. Please try again.")
        return

    plan = await get_plan(plan_id)
    if not plan:
        await call.message.answer("⚠️ Plan not found. It may have been removed.")
        return

    await log_plan_selected(
        bot,
        call.from_user.id,
        call.from_user.first_name,
        plan_title=plan["name"],
        price=f"₹{plan['price']} / {plan['validity']}",
    )

    await send_demo_videos(bot, call.message.chat.id, plan)

    plan_text = (
        f"📦 <b>{plan['name']}</b>\n\n"
        f"💰 <b>Price:</b> ₹{plan['price']}\n"
        f"⏳ <b>Validity:</b> {plan['validity']}\n\n"
        "Tap <b>Buy Now</b> to proceed with payment."
    )
    await call.message.answer(plan_text, reply_markup=plan_detail_keyboard(plan_id))


# ── Back to plan list ─────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "back")
async def callback_back(call: CallbackQuery) -> None:
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.answer(NO_PLANS_TEXT)
        return
    await call.message.answer(
        PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=plans_list_keyboard(plans),
    )


# ── Main menu ─────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "main_menu")
async def callback_main_menu(call: CallbackQuery) -> None:
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.answer(NO_PLANS_TEXT)
        return
    await call.message.answer(
        PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=plans_list_keyboard(plans),
    )
