"""
handlers/admin.py — /admin command and full admin panel wizard.

State machine is kept in module-level dicts (no FSM storage needed in main.py).

Steps
─────
add:name         → add:price → add:validity → add:demo → add:access → add:confirm
edit:select      → edit:field → edit:value
delete:select    → delete:confirm
demo:select      → demo:videos  (admin sends media, clicks Done)
link:select      → link:value
buymsg:select    → buymsg:value
startdemo:videos (admin forwards from demo channel, clicks Done)
broadcast:msg
"""

import asyncio
import logging

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramForbiddenError

from config import ADMIN_IDS, SOURCE_CHANNEL_ID
import handlers.settings as _settings_module  # for cross-module state clearing
from database import (
    create_plan,
    get_all_plans,
    get_plan,
    update_plan,
    delete_plan,
    get_stats,
    get_pending_orders,
    get_all_user_ids,
    get_setting,
    set_setting,
    get_start_demo,
    set_start_demo_ids,
)
from keyboards.menu import (
    admin_panel_keyboard,
    admin_plan_list_keyboard,
    admin_edit_fields_keyboard,
    admin_delete_confirm_keyboard,
    admin_demo_done_keyboard,
    admin_confirm_save_keyboard,
    main_menu_keyboard,
    start_demo_settings_keyboard,
    start_demo_done_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()

# ── State storage ─────────────────────────────────────────────────────────────
# { user_id: { "step": str, "data": dict } }
_state: dict[int, dict] = {}

_STEPS_LABEL = {
    "add:name":     "📝 Enter the plan name:",
    "add:price":    "💰 Enter the price (e.g. 49):",
    "add:validity": "⏳ Enter validity (e.g. 30 Days):",
    "add:demo":     (
        "🎥 <b>Forward</b> demo messages from the source channel.\n\n"
        "Go to your source channel → select messages → forward them here.\n"
        "When you're done, click <b>✅ Done</b> below."
    ),
    "add:access":   "🔗 Enter the access link (channel/group invite URL):",
}

EDIT_FIELD_LABELS = {
    "name":        "📝 Enter the new plan name:",
    "price":       "💰 Enter the new price (e.g. 49):",
    "validity":    "⏳ Enter new validity (e.g. 30 Days):",
    "access_link": "🔗 Enter the new access link:",
}


# ── Guards ────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _in_state(step: str):
    """Filter: user must be in the given state step."""
    async def _check(message: Message) -> bool:
        st = _state.get(message.from_user.id)
        return st is not None and st["step"] == step
    return _check


def _in_any_admin_state(message: Message) -> bool:
    return message.from_user.id in _state


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _go_panel(target, bot: Bot | None = None) -> None:
    """Send or edit-to the main admin panel."""
    text = "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:"
    kb = admin_panel_keyboard()
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except Exception:
            await target.message.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


async def _cancel(call: CallbackQuery) -> None:
    _state.pop(call.from_user.id, None)
    await call.answer("Cancelled.")
    await _go_panel(call)


# ── /admin command ────────────────────────────────────────────────────────────

@router.message(Command("admin", ignore_case=True))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ You are not authorised to use this command.")
        return
    _state.pop(message.from_user.id, None)
    await _go_panel(message)


# ── /cancel — global escape from any admin wizard state ──────────────────────

@router.message(Command("cancel", ignore_case=True))
async def cmd_cancel(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return  # not an admin — let other handlers deal with it
    uid = message.from_user.id
    # Clear state from both admin wizard AND settings panel
    in_admin    = uid in _state
    in_settings = uid in _settings_module._state
    _state.pop(uid, None)
    _settings_module._state.pop(uid, None)
    if in_admin or in_settings:
        await message.answer(
            "✅ Cancelled.",
            reply_markup=admin_panel_keyboard(),
        )
    else:
        await message.answer("No active wizard to cancel.")


# ── Cancel (global) ───────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_cancel")
async def cb_cancel(call: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await _cancel(call)


# ── Admin panel entry buttons ─────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_stats")
async def cb_stats(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    s = await get_stats()

    # Format revenue: show as integer when it's a whole number, else 2 d.p.
    rev = s["total_revenue"]
    rev_str = f"₹{int(rev):,}" if rev == int(rev) else f"₹{rev:,.2f}"

    await call.message.edit_text(
        "📊 <b>Statistics</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥  <b>Total Users</b>              {s['total_users']}\n"
        f"📦  <b>Total Plans</b>              {s['total_plans']}\n\n"
        f"💰  <b>Total Revenue</b>            {rev_str}\n\n"
        f"✅  <b>Active Subscriptions</b>     {s['active_subs']}\n"
        f"❌  <b>Expired Subscriptions</b>    {s['expired_subs']}\n\n"
        f"⏳  <b>Pending Payments</b>         {s['pending']}\n"
        f"✔️  <b>Approved Orders</b>          {s['approved_orders']}\n"
        f"✖️  <b>Rejected Orders</b>          {s['rejected_orders']}\n"
        "━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(lambda c: c.data == "admin_plans")
async def cb_plans_list(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.edit_text(
            "📦 <b>Plans</b>\n\nNo plans found. Use ➕ Add Plan to create one.",
            reply_markup=admin_panel_keyboard(),
        )
        return
    lines = []
    for p in plans:
        lines.append(
            f"📦 <b>{p['name']}</b>\n"
            f"   💰 ₹{p['price']} / {p['validity']}\n"
            f"   🔗 {p['access_link'] or '—'}"
        )
    text = "📦 <b>All Plans</b>\n\n" + "\n\n".join(lines)
    await call.message.edit_text(text, reply_markup=admin_panel_keyboard())


@router.callback_query(lambda c: c.data == "admin_pending")
async def cb_pending(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    orders = await get_pending_orders()
    if not orders:
        await call.message.edit_text(
            "📋 <b>Pending Payments</b>\n\nNo pending payments right now.",
            reply_markup=admin_panel_keyboard(),
        )
        return
    lines = [
        f"🆔 #{o['order_id']}\n"
        f"👤 User: <code>{o['user_id']}</code>\n"
        f"📦 {o['plan_name']} — ₹{o['plan_price']}\n"
        f"🕒 {o['created_at']}"
        for o in orders
    ]
    text = "📋 <b>Pending Payments</b>\n\n" + "\n\n".join(lines)
    await call.message.edit_text(text, reply_markup=admin_panel_keyboard())


# ── Broadcast ─────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_broadcast")
async def cb_broadcast_start(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state[call.from_user.id] = {"step": "broadcast:msg", "data": {}}
    await call.message.edit_text(
        "📢 <b>Broadcast</b>\n\n"
        "Send the message you want to broadcast to all users.\n"
        "Supports text, photos, and videos.\n\n"
        "Type /cancel to abort.",
        reply_markup=None,
    )


@router.message(_in_state("broadcast:msg"), F.text | F.photo | F.video)
async def handle_broadcast_msg(message: Message, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        return
    if message.text and message.text.startswith("/"):
        return
    _state.pop(message.from_user.id, None)

    user_ids = await get_all_user_ids()
    sent = failed = blocked = 0

    status_msg = await message.answer(
        f"📢 Broadcasting to {len(user_ids)} users… please wait."
    )

    for uid in user_ids:
        try:
            if message.photo:
                await bot.send_photo(
                    chat_id=uid,
                    photo=message.photo[-1].file_id,
                    caption=message.caption or "",
                )
            elif message.video:
                await bot.send_video(
                    chat_id=uid,
                    video=message.video.file_id,
                    caption=message.caption or "",
                )
            else:
                await bot.send_message(chat_id=uid, text=message.text or "")
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msg/s to stay under rate limits

    await status_msg.edit_text(
        "📢 <b>Broadcast Completed</b>\n\n"
        f"✅ <b>Successfully Sent:</b>  {sent}\n"
        f"❌ <b>Failed:</b>            {failed}\n"
        f"🚫 <b>Blocked Users:</b>     {blocked}"
    )
    await message.answer("🛠 <b>ADMIN PANEL</b>\n\nSelect an option:", reply_markup=admin_panel_keyboard())


# ── Add Plan wizard ───────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_add")
async def cb_add_start(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state[call.from_user.id] = {"step": "add:name", "data": {}}
    await call.message.edit_text(
        "➕ <b>Add Plan — Step 1/5</b>\n\n" + _STEPS_LABEL["add:name"],
        reply_markup=None,
    )


@router.message(_in_state("add:name"), F.text)
async def add_step_name(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    _state[message.from_user.id]["data"]["name"] = message.text.strip()
    _state[message.from_user.id]["step"] = "add:price"
    await message.answer("➕ <b>Add Plan — Step 2/5</b>\n\n" + _STEPS_LABEL["add:price"])


@router.message(_in_state("add:price"), F.text)
async def add_step_price(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    _state[message.from_user.id]["data"]["price"] = message.text.strip()
    _state[message.from_user.id]["step"] = "add:validity"
    await message.answer("➕ <b>Add Plan — Step 3/5</b>\n\n" + _STEPS_LABEL["add:validity"])


@router.message(_in_state("add:validity"), F.text)
async def add_step_validity(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    _state[message.from_user.id]["data"]["validity"] = message.text.strip()
    _state[message.from_user.id]["data"]["demo_ids"] = []
    _state[message.from_user.id]["step"] = "add:demo"
    await message.answer(
        "➕ <b>Add Plan — Step 4/5</b>\n\n" + _STEPS_LABEL["add:demo"],
        reply_markup=admin_demo_done_keyboard(0),
    )


@router.message(_in_state("add:demo"))
async def add_step_demo_media(message: Message) -> None:
    """
    Accept forwarded messages from the source channel during the demo step.
    We store the original message ID from the source channel (forward_from_message_id),
    not the admin-chat message ID, so copy_messages() works correctly later.
    """
    if not _is_admin(message.from_user.id):
        return
    if message.text and message.text.startswith("/"):
        return

    st = _state[message.from_user.id]

    # Must be a forward from a channel so we can resolve the source message ID.
    fwd_id = getattr(message, "forward_from_message_id", None)
    fwd_chat = getattr(message, "forward_from_chat", None)

    if fwd_id is None or fwd_chat is None:
        await message.answer(
            "⚠️ Please <b>forward</b> the demo videos directly from the source channel.\n"
            "Do not upload new files — forward existing messages from the channel."
        )
        return

    st["data"]["demo_ids"].append(fwd_id)
    # Store (or confirm) the source channel ID from the first forwarded message.
    if not st["data"].get("source_channel_id"):
        st["data"]["source_channel_id"] = str(fwd_chat.id)

    count = len(st["data"]["demo_ids"])
    try:
        await message.answer(
            f"✅ Got it! {count} message{'s' if count != 1 else ''} forwarded so far.\n"
            "Forward more, or click <b>✅ Done</b> when finished.",
            reply_markup=admin_demo_done_keyboard(count),
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data == "admin_demo_done")
async def cb_demo_done(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    st = _state.get(call.from_user.id)
    if not st:
        await call.answer("No active wizard.", show_alert=True)
        return
    await call.answer()
    step = st["step"]

    if step == "add:demo":
        if not st["data"].get("demo_ids"):
            await call.message.answer(
                "⚠️ No demo videos captured yet. Please forward at least one message from the source channel."
            )
            return
        # Carry forward the source channel resolved from forwarded messages.
        if st["data"].get("source_channel_id"):
            st["data"]["resolved_source_channel"] = st["data"]["source_channel_id"]
        st["step"] = "add:access"
        await call.message.answer(
            "➕ <b>Add Plan — Step 5/5</b>\n\n" + _STEPS_LABEL["add:access"]
        )

    elif step == "demo:videos":
        # Changing demo videos for existing plan
        plan_id = st["data"]["plan_id"]
        new_ids = st["data"]["demo_ids"]
        if not new_ids:
            await call.message.answer(
                "⚠️ No demo videos captured yet. Please forward at least one message from the source channel."
            )
            return
        update_kwargs: dict = {"demo_message_ids": new_ids}
        # If forwarded messages reveal a source channel, update it too.
        if st["data"].get("source_channel_id"):
            update_kwargs["source_channel_id"] = st["data"]["source_channel_id"]
        await update_plan(plan_id, **update_kwargs)
        _state.pop(call.from_user.id, None)
        count = len(new_ids)
        await call.message.answer(
            f"✅ Demo videos updated ({count} message ID{'s' if count != 1 else ''} saved).",
            reply_markup=admin_panel_keyboard(),
        )


@router.message(_in_state("add:access"), F.text)
async def add_step_access(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    st = _state[message.from_user.id]
    st["data"]["access_link"] = message.text.strip()
    st["step"] = "add:confirm"

    d = st["data"]
    count = len(d.get("demo_ids", []))
    await message.answer(
        "➕ <b>Add Plan — Confirmation</b>\n\n"
        f"📝 <b>Name:</b> {d['name']}\n"
        f"💰 <b>Price:</b> ₹{d['price']}\n"
        f"⏳ <b>Validity:</b> {d['validity']}\n"
        f"🎥 <b>Demo IDs:</b> {count} message{'s' if count != 1 else ''}\n"
        f"🔗 <b>Access Link:</b> {d['access_link']}\n\n"
        "Save this plan?",
        reply_markup=admin_confirm_save_keyboard(),
    )


@router.callback_query(lambda c: c.data == "admin_save")
async def cb_save_plan(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    st = _state.pop(call.from_user.id, None)
    if not st or st["step"] != "add:confirm":
        await call.answer("No plan to save.", show_alert=True)
        return
    await call.answer()
    d = st["data"]
    # Use the source channel resolved from forwarded demo messages;
    # fall back to the global SOURCE_CHANNEL_ID from config.
    source = d.get("resolved_source_channel") or SOURCE_CHANNEL_ID
    await create_plan(
        name=d["name"],
        price=d["price"],
        validity=d["validity"],
        demo_message_ids=d.get("demo_ids", []),
        source_channel_id=source,
        access_link=d["access_link"],
    )
    await call.message.edit_text(
        f"✅ Plan <b>{d['name']}</b> saved successfully!",
        reply_markup=admin_panel_keyboard(),
    )


# ── Edit Plan wizard ──────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_edit")
async def cb_edit_start(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.edit_text(
            "✏️ <b>Edit Plan</b>\n\nNo plans found.",
            reply_markup=admin_panel_keyboard(),
        )
        return
    _state[call.from_user.id] = {"step": "edit:select", "data": {}}
    await call.message.edit_text(
        "✏️ <b>Edit Plan</b>\n\nSelect a plan to edit:",
        reply_markup=admin_plan_list_keyboard(plans, "admin_ep"),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin_ep:"))
async def cb_edit_plan_selected(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    plan_id = int(call.data.split(":", 1)[1])
    await call.answer()
    plan = await get_plan(plan_id)
    if not plan:
        await call.answer("Plan not found.", show_alert=True)
        return
    _state[call.from_user.id] = {"step": "edit:field", "data": {"plan_id": plan_id}}
    await call.message.edit_text(
        f"✏️ <b>Edit Plan:</b> {plan['name']}\n\nSelect a field to edit:",
        reply_markup=admin_edit_fields_keyboard(plan_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin_ef:"))
async def cb_edit_field_selected(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    _, plan_id_str, field = call.data.split(":", 2)
    plan_id = int(plan_id_str)
    await call.answer()
    _state[call.from_user.id] = {
        "step": "edit:value",
        "data": {"plan_id": plan_id, "field": field},
    }
    await call.message.edit_text(
        f"✏️ <b>Edit Field</b>\n\n{EDIT_FIELD_LABELS.get(field, 'Enter new value:')}",
        reply_markup=None,
    )


@router.message(_in_state("edit:value"), F.text)
async def handle_edit_value(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    st = _state.pop(message.from_user.id, None)
    if not st:
        return
    plan_id = st["data"]["plan_id"]
    field = st["data"]["field"]
    await update_plan(plan_id, **{field: message.text.strip()})
    await message.answer(
        f"✅ <b>{field.replace('_', ' ').title()}</b> updated successfully!",
        reply_markup=admin_panel_keyboard(),
    )


# ── Delete Plan wizard ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_delete")
async def cb_delete_start(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.edit_text(
            "🗑 <b>Delete Plan</b>\n\nNo plans found.",
            reply_markup=admin_panel_keyboard(),
        )
        return
    _state[call.from_user.id] = {"step": "delete:select", "data": {}}
    await call.message.edit_text(
        "🗑 <b>Delete Plan</b>\n\nSelect a plan to delete:",
        reply_markup=admin_plan_list_keyboard(plans, "admin_dp"),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin_dp:"))
async def cb_delete_plan_selected(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    plan_id = int(call.data.split(":", 1)[1])
    await call.answer()
    plan = await get_plan(plan_id)
    if not plan:
        await call.answer("Plan not found.", show_alert=True)
        return
    _state[call.from_user.id] = {"step": "delete:confirm", "data": {"plan_id": plan_id}}
    await call.message.edit_text(
        f"🗑 <b>Delete Plan</b>\n\n"
        f"Are you sure you want to delete <b>{plan['name']}</b>?\n"
        f"This cannot be undone.",
        reply_markup=admin_delete_confirm_keyboard(plan_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin_dc:"))
async def cb_delete_confirm(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    plan_id = int(call.data.split(":", 1)[1])
    await call.answer()
    plan = await get_plan(plan_id)
    name = plan["name"] if plan else f"#{plan_id}"
    await delete_plan(plan_id)
    _state.pop(call.from_user.id, None)
    await call.message.edit_text(
        f"✅ Plan <b>{name}</b> has been deleted.",
        reply_markup=admin_panel_keyboard(),
    )


# ── Change Demo Videos ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_demo")
async def cb_demo_start(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.edit_text(
            "🎥 <b>Change Demo Videos</b>\n\nNo plans found.",
            reply_markup=admin_panel_keyboard(),
        )
        return
    _state[call.from_user.id] = {"step": "demo:select", "data": {}}
    await call.message.edit_text(
        "🎥 <b>Change Demo Videos</b>\n\nSelect a plan:",
        reply_markup=admin_plan_list_keyboard(plans, "admin_dmp"),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin_dmp:"))
async def cb_demo_plan_selected(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    plan_id = int(call.data.split(":", 1)[1])
    await call.answer()
    plan = await get_plan(plan_id)
    if not plan:
        await call.answer("Plan not found.", show_alert=True)
        return
    _state[call.from_user.id] = {
        "step": "demo:videos",
        "data": {"plan_id": plan_id, "demo_ids": []},
    }
    await call.message.edit_text(
        f"🎥 <b>Change Demo Videos: {plan['name']}</b>\n\n"
        "Send the new demo videos (photos/videos) one by one or as an album.\n"
        "Click <b>✅ Done</b> when finished. This will replace the old demo videos.",
        reply_markup=admin_demo_done_keyboard(0),
    )


@router.message(_in_state("demo:videos"))
async def handle_demo_videos_media(message: Message) -> None:
    """Accept forwarded messages from the source channel when changing demo videos."""
    if not _is_admin(message.from_user.id):
        return
    if message.text and message.text.startswith("/"):
        return

    st = _state[message.from_user.id]

    fwd_id = getattr(message, "forward_from_message_id", None)
    fwd_chat = getattr(message, "forward_from_chat", None)

    if fwd_id is None or fwd_chat is None:
        await message.answer(
            "⚠️ Please <b>forward</b> the demo videos directly from the source channel.\n"
            "Do not upload new files — forward existing messages from the channel."
        )
        return

    st["data"]["demo_ids"].append(fwd_id)
    if not st["data"].get("source_channel_id"):
        st["data"]["source_channel_id"] = str(fwd_chat.id)

    count = len(st["data"]["demo_ids"])
    try:
        await message.answer(
            f"✅ {count} message{'s' if count != 1 else ''} forwarded. Forward more or click Done.",
            reply_markup=admin_demo_done_keyboard(count),
        )
    except Exception:
        pass


# ── Start Demo Settings ───────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_startdemo")
async def cb_startdemo_panel(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state.pop(call.from_user.id, None)
    cfg = await get_start_demo()
    ids = cfg["ids"]
    status_line = (
        f"📹 <b>Start Demo Settings</b>\n\n"
        f"Status: {'✅ Enabled' if cfg['enabled'] else '🚫 Disabled'}\n"
        f"Videos saved: {len(ids)}\n\n"
        "Select an option:"
    )
    try:
        await call.message.edit_text(status_line, reply_markup=start_demo_settings_keyboard(cfg["enabled"]))
    except Exception:
        await call.message.answer(status_line, reply_markup=start_demo_settings_keyboard(cfg["enabled"]))


@router.callback_query(lambda c: c.data == "admin_sd_noop")
async def cb_sd_noop(call: CallbackQuery) -> None:
    await call.answer()  # status badge tap — do nothing


@router.callback_query(lambda c: c.data == "admin_sd_enable")
async def cb_sd_enable(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await set_setting("start_demo_enabled", "1")
    await call.answer("✅ Start demo videos enabled.", show_alert=True)
    cfg = await get_start_demo()
    try:
        await call.message.edit_text(
            f"📹 <b>Start Demo Settings</b>\n\nStatus: ✅ Enabled\nVideos saved: {len(cfg['ids'])}\n\nSelect an option:",
            reply_markup=start_demo_settings_keyboard(True),
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data == "admin_sd_disable")
async def cb_sd_disable(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await set_setting("start_demo_enabled", "0")
    await call.answer("🚫 Start demo videos disabled.", show_alert=True)
    cfg = await get_start_demo()
    try:
        await call.message.edit_text(
            f"📹 <b>Start Demo Settings</b>\n\nStatus: 🚫 Disabled\nVideos saved: {len(cfg['ids'])}\n\nSelect an option:",
            reply_markup=start_demo_settings_keyboard(False),
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data == "admin_sd_change")
async def cb_sd_change(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    _state[call.from_user.id] = {"step": "startdemo:videos", "data": {"demo_ids": []}}
    try:
        await call.message.edit_text(
            "📹 <b>Change Start Demo Videos</b>\n\n"
            f"Forward the start demo videos from the configured Demo Videos Channel "
            f"(<code>{SOURCE_CHANNEL_ID}</code>).\n\n"
            "When finished, press <b>✅ Done</b>.",
            reply_markup=start_demo_done_keyboard(0),
        )
    except Exception:
        await call.message.answer(
            "📹 <b>Change Start Demo Videos</b>\n\n"
            f"Forward the start demo videos from the configured Demo Videos Channel "
            f"(<code>{SOURCE_CHANNEL_ID}</code>).\n\n"
            "When finished, press <b>✅ Done</b>.",
            reply_markup=start_demo_done_keyboard(0),
        )


@router.message(_in_state("startdemo:videos"))
async def handle_startdemo_media(message: Message) -> None:
    """Accept forwarded messages from the demo videos channel."""
    if not _is_admin(message.from_user.id):
        return
    if message.text and message.text.startswith("/"):
        return

    st = _state[message.from_user.id]

    fwd_id   = getattr(message, "forward_from_message_id", None)
    fwd_chat = getattr(message, "forward_from_chat", None)

    if fwd_id is None or fwd_chat is None:
        await message.answer(
            "⚠️ Please <b>forward</b> messages directly from the Demo Videos Channel.\n"
            "Do not upload new files — forward existing messages from the channel."
        )
        return

    # Verify the message originates from the configured demo videos channel.
    # Fail closed: if SOURCE_CHANNEL_ID is not a valid integer, reject all forwards.
    try:
        expected_id = int(SOURCE_CHANNEL_ID)
    except (ValueError, TypeError):
        await message.answer(
            "⚠️ The Demo Videos Channel is not configured correctly on this bot.\n"
            "Please contact the bot owner to set <code>SOURCE_CHANNEL_ID</code>."
        )
        return

    if fwd_chat.id != expected_id:
        await message.answer(
            f"⚠️ That message is not from the configured Demo Videos Channel "
            f"(<code>{SOURCE_CHANNEL_ID}</code>).\n\n"
            "Please forward messages only from that channel."
        )
        return

    st["data"]["demo_ids"].append(fwd_id)
    if not st["data"].get("source_channel_id"):
        st["data"]["source_channel_id"] = str(fwd_chat.id)

    count = len(st["data"]["demo_ids"])
    try:
        await message.answer(
            f"✅ Got it! {count} video{'s' if count != 1 else ''} collected so far.\n"
            "Forward more, or press <b>✅ Done</b> when finished.",
            reply_markup=start_demo_done_keyboard(count),
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data == "admin_sd_done")
async def cb_sd_done(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    st = _state.get(call.from_user.id)
    if not st or st.get("step") != "startdemo:videos":
        await call.answer("No active wizard.", show_alert=True)
        return

    ids = st["data"].get("demo_ids", [])
    if not ids:
        await call.answer(
            "⚠️ No videos collected yet. Forward at least one message from the channel.",
            show_alert=True,
        )
        return

    source = st["data"].get("source_channel_id") or SOURCE_CHANNEL_ID
    _state.pop(call.from_user.id, None)
    await call.answer()

    await set_start_demo_ids(ids, source)
    count = len(ids)
    await call.message.edit_text(
        f"✅ <b>Start demo videos updated!</b>\n\n"
        f"{count} video{'s' if count != 1 else ''} saved.\n\n"
        "They will be sent to users on /start when the feature is enabled.",
        reply_markup=admin_panel_keyboard(),
    )


# ── Edit Plan QR ─────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_planqr")
async def cb_planqr_start(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.edit_text(
            "💳 <b>Edit Plan QR</b>\n\nNo plans found.",
            reply_markup=admin_panel_keyboard(),
        )
        return
    _state[call.from_user.id] = {"step": "planqr:select", "data": {}}
    await call.message.edit_text(
        "💳 <b>Edit Plan QR</b>\n\nSelect a plan:",
        reply_markup=admin_plan_list_keyboard(plans, "admin_pq"),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin_pq:"))
async def cb_planqr_plan_selected(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    try:
        plan_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("⚠️ Invalid plan.", show_alert=True)
        return
    await call.answer()
    plan = await get_plan(plan_id)
    if not plan:
        await call.answer("Plan not found.", show_alert=True)
        return
    _state[call.from_user.id] = {"step": "planqr:photo", "data": {"plan_id": plan_id}}
    has_qr = bool(plan.get("qr_image"))
    await call.message.edit_text(
        f"💳 <b>Edit Plan QR: {plan['name']}</b>\n\n"
        f"Current QR: {'✅ Set' if has_qr else '⬜ Not set'}\n\n"
        "Send the new QR image for this plan.",
        reply_markup=None,
    )


@router.message(_in_state("planqr:photo"), F.photo)
async def handle_planqr_photo(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    st = _state.pop(message.from_user.id, None)
    if not st:
        return
    plan_id = st["data"]["plan_id"]
    file_id = message.photo[-1].file_id
    await update_plan(plan_id, qr_image=file_id)
    await message.answer(
        "✅ QR updated successfully.",
        reply_markup=admin_panel_keyboard(),
    )


@router.message(_in_state("planqr:photo"))
async def handle_planqr_wrong_type(message: Message) -> None:
    """Catch non-photo messages when planqr:photo step is active."""
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    await message.answer("⚠️ Please send a <b>photo</b> of the QR code.")


# ── Edit Plan Buy Message ─────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_buymsg")
async def cb_buymsg_start(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.edit_text(
            "📝 <b>Edit Plan Buy Message</b>\n\nNo plans found.",
            reply_markup=admin_panel_keyboard(),
        )
        return
    _state[call.from_user.id] = {"step": "buymsg:select", "data": {}}
    await call.message.edit_text(
        "📝 <b>Edit Plan Buy Message</b>\n\nSelect a plan:",
        reply_markup=admin_plan_list_keyboard(plans, "admin_bm"),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin_bm:"))
async def cb_buymsg_plan_selected(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    plan_id = int(call.data.split(":", 1)[1])
    await call.answer()
    plan = await get_plan(plan_id)
    if not plan:
        await call.answer("Plan not found.", show_alert=True)
        return
    _state[call.from_user.id] = {
        "step": "buymsg:value",
        "data": {"plan_id": plan_id},
    }
    current = plan.get("buy_message", "")
    await call.message.edit_text(
        f"📝 <b>Edit Buy Message: {plan['name']}</b>\n\n"
        "<b>Current message:</b>\n"
        f"{current if current else '(not set — using default)'}\n\n"
        "Send the new complete Buy Message for this plan (title, description, "
        "price, validity, emojis, formatting, line breaks, etc. — all in one message).\n\n"
        "You can use these placeholders and they will be filled in automatically:\n"
        "<code>{plan_name}</code>  <code>{plan_price}</code>  <code>{plan_validity}</code>\n\n"
        "HTML formatting is supported.",
        reply_markup=None,
    )


@router.message(_in_state("buymsg:value"), F.text)
async def handle_buymsg_value(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    st = _state.pop(message.from_user.id, None)
    if not st:
        return
    plan_id = st["data"]["plan_id"]
    await update_plan(plan_id, buy_message=message.text.strip())
    await message.answer(
        "✅ <b>Buy message updated for this plan!</b>\n\n"
        "Users will see it the next time they select this plan.",
        reply_markup=admin_panel_keyboard(),
    )


# ── Change Access Link ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin_link")
async def cb_link_start(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    await call.answer()
    plans = await get_all_plans()
    if not plans:
        await call.message.edit_text(
            "🔗 <b>Change Access Link</b>\n\nNo plans found.",
            reply_markup=admin_panel_keyboard(),
        )
        return
    _state[call.from_user.id] = {"step": "link:select", "data": {}}
    await call.message.edit_text(
        "🔗 <b>Change Access Link</b>\n\nSelect a plan:",
        reply_markup=admin_plan_list_keyboard(plans, "admin_lp"),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin_lp:"))
async def cb_link_plan_selected(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔ Unauthorised.", show_alert=True)
        return
    plan_id = int(call.data.split(":", 1)[1])
    await call.answer()
    plan = await get_plan(plan_id)
    if not plan:
        await call.answer("Plan not found.", show_alert=True)
        return
    _state[call.from_user.id] = {
        "step": "link:value",
        "data": {"plan_id": plan_id},
    }
    await call.message.edit_text(
        f"🔗 <b>Change Access Link: {plan['name']}</b>\n\n"
        f"Current link: {plan['access_link'] or '—'}\n\n"
        "Send the new access link:",
        reply_markup=None,
    )


@router.message(_in_state("link:value"), F.text)
async def handle_link_value(message: Message) -> None:
    if not _is_admin(message.from_user.id) or (message.text or "").startswith("/"):
        return
    st = _state.pop(message.from_user.id, None)
    if not st:
        return
    plan_id = st["data"]["plan_id"]
    await update_plan(plan_id, access_link=message.text.strip())
    await message.answer(
        "✅ Access link updated successfully!",
        reply_markup=admin_panel_keyboard(),
    )
