"""
handlers/payment.py — Buy Now flow.

Sequence:
  1. callback_buy         → load plan from DB, generate order, show payment details
  2. callback_i_have_paid → ask user to send screenshot or UTR
  3. handle_payment_proof → accept photo/text, forward to review channel, confirm
  4. cancel callbacks     → cancel order, return to main menu
  5. approve / reject     → admin buttons in review channel
"""

import html
import logging
import random
from datetime import datetime, timezone, timedelta

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery

from config import QR_IMAGE_URL, PAYMENT_REVIEW_CHANNEL_ID, ADMIN_IDS
from database import (
    create_order,
    update_order_status,
    approve_order,
    get_plan,
    get_all_plans,
    get_setting,
    set_pending_reminder,
    cancel_reminder,
)
from keyboards.menu import (
    payment_details_keyboard,
    await_proof_keyboard,
    main_menu_keyboard,
    approve_reject_keyboard,
    plans_list_keyboard,
)
from handlers.log_channel import log_payment_started

logger = logging.getLogger(__name__)

router = Router()

_IST = timezone(timedelta(hours=5, minutes=30))

# user_id -> { order_id, plan_name, plan_price, plan_validity, access_link }
_awaiting_proof: dict[int, dict] = {}

_PRODUCT_TEXT = "Hello, {first_name} 👋\n\nChoose a plan to get started 💫"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_order_id() -> str:
    return f"A{random.randint(100000, 999999)}"


def _now_ist() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")


# ── Buy Now (buy:{plan_id}) ───────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("buy:"))
async def callback_buy(call: CallbackQuery, bot: Bot) -> None:
    """User tapped Buy Now — load plan from DB, generate order, show payment details."""
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

    user = call.from_user
    await log_payment_started(bot, user.id, user.first_name, plan_title=plan["name"])

    # Retry up to 5 times on PK collision
    order_id: str | None = None
    for _ in range(5):
        candidate = _make_order_id()
        try:
            await create_order(
                user_id=user.id,
                plan_name=plan["name"],
                plan_price=plan["price"],
                plan_validity=plan["validity"],
                order_id=candidate,
                plan_id=plan_id,
                access_link=plan["access_link"],
            )
            order_id = candidate
            break
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                logger.warning("Order ID collision on %s — retrying", candidate)
                continue
            logger.exception("Failed to create order for user %s", user.id)
            await call.message.answer("⚠️ Something went wrong. Please try again.")
            return

    if order_id is None:
        await call.message.answer("⚠️ Could not generate order. Please try again.")
        return

    # Payment message: use DB setting, fall back to built-in default template
    _default_tpl = (
        "💳 <b>Payment Details</b>\n\n"
        "📦 <b>Plan:</b> {plan_name}\n"
        "💰 <b>Amount:</b> ₹{plan_price}\n"
        "⌛ <b>Validity:</b> {plan_validity}\n\n"
        "📲 Scan the QR code above using any UPI app.\n\n"
        "✓ Pay ₹{plan_price} to the UPI ID shown.\n"
        "✓ After payment, click <b>✅ I Have Paid</b>\n\n"
        "🆔 <b>Order:</b> #{order_id}"
    )
    payment_tpl = (await get_setting("payment_message")) or _default_tpl
    _fmt_kwargs = dict(
        plan_name=plan["name"],
        plan_price=plan["price"],
        plan_validity=plan["validity"],
        order_id=order_id,
    )
    try:
        payment_msg = payment_tpl.format(**_fmt_kwargs)
    except (KeyError, ValueError, IndexError):
        # Admin entered a malformed template — fall back to built-in default
        logger.warning("payment_message template is malformed — using default")
        payment_msg = _default_tpl.format(**_fmt_kwargs)

    # QR image: per-plan first, then global DB setting, then env var URL, then skip
    qr_image = plan.get("qr_image") or (await get_setting("qr_image")) or QR_IMAGE_URL
    if qr_image:
        try:
            await bot.send_photo(chat_id=call.message.chat.id, photo=qr_image)
        except Exception:
            logger.warning("Failed to send QR image — check the stored file_id or URL")

    await call.message.answer(payment_msg, reply_markup=payment_details_keyboard(order_id))

    # Store plan context for proof handler
    _awaiting_proof[user.id] = {
        "order_id":     order_id,
        "plan_name":    plan["name"],
        "plan_price":   plan["price"],
        "plan_validity": plan["validity"],
        "access_link":  plan["access_link"],
    }

    # Schedule abandoned-payment reminders — replaces any previous schedule
    # for this user instead of stacking duplicates.
    _MAX_REMINDER_DELAY_MIN = 525600  # 1 year — matches the admin input cap; guards timedelta()

    def _clamped_delay(raw: str, fallback: int) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return fallback
        if value <= 0:
            return fallback
        return min(value, _MAX_REMINDER_DELAY_MIN)

    first_min = _clamped_delay(await get_setting("reminder_first_delay_min", "15"), 15)
    second_min = _clamped_delay(await get_setting("reminder_second_delay_min", "1440"), 1440)
    now = datetime.now(timezone.utc)
    await set_pending_reminder(
        user_id=user.id,
        order_id=order_id,
        plan_id=plan_id,
        plan_name=plan["name"],
        plan_price=plan["price"],
        plan_validity=plan["validity"],
        first_due=now + timedelta(minutes=first_min),
        second_due=now + timedelta(minutes=second_min),
    )


# ── I Have Paid ───────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("paid:"))
async def callback_i_have_paid(call: CallbackQuery) -> None:
    await call.answer()
    order_id = call.data.split(":", 1)[1]

    # Ensure state is current (user may have come from the payment details message)
    if call.from_user.id not in _awaiting_proof:
        _awaiting_proof[call.from_user.id] = {"order_id": order_id}
    else:
        _awaiting_proof[call.from_user.id]["order_id"] = order_id

    await call.message.answer(
        "✅ <b>Great!</b>\n\n"
        "📤 Please send your <b>payment screenshot</b> OR\n"
        "📝 type your <b>UTR / Transaction ID</b>\n\n"
        "We'll verify and activate your plan within 30 minutes.",
        reply_markup=await_proof_keyboard(),
    )


# ── Cancel Order (from payment details screen) ────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("cancel_order:"))
async def callback_cancel_order(call: CallbackQuery) -> None:
    await call.answer()
    order_id = call.data.split(":", 1)[1]
    await update_order_status(order_id, "cancelled")
    _awaiting_proof.pop(call.from_user.id, None)
    await cancel_reminder(call.from_user.id, order_id)

    plans = await get_all_plans()
    await call.message.answer(
        _PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=plans_list_keyboard(plans) if plans else main_menu_keyboard(),
    )


# ── Cancel Proof (from awaiting-proof screen) ─────────────────────────────────

@router.callback_query(lambda c: c.data == "cancel_proof")
async def callback_cancel_proof(call: CallbackQuery) -> None:
    await call.answer()
    info = _awaiting_proof.pop(call.from_user.id, None)
    if info:
        await update_order_status(info["order_id"], "cancelled")
        await cancel_reminder(call.from_user.id, info["order_id"])
    else:
        await cancel_reminder(call.from_user.id)

    plans = await get_all_plans()
    await call.message.answer(
        _PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=plans_list_keyboard(plans) if plans else main_menu_keyboard(),
    )


# ── Payment Proof handler ─────────────────────────────────────────────────────

async def _user_is_awaiting_proof(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in _awaiting_proof


@router.message(_user_is_awaiting_proof, F.photo | F.text)
async def handle_payment_proof(message: Message, bot: Bot) -> None:
    if message.text and message.text.startswith("/"):
        return

    user = message.from_user
    info = _awaiting_proof.pop(user.id, None)
    if not info:
        return

    order_id = info["order_id"]
    plan_name = info.get("plan_name", "—")
    plan_price = info.get("plan_price", "—")

    await update_order_status(order_id, "pending")

    username = f"@{html.escape(user.username)}" if user.username else "None"
    review_caption = (
        f"🆔 Order: #{order_id}\n"
        f"👤 Name: {html.escape(user.first_name)}\n"
        f"📛 Username: {username}\n"
        f"🆔 User ID: <code>{user.id}</code>\n"
        f"📦 Plan: {html.escape(plan_name)}\n"
        f"💰 Amount: ₹{html.escape(plan_price)}\n"
        f"🕒 Time: {_now_ist()}"
    )

    try:
        if PAYMENT_REVIEW_CHANNEL_ID:
            kb = approve_reject_keyboard(order_id)
            if message.photo:
                await bot.send_photo(
                    chat_id=PAYMENT_REVIEW_CHANNEL_ID,
                    photo=message.photo[-1].file_id,
                    caption=review_caption,
                    reply_markup=kb,
                )
            else:
                await bot.send_message(
                    chat_id=PAYMENT_REVIEW_CHANNEL_ID,
                    text=review_caption + f"\n\n📝 UTR / Transaction ID: {html.escape(message.text or '')}",
                    reply_markup=kb,
                )
        else:
            logger.warning("PAYMENT_REVIEW_CHANNEL_ID not set — skipping review forward")
    except Exception:
        logger.exception("Failed to forward payment proof to review channel")

    await message.answer(
        f"✅ <b>Request Submitted!</b>\n\n"
        f"🆔 Order #{order_id}\n\n"
        f"⌛ Your plan will be activated after verification.\n\n"
        f"You'll receive a notification once approved.",
        reply_markup=main_menu_keyboard(),
    )


# ── Admin: Approve ────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("approve:"))
async def callback_approve(call: CallbackQuery, bot: Bot) -> None:
    # Fail-closed: both conditions must pass regardless of whether ADMIN_IDS is configured.
    if call.message.chat.id != PAYMENT_REVIEW_CHANNEL_ID or call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔ Unauthorized.", show_alert=True)
        return

    order_id = call.data.split(":", 1)[1]
    result = await approve_order(order_id)
    if not result:
        await call.answer("⚠️ Order not found or already actioned.", show_alert=True)
        return

    await call.answer("✅ Approved!")

    sub_end_ist = result["subscription_end"].astimezone(_IST)
    expiry_str = sub_end_ist.strftime("%d %b %Y")

    access_link = result.get("access_link", "")

    try:
        activation_text = (
            "🎉 <b>Plan Activated!</b>\n\n"
            f"📦 <b>Plan:</b> {result['plan_name']}\n"
            f"⏳ <b>Validity:</b> {result['plan_validity']}\n"
            f"📅 <b>Expires:</b> {expiry_str}\n\n"
        )
        if access_link:
            activation_text += f"🔗 <b>Access Link:</b>\n{access_link}\n\n"
        activation_text += "Thank you for your purchase! ❤️"

        await bot.send_message(
            chat_id=result["user_id"],
            text=activation_text,
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        logger.exception("Failed to notify user %s of approval", result["user_id"])

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ── Admin: Reject ─────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("reject:"))
async def callback_reject(call: CallbackQuery, bot: Bot) -> None:
    # Fail-closed: both conditions must pass regardless of whether ADMIN_IDS is configured.
    if call.message.chat.id != PAYMENT_REVIEW_CHANNEL_ID or call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔ Unauthorized.", show_alert=True)
        return

    order_id = call.data.split(":", 1)[1]
    await update_order_status(order_id, "rejected")
    await call.answer("❌ Payment rejected.", show_alert=True)

    # Notify the user about rejection
    try:
        # Fetch user_id from review message caption
        caption = call.message.caption or call.message.text or ""
        uid_line = next((l for l in caption.splitlines() if "User ID:" in l), None)
        if uid_line:
            # "🆔 User ID: 123456" or with code tags
            uid_str = uid_line.split(":")[-1].strip().strip("<code>").strip("</code>")
            user_id = int(uid_str)
            await cancel_reminder(user_id, order_id)
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "❌ <b>Payment Rejected</b>\n\n"
                    f"🆔 Order #{order_id}\n\n"
                    "Your payment could not be verified. Please contact support if you believe this is an error."
                ),
                reply_markup=main_menu_keyboard(),
            )
    except Exception:
        logger.exception("Failed to notify user of rejection for order %s", order_id)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
