"""
handlers/payment.py — Buy Now flow with automatic VC Store payment verification.

Sequence:
  1. callback_buy         → load plan from DB, generate order, show payment details
  2. callback_i_have_paid → call VC Store API to verify payment automatically
       success  → instantly approve order, send access link
       pending  → tell user payment is still being processed
       failed   → ask user to complete payment and try again
  3. cancel callbacks     → cancel order, return to main menu
"""

import html
import logging
import random
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import aiohttp

from aiogram import Router, Bot
from aiogram.types import CallbackQuery

from config import VC_API_KEY, VC_API_URL
from database import (
    create_order,
    update_order_status,
    approve_order,
    get_order,
    get_order_final_price,
    user_has_active_plan,
    get_plan,
    get_all_plans,
    get_setting,
    get_user_referral_info,
    set_pending_reminder,
    cancel_reminder,
    clear_plan_interest,
)
from keyboards.menu import (
    payment_details_keyboard,
    main_menu_keyboard,
    plans_list_keyboard,
)
from handlers.log_channel import log_payment_started

logger = logging.getLogger(__name__)

router = Router()

_IST = timezone(timedelta(hours=5, minutes=30))

# user_id -> { order_id, plan_name, plan_price, plan_validity, access_link, final_price }
_awaiting_proof: dict[int, dict] = {}

_PRODUCT_TEXT = "Hello, {first_name} 👋\n\nChoose a plan to get started 💫"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_order_id() -> str:
    return f"ORD{int(time.time())}"


def _make_upi_qr_url(order_id: str, amount: str) -> str:
    """Build a quickchart.io QR image URL that encodes the UPI payment URI."""
    upi_uri = (
        f"upi://pay?pa=paytm.s1dw5n0@pty"
        f"&pn=VC+Payment+Gateway"
        f"&tid={order_id}"
        f"&tr={order_id}"
        f"&tn=VC+Payment"
        f"&am={amount}"
        f"&cu=INR"
    )
    encoded = urllib.parse.quote(upi_uri, safe="")
    return f"https://quickchart.io/qr?text={encoded}"


def _now_ist() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")


async def _verify_payment_vc(order_id: str, amount: str) -> str:
    """
    Call the VC Store payment verification API.
    Returns "success", "pending", or "failed".
    """
    logger.info("API key loaded: %s", bool(VC_API_KEY))
    if not VC_API_URL or not VC_API_KEY:
        logger.warning("VC_API_URL or VC_API_KEY is not configured")
        return "error"

    try:
        params = {"api_key": VC_API_KEY, "order_id": order_id, "amount": amount}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                VC_API_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                raw_text = await resp.text()
                final_url = str(resp.url)
                http_status = resp.status
                logger.info("Final Request URL: %s", final_url)
                logger.info("HTTP Status: %s", http_status)
                logger.info("Raw Response: %r", raw_text)
                try:
                    data = __import__("json").loads(raw_text)
                except Exception:
                    logger.error("VC API returned non-JSON for order %s", order_id)
                    return "error"
                status = str(data.get("status", "")).lower()
                if status == "success":
                    return "success"
                elif status == "pending":
                    return "pending"
                else:
                    return "failed"
    except Exception:
        logger.exception("VC API call failed for order %s", order_id)
        return "error"


# ── Buy Now (buy:{plan_id}) ───────────────────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("buy:"))
async def callback_buy(call: CallbackQuery, bot: Bot) -> None:
    """User tapped Buy Now — load plan from DB, generate order, show payment details."""
    logger.info("BUY CALLBACK HIT")
    print("BUY CALLBACK HIT:", call.data)
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

    # Block repurchase of an already-active plan (approved + not yet expired).
    if await user_has_active_plan(user.id, plan_id):
        await call.message.answer(
            "✅ <b>You have already purchased this plan.</b>\n\n"
            "Thank you for your purchase! ❤️\n\n"
            "You already have access to this plan."
        )
        return

    await log_payment_started(bot, user.id, user.first_name, plan_title=plan["name"])

    # User clicked Buy Now — suppress any pending plan-interest reminder.
    try:
        await clear_plan_interest(user.id)
    except Exception:
        logger.exception("Failed to clear plan interest for user %s", user.id)

    # Referral discount
    referral_info = await get_user_referral_info(user.id)
    discount_pct = referral_info.get("referral_discount", 0) or 0
    original_price_str = plan["price"]

    if discount_pct > 0:
        try:
            final_price = round(float(original_price_str) * (1 - discount_pct / 100))
            final_price_str = str(final_price)
        except (ValueError, TypeError):
            final_price_str = original_price_str
    else:
        discount_pct = 0
        final_price_str = original_price_str

    price_section = (
        f"💰 <b>Original Price:</b> ₹{original_price_str}\n"
        f"🎁 <b>Referral Discount:</b> {discount_pct}%\n"
        f"💳 <b>Final Price:</b> ₹{final_price_str}"
    )

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
                final_price=final_price_str,
                referral_discount_used=discount_pct,
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

    # Payment message
    _default_tpl = (
        "💳 <b>Payment Details</b>\n\n"
        "📦 <b>Plan:</b> {plan_name}\n"
        "{price_section}\n"
        "⌛ <b>Validity:</b> {plan_validity}\n\n"
        "📲 Scan the QR code above using any UPI app.\n\n"
        "✅ <b>Pay ₹{final_price_str}</b> by scanning the <b>QR Code</b> above.\n"
        "✓ After payment, click <b>✅ I Have Paid</b>\n\n"
        "🆔 <b>Order:</b> #{order_id}"
    )
    payment_tpl = (await get_setting("payment_message")) or _default_tpl
    _fmt_kwargs = dict(
        plan_name=plan["name"],
        plan_price=plan["price"],
        plan_validity=plan["validity"],
        order_id=order_id,
        price_section=price_section,
        final_price_str=final_price_str,
    )
    try:
        payment_msg = payment_tpl.format(**_fmt_kwargs)
    except (KeyError, ValueError, IndexError):
        logger.warning("payment_message template is malformed — using default")
        payment_msg = _default_tpl.format(**_fmt_kwargs)

    # Build UPI QR and send it
    qr_url = _make_upi_qr_url(order_id, final_price_str)
    logger.info("UPI QR URL for order %s: %s", order_id, qr_url)
    try:
        await bot.send_photo(chat_id=call.message.chat.id, photo=qr_url)
    except Exception:
        logger.exception("Failed to send QR image for order %s", order_id)

    await call.message.answer(
        payment_msg, reply_markup=payment_details_keyboard(order_id)
    )

    # Store plan context for the verification handler
    _awaiting_proof[user.id] = {
        "order_id": order_id,
        "plan_name": plan["name"],
        "plan_price": plan["price"],
        "final_price": final_price_str,
        "plan_validity": plan["validity"],
        "access_link": plan["access_link"],
    }

    # Schedule abandoned-payment reminders
    _MAX_REMINDER_DELAY_MIN = 525600  # 1 year

    def _clamped_delay(raw: str, fallback: int) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return fallback
        if value <= 0:
            return fallback
        return min(value, _MAX_REMINDER_DELAY_MIN)

    first_min = _clamped_delay(await get_setting("reminder_first_delay_min", "15"), 15)
    second_min = _clamped_delay(
        await get_setting("reminder_second_delay_min", "1440"), 1440
    )
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


# ── I Have Paid → automatic VC verification ───────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("paid:"))
async def callback_i_have_paid(call: CallbackQuery, bot: Bot) -> None:
    """Verify payment automatically via VC Store API and activate instantly on success."""
    await call.answer()
    order_id = call.data.split(":", 1)[1]
    user = call.from_user

    # Restore order context: prefer in-memory, fall back to DB on cold start
    info = _awaiting_proof.get(user.id, {})
    if not info or info.get("order_id") != order_id:
        # Cold start recovery — fetch what we need from the DB
        order_doc = await get_order(order_id)
        if order_doc:
            info = {
                "order_id": order_id,
                "plan_name": order_doc.get("plan_name", ""),
                "plan_price": order_doc.get("plan_price", ""),
                "final_price": order_doc.get("final_price")
                or order_doc.get("plan_price", "0"),
                "plan_validity": order_doc.get("plan_validity", ""),
                "access_link": order_doc.get("access_link", ""),
            }
        else:
            info = {"order_id": order_id}
        _awaiting_proof[user.id] = info

    final_price = (
        info.get("final_price") or await get_order_final_price(order_id) or "0"
    )

    # Show a "verifying" message while the API call is in-flight
    verifying_msg = await call.message.answer(
        "⏳ <b>Verifying your payment...</b>\n\nPlease wait a moment."
    )

    status = await _verify_payment_vc(order_id, final_price)

    if status == "success":
        # Set to pending first (approve_order requires pending status)
        await update_order_status(order_id, "pending")
        result = await approve_order(order_id)
        _awaiting_proof.pop(user.id, None)

        if result:
            sub_end_ist = result["subscription_end"].astimezone(_IST)
            expiry_str = sub_end_ist.strftime("%d %b %Y")
            access_link = result.get("access_link", "")

            activation_text = (
                "🎉 <b>Payment Verified! Plan Activated!</b>\n\n"
                f"📦 <b>Plan:</b> {html.escape(result['plan_name'])}\n"
                f"⏳ <b>Validity:</b> {html.escape(result['plan_validity'])}\n"
                f"📅 <b>Expires:</b> {expiry_str}\n\n"
            )
            if access_link:
                activation_text += f"🔗 <b>Access Link:</b>\n{access_link}\n\n"
            activation_text += "Thank you for your purchase! ❤️"

            try:
                await verifying_msg.delete()
            except Exception:
                pass
            await call.message.answer(
                activation_text, reply_markup=main_menu_keyboard()
            )
        else:
            # Order may have already been approved (e.g. double-tap)
            await verifying_msg.edit_text(
                "✅ <b>Your plan is already activated.</b>\n\n"
                "Use /status to check your subscription.",
                reply_markup=main_menu_keyboard(),
            )

    elif status == "pending":
        await verifying_msg.edit_text(
            "⏳ Payment not received yet. Please wait a moment and try again.",
            reply_markup=payment_details_keyboard(order_id),
        )

    else:
        # failed or API error
        await verifying_msg.edit_text(
            "❌ Payment not found.",
            reply_markup=payment_details_keyboard(order_id),
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


# ── Utility ───────────────────────────────────────────────────────────────────


def clear_payment_state(user_id: int) -> None:
    """Remove any in-memory payment state for a user. Does NOT touch MongoDB."""
    _awaiting_proof.pop(user_id, None)
