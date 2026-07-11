"""
reminder_scheduler.py — background loop for abandoned-payment reminders.

The bot is a single-process aiogram poller with MongoDB and no task queue, so
reminders are handled with a simple asyncio loop: every CHECK_INTERVAL_SECONDS
it looks in the `reminders` collection for schedules whose first/second
reminder is due and not yet sent, sends them, and marks them sent.

Schedules are created/replaced in handlers/payment.py (callback_buy) and
cancelled in database.py (approve_order) and handlers/payment.py (reject /
cancel_order / cancel_proof). This module only sends what's already due.

Launch with `asyncio.create_task(reminder_scheduler.run(bot))` — it never
returns on its own.
"""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot

from database import (
    get_setting,
    get_due_first_reminders,
    get_due_second_reminders,
    mark_first_reminder_sent,
    mark_second_reminder_sent,
)
from keyboards.menu import reminder_buy_now_keyboard

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 30

_DEFAULT_REMINDER_FIRST_MESSAGE = (
    "🔔 <b>Reminder</b>\n\n"
    "You still haven't completed payment for <b>{plan_name}</b>.\n\n"
    "💰 <b>Price:</b> ₹{plan_price}\n"
    "⏳ <b>Validity:</b> {plan_validity}\n\n"
    "Tap <b>Buy Now</b> below and complete your payment to activate your plan!"
)

_DEFAULT_REMINDER_SECOND_MESSAGE = (
    "🔔 <b>Last Chance!</b>\n\n"
    "Your payment for <b>{plan_name}</b> is still incomplete.\n\n"
    "💰 <b>Price:</b> ₹{plan_price}\n"
    "⏳ <b>Validity:</b> {plan_validity}\n\n"
    "Tap <b>Buy Now</b> below before this offer slips away!"
)


def _render(template: str, doc: dict, default: str) -> str:
    kwargs = dict(
        plan_name=doc.get("plan_name", ""),
        plan_price=doc.get("plan_price", ""),
        plan_validity=doc.get("plan_validity", ""),
    )
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        logger.warning("reminder message template is malformed — using default")
        return default.format(**kwargs)


async def run(bot: Bot) -> None:
    """Background loop — never returns. Launch with asyncio.create_task()."""
    logger.info("Payment reminder scheduler started (interval=%ss)", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await _tick(bot)
        except Exception:
            logger.exception("Reminder scheduler tick failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _tick(bot: Bot) -> None:
    enabled = (await get_setting("reminder_enabled", "1")) == "1"
    if not enabled:
        return

    now = datetime.now(timezone.utc)
    first_template = (await get_setting("reminder_first_message")) or _DEFAULT_REMINDER_FIRST_MESSAGE
    second_template = (await get_setting("reminder_second_message")) or _DEFAULT_REMINDER_SECOND_MESSAGE

    for doc in await get_due_first_reminders(now):
        user_id = doc["_id"]
        order_id = doc.get("order_id")
        plan_id = doc.get("plan_id")
        try:
            await bot.send_message(
                chat_id=user_id,
                text=_render(first_template, doc, _DEFAULT_REMINDER_FIRST_MESSAGE),
                reply_markup=reminder_buy_now_keyboard(plan_id) if plan_id is not None else None,
            )
        except Exception:
            logger.warning("Failed to send first reminder to user %s", user_id)
        # Mark sent regardless of delivery outcome — a blocked/invalid chat
        # should not be retried forever. Scoped to order_id so a schedule
        # replaced by a repeat Buy Now in the meantime is left untouched.
        await mark_first_reminder_sent(user_id, order_id)

    for doc in await get_due_second_reminders(now):
        user_id = doc["_id"]
        order_id = doc.get("order_id")
        plan_id = doc.get("plan_id")
        try:
            await bot.send_message(
                chat_id=user_id,
                text=_render(second_template, doc, _DEFAULT_REMINDER_SECOND_MESSAGE),
                reply_markup=reminder_buy_now_keyboard(plan_id) if plan_id is not None else None,
            )
        except Exception:
            logger.warning("Failed to send final reminder to user %s", user_id)
        await mark_second_reminder_sent(user_id, order_id)
