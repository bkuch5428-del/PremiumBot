"""
handlers/settings.py — Settings sub-panel for the admin.

Entry:  admin_settings   callback  → show settings menu
Steps:
  settings_welcome → admin sends new welcome text   → saved
  settings_payment → admin sends new payment template → saved
  settings_qr      → admin sends a photo            → file_id saved
  settings_support → admin sends support group URL  → saved

Use /cancel to exit at any time.
"""

import html
import logging

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS
from database import get_setting, set_setting, get_all_settings
from keyboards.menu import (
    admin_panel_keyboard,
    admin_settings_keyboard,
    settings_cancel_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()

# { user_id: { "step": str } }
_state: dict[int, dict] = {}


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _in_step(step: str):
    async def _check(message: Message) -> bool:
        st = _state.get(message.from_user.id)
        return st is not None and st["step"] == step
    return _check


# ── Settings panel entry ──────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_settings")
async def cb_settings_panel(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state.pop(call.from_user.id, None)

    cfg = await get_all_settings()
    welcome_preview = html.escape((cfg.get("welcome_message") or "")[:60].replace("\n", " "))
    payment_preview = html.escape((cfg.get("payment_message") or "")[:60].replace("\n", " "))
    qr_val          = cfg.get("qr_image", "")
    support_val     = html.escape(cfg.get("support_group_url", ""))

    text = (
        "⚙️ <b>Settings</b>\n\n"
        f"📝 <b>Welcome:</b> {welcome_preview or '(default)'}…\n"
        f"💳 <b>Payment msg:</b> {payment_preview or '(default)'}…\n"
        f"🖼 <b>QR Image:</b> {'✅ set' if qr_val else '⬜ not set'}\n"
        f"👥 <b>Support:</b> {support_val or '(env default)'}\n\n"
        "Select a setting to update:"
    )
    try:
        await call.message.edit_text(text, reply_markup=admin_settings_keyboard())
    except Exception:
        await call.message.answer(text, reply_markup=admin_settings_keyboard())


# ── Back to admin panel ───────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "settings_back")
async def cb_settings_back(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    _state.pop(call.from_user.id, None)
    await call.answer()
    try:
        await call.message.edit_text(
            "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:",
            reply_markup=admin_panel_keyboard(),
        )
    except Exception:
        await call.message.answer(
            "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:",
            reply_markup=admin_panel_keyboard(),
        )


# ── Cancel (from within a settings input step) ────────────────────────────────

@router.callback_query(lambda c: c.data == "settings_cancel")
async def cb_settings_cancel(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    _state.pop(call.from_user.id, None)
    await call.answer("Cancelled.")
    await call.message.answer(
        "⚙️ <b>Settings</b>\n\nCancelled. Select a setting to update:",
        reply_markup=admin_settings_keyboard(),
    )


# ── Welcome Message ───────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "settings_welcome")
async def cb_settings_welcome(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state[call.from_user.id] = {"step": "settings:welcome"}

    current = await get_setting("welcome_message")
    await call.message.answer(
        "📝 <b>Welcome Message</b>\n\n"
        "<b>Current message:</b>\n"
        f"{html.escape(current) if current else '(not set)'}\n\n"
        "Send the new welcome message.\n"
        "HTML formatting is supported.",
        reply_markup=settings_cancel_keyboard(),
    )


@router.message(_in_step("settings:welcome"), F.text)
async def handle_welcome_input(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    _state.pop(message.from_user.id, None)
    await set_setting("welcome_message", message.text.strip())
    await message.answer(
        "✅ <b>Welcome message updated!</b>\n\n"
        "Users will see the new message the next time they start the bot.",
        reply_markup=admin_settings_keyboard(),
    )


# ── Payment Message ───────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "settings_payment")
async def cb_settings_payment(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state[call.from_user.id] = {"step": "settings:payment"}

    current = await get_setting("payment_message")
    await call.message.answer(
        "💳 <b>Payment Message</b>\n\n"
        "<b>Current message:</b>\n"
        f"{html.escape(current) if current else '(not set)'}\n\n"
        "Send the new payment instructions.\n\n"
        "You can use these placeholders and they will be filled in automatically:\n"
        "<code>{plan_name}</code>  <code>{plan_price}</code>  "
        "<code>{plan_validity}</code>  <code>{order_id}</code>\n\n"
        "HTML formatting is supported.",
        reply_markup=settings_cancel_keyboard(),
    )


@router.message(_in_step("settings:payment"), F.text)
async def handle_payment_input(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    _state.pop(message.from_user.id, None)
    await set_setting("payment_message", message.text.strip())
    await message.answer(
        "✅ <b>Payment message updated!</b>\n\n"
        "New orders will use the updated message.",
        reply_markup=admin_settings_keyboard(),
    )


# ── QR Image ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "settings_qr")
async def cb_settings_qr(call: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state[call.from_user.id] = {"step": "settings:qr"}

    current_file_id = await get_setting("qr_image")
    if current_file_id:
        try:
            await call.message.answer_photo(
                photo=current_file_id,
                caption="🖼 <b>Current QR Image</b>\n\nSend a new photo to replace it.",
                reply_markup=settings_cancel_keyboard(),
            )
            return
        except Exception:
            pass  # fall through if file_id is stale / URL

    await call.message.answer(
        "🖼 <b>QR Image</b>\n\n"
        "No QR image is currently saved in the database.\n\n"
        "Send a photo of your UPI QR code and it will be saved.",
        reply_markup=settings_cancel_keyboard(),
    )


@router.message(_in_step("settings:qr"), F.photo)
async def handle_qr_photo(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    _state.pop(message.from_user.id, None)
    # Always use the largest available size for best quality
    file_id = message.photo[-1].file_id
    await set_setting("qr_image", file_id)
    await message.answer(
        "✅ <b>QR image updated!</b>\n\n"
        "The new QR code will be shown to users during checkout.",
        reply_markup=admin_settings_keyboard(),
    )


@router.message(_in_step("settings:qr"))
async def handle_qr_wrong_type(message: Message) -> None:
    """Catch non-photo messages when QR step is active."""
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    await message.answer(
        "⚠️ Please send a <b>photo</b> of the QR code.",
        reply_markup=settings_cancel_keyboard(),
    )


# ── Support Group ─────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "settings_support")
async def cb_settings_support(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state[call.from_user.id] = {"step": "settings:support"}

    current = await get_setting("support_group_url")
    await call.message.answer(
        "👥 <b>Support Group</b>\n\n"
        f"<b>Current link:</b> {html.escape(current) if current else '(using env default)'}\n\n"
        "Send the new support group link (e.g. https://t.me/+xxxxx):",
        reply_markup=settings_cancel_keyboard(),
    )


@router.message(_in_step("settings:support"), F.text)
async def handle_support_input(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    _state.pop(message.from_user.id, None)
    await set_setting("support_group_url", message.text.strip())
    await message.answer(
        "✅ <b>Support group link updated!</b>",
        reply_markup=admin_settings_keyboard(),
    )
