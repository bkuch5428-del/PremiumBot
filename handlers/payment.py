"""
handlers/payment.py — Buy Now flow.

Sequence:
  1. callback_buy         → generate order, send QR + payment details message
  2. callback_i_have_paid → ask user to send screenshot or UTR
  3. handle_payment_proof → accept photo/text, forward to review channel, confirm
  4. cancel callbacks     → cancel order, return to main menu

State while awaiting proof is kept in the module-level dict _awaiting_proof
(user_id -> order_id).  This requires no FSM storage changes in main.py.
To add Approve / Reject logic later, add handlers here that act on order_id
forwarded from the review channel.
"""

import logging
import random
from datetime import datetime, timezone, timedelta

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery

from config import (
    QR_IMAGE_URL,
    PAYMENT_REVIEW_CHANNEL_ID,
    PLAN_NAME,
    PLAN_PRICE,
    PLAN_VALIDITY,
    PUBLIC_CHANNEL_URL,
)
from database import create_order, update_order_status, approve_order
from keyboards.menu import (
    payment_details_keyboard,
    await_proof_keyboard,
    main_menu_keyboard,
    approve_reject_keyboard,
    product_keyboard,
)
from handlers.log_channel import log_payment_started

logger = logging.getLogger(__name__)

router = Router()

_IST = timezone(timedelta(hours=5, minutes=30))

# user_id -> order_id while we are waiting for the user to send proof.
_awaiting_proof: dict[int, str] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_order_id() -> str:
    # 6-digit suffix → 900 000 possible values, low collision probability.
    return f"A{random.randint(100000, 999999)}"


def _now_ist() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")


_PRODUCT_TEXT = (
    "Hello, {first_name} 👋\n\n"
    "Choose a plan to get started 💋"
)


# ── Buy Now ───────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "buy")
async def callback_buy(call: CallbackQuery, bot: Bot) -> None:
    """User tapped Buy Now — generate an order and show payment details."""
    await call.answer()

    user = call.from_user
    await log_payment_started(bot, user.id, user.first_name)

    # Retry up to 5 times in the unlikely event of a PK collision.
    order_id: str | None = None
    for _ in range(5):
        candidate = _make_order_id()
        try:
            await create_order(user.id, PLAN_NAME, PLAN_PRICE, PLAN_VALIDITY, candidate)
            order_id = candidate
            break
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                logger.warning("Order ID collision on %s — retrying", candidate)
                continue
            logger.exception("Failed to create order for user %s", user.id)
            await call.message.answer(
                "⚠️ Something went wrong. Please try again in a moment."
            )
            return

    if order_id is None:
        logger.error("Could not generate a unique order ID for user %s", user.id)
        await call.message.answer(
            "⚠️ Something went wrong. Please try again in a moment."
        )
        return

    payment_msg = (
        f"💳 <b>Payment Details</b>\n\n"
        f"📦 <b>Plan:</b> {PLAN_NAME}\n"
        f"💰 <b>Amount:</b> ₹{PLAN_PRICE}\n"
        f"⌛ <b>Validity:</b> {PLAN_VALIDITY}\n\n"
        f"📲 Scan the QR code above using any UPI app.\n\n"
        f"✓ Pay ₹{PLAN_PRICE} to the UPI ID above.\n"
        f"✓ After payment, click <b>✅ I Have Paid</b>\n\n"
        f"🆔 <b>Order:</b> #{order_id}"
    )

    if QR_IMAGE_URL:
        await bot.send_photo(
            chat_id=call.message.chat.id,
            photo=QR_IMAGE_URL,
        )

    await call.message.answer(
        payment_msg,
        reply_markup=payment_details_keyboard(order_id),
    )


# ── I Have Paid ───────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("paid:"))
async def callback_i_have_paid(call: CallbackQuery) -> None:
    """User tapped I Have Paid — ask for screenshot or UTR."""
    await call.answer()
    order_id = call.data.split(":", 1)[1]
    _awaiting_proof[call.from_user.id] = order_id

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
    """User cancelled before paying — mark order cancelled, go to main menu."""
    await call.answer()
    order_id = call.data.split(":", 1)[1]
    await update_order_status(order_id, "cancelled")
    _awaiting_proof.pop(call.from_user.id, None)

    await call.message.answer(
        _PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=product_keyboard(),
    )


# ── Cancel Proof (from awaiting-proof screen) ─────────────────────────────────

@router.callback_query(lambda c: c.data == "cancel_proof")
async def callback_cancel_proof(call: CallbackQuery) -> None:
    """User cancelled while we were waiting for proof — cancel order, go to main menu."""
    await call.answer()
    order_id = _awaiting_proof.pop(call.from_user.id, None)
    if order_id:
        await update_order_status(order_id, "cancelled")

    await call.message.answer(
        _PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=product_keyboard(),
    )


# ── Main Menu (from submission confirmation screen) ───────────────────────────

@router.callback_query(lambda c: c.data == "main_menu")
async def callback_main_menu(call: CallbackQuery) -> None:
    """User tapped Main Menu from confirmation screen."""
    await call.answer()
    await call.message.answer(
        _PRODUCT_TEXT.format(first_name=call.from_user.first_name),
        reply_markup=product_keyboard(),
    )


# ── Payment Proof handler ─────────────────────────────────────────────────────

async def _user_is_awaiting_proof(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in _awaiting_proof


@router.message(_user_is_awaiting_proof, F.photo | F.text)
async def handle_payment_proof(message: Message, bot: Bot) -> None:
    """
    Fires only for users in _awaiting_proof.
    Accepts a screenshot (photo) or a UTR / transaction ID (text).
    Forwards the proof to PAYMENT_REVIEW_CHANNEL_ID with full order details,
    then confirms to the user.
    """
    # Ignore commands — let command handlers deal with them.
    if message.text and message.text.startswith("/"):
        return

    user = message.from_user
    order_id = _awaiting_proof.pop(user.id, None)
    if not order_id:
        return

    await update_order_status(order_id, "pending")

    username = f"@{user.username}" if user.username else "None"
    review_caption = (
        f"🆔 Order: #{order_id}\n"
        f"👤 Name: {user.first_name}\n"
        f"📛 Username: {username}\n"
        f"🆔 User ID: <code>{user.id}</code>\n"
        f"📦 Plan: {PLAN_NAME}\n"
        f"💰 Amount: ₹{PLAN_PRICE}\n"
        f"🕒 Time: {_now_ist()}"
    )

    # Forward proof to the admin review channel with Approve / Reject buttons.
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
                    text=review_caption + f"\n\n📝 UTR / Transaction ID: {message.text}",
                    reply_markup=kb,
                )
        else:
            logger.warning("PAYMENT_REVIEW_CHANNEL_ID not set — skipping review forward")
    except Exception:
        logger.exception("Failed to forward payment proof to review channel")

    # Confirm to the user.
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
    """
    Admin clicked ✅ Approve in the review channel.
    Updates the order, notifies the user, removes buttons from the review message.
    Only processes callbacks that originate from PAYMENT_REVIEW_CHANNEL_ID.
    """
    # Guard: only honour clicks that came from the review channel itself.
    if call.message.chat.id != PAYMENT_REVIEW_CHANNEL_ID:
        await call.answer("⛔ Unauthorized.", show_alert=True)
        return

    order_id = call.data.split(":", 1)[1]
    result = await approve_order(order_id)
    if not result:
        await call.answer("⚠️ Order not found or already actioned.", show_alert=True)
        return

    await call.answer("✅ Approved!")

    # Convert UTC subscription_end to IST for display.
    sub_end_ist = result["subscription_end"].astimezone(_IST)
    expiry_str = sub_end_ist.strftime("%d %b %Y")

    # Notify the user.
    try:
        await bot.send_message(
            chat_id=result["user_id"],
            text=(
                "🎉 <b>Plan Activated!</b>\n\n"
                f"📦 <b>Plan:</b> {result['plan_name']}\n"
                f"⏳ <b>Validity:</b> {result['plan_validity']}\n"
                f"📅 <b>Expires:</b> {expiry_str}\n\n"
                f"🔗 <b>Your Public Channel:</b>\n"
                f"{PUBLIC_CHANNEL_URL}\n\n"
                "Thank you for your purchase! ❤️"
            ),
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        logger.exception("Failed to notify user %s of approval", result["user_id"])

    # Remove the Approve/Reject buttons from the review channel message.
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass  # message may already be edited or too old


# ── Admin: Reject (structure ready for next update) ───────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("reject:"))
async def callback_reject(call: CallbackQuery) -> None:
    """
    Admin clicked ❌ Reject in the review channel.
    Full rejection logic (user notification, refund instructions) to be added
    in the next update.  Buttons are removed so the order is not double-actioned.
    Only processes callbacks that originate from PAYMENT_REVIEW_CHANNEL_ID.
    """
    # Guard: only honour clicks that came from the review channel itself.
    if call.message.chat.id != PAYMENT_REVIEW_CHANNEL_ID:
        await call.answer("⛔ Unauthorized.", show_alert=True)
        return

    order_id = call.data.split(":", 1)[1]
    await update_order_status(order_id, "rejected")
    await call.answer("❌ Rejected. Full logic coming in next update.", show_alert=True)

    # Remove buttons from the review message.
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
