"""
log_channel.py — centralised helpers for posting activity events to the log channel.

To add a new event type, define a new async function here and call it from
the relevant handler. All functions silently swallow errors so a log failure
never disrupts the user-facing flow.
"""

import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot

from config import LOG_CHANNEL_ID

logger = logging.getLogger(__name__)

# IST = UTC+5:30
_IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")


async def _send(bot: Bot, text: str) -> None:
    """Internal helper — posts to the log channel, never raises."""
    try:
        await bot.send_message(chat_id=LOG_CHANNEL_ID, text=text)
    except Exception:
        logger.exception("Failed to post to log channel")


# ── Event: new user ───────────────────────────────────────────────────────────

async def log_new_user(bot: Bot, user_id: int, first_name: str, username: str | None) -> None:
    uname = f"@{username}" if username else "None"
    text = (
        "🆕 <b>New User</b>\n\n"
        f"👤 Name: {first_name}\n"
        f"📛 Username: {uname}\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"🕒 Time: {_now_ist()}"
    )
    await _send(bot, text)


# ── Event: plan selected ──────────────────────────────────────────────────────

async def log_plan_selected(
    bot: Bot,
    user_id: int,
    first_name: str,
    plan_title: str = "💦 𝐑𝐞𝐚𝐥 𝐈𝐧𝐝!𝐚𝐧 𝐃ē𝐬𝐢 𝐏𝟎𝐫𝐧 🫦",
    price: str = "₹49 / 30 Days",
) -> None:
    text = (
        "💎 <b>Plan Selected</b>\n\n"
        f"👤 Name: {first_name}\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"📦 Plan: {plan_title}\n"
        f"💰 Price: {price}"
    )
    await _send(bot, text)


# ── Event: payment started ────────────────────────────────────────────────────

async def log_payment_started(
    bot: Bot,
    user_id: int,
    first_name: str,
    plan_title: str = "💦 𝐑𝐞𝐚𝐥 𝐈𝐧𝐝!𝐚𝐧 𝐃ē𝐬𝐢 𝐏𝟎𝐫𝐧 🫦",
) -> None:
    text = (
        "💳 <b>Payment Started</b>\n\n"
        f"👤 Name: {first_name}\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"📦 Plan: {plan_title}"
    )
    await _send(bot, text)
