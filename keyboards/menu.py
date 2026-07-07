from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Admin panel ───────────────────────────────────────────────────────────────

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Add Plan",    callback_data="admin_add"),
                InlineKeyboardButton(text="✏️ Edit Plan",   callback_data="admin_edit"),
                InlineKeyboardButton(text="🗑 Delete Plan", callback_data="admin_delete"),
            ],
            [
                InlineKeyboardButton(text="🎥 Change Demo Videos", callback_data="admin_demo"),
                InlineKeyboardButton(text="🔗 Change Access Link", callback_data="admin_link"),
            ],
            [
                InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats"),
                InlineKeyboardButton(text="📢 Broadcast",  callback_data="admin_broadcast"),
            ],
            [
                InlineKeyboardButton(text="📋 Pending Payments", callback_data="admin_pending"),
                InlineKeyboardButton(text="📦 Plans",            callback_data="admin_plans"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Settings", callback_data="admin_settings"),
            ],
        ]
    )


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    """Settings sub-panel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Welcome Message", callback_data="settings_welcome")],
            [InlineKeyboardButton(text="💳 Payment Message",  callback_data="settings_payment")],
            [InlineKeyboardButton(text="🖼 QR Image",         callback_data="settings_qr")],
            [InlineKeyboardButton(text="👥 Support Group",    callback_data="settings_support")],
            [InlineKeyboardButton(text="⬅️ Back",             callback_data="settings_back")],
        ]
    )


def settings_cancel_keyboard() -> InlineKeyboardMarkup:
    """Shown while awaiting new setting value — lets admin bail out."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="settings_cancel")],
        ]
    )


def admin_plan_list_keyboard(plans: list[dict], cb_prefix: str) -> InlineKeyboardMarkup:
    """Render a list of plans as inline buttons. cb_prefix:plan_id is the callback_data."""
    rows = [
        [InlineKeyboardButton(
            text=f"📦 {p['name']} — ₹{p['price']}",
            callback_data=f"{cb_prefix}:{p['id']}",
        )]
        for p in plans
    ]
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="admin_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_edit_fields_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Name",         callback_data=f"admin_ef:{plan_id}:name")],
            [InlineKeyboardButton(text="💰 Price",        callback_data=f"admin_ef:{plan_id}:price")],
            [InlineKeyboardButton(text="⏳ Validity",     callback_data=f"admin_ef:{plan_id}:validity")],
            [InlineKeyboardButton(text="🔗 Access Link",  callback_data=f"admin_ef:{plan_id}:access_link")],
            [InlineKeyboardButton(text="❌ Cancel",       callback_data="admin_cancel")],
        ]
    )


def admin_delete_confirm_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"admin_dc:{plan_id}"),
                InlineKeyboardButton(text="❌ No, Cancel",  callback_data="admin_cancel"),
            ]
        ]
    )


def admin_demo_done_keyboard(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"✅ Done ({count} video{'s' if count != 1 else ''} collected)",
                callback_data="admin_demo_done",
            )],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_cancel")],
        ]
    )


def admin_confirm_save_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Save",   callback_data="admin_save"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="admin_cancel"),
            ]
        ]
    )


# ── User-facing plan list (dynamic) ───────────────────────────────────────────

def plans_list_keyboard(plans: list[dict]) -> InlineKeyboardMarkup:
    """Show all plans as selectable buttons."""
    rows = [
        [InlineKeyboardButton(
            text=f"📦 {p['name']} — ₹{p['price']} / {p['validity']}",
            callback_data=f"plan:{p['id']}",
        )]
        for p in plans
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_detail_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    """Plan detail screen — Buy Now + Back."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Buy Now",   callback_data=f"buy:{plan_id}")],
            [InlineKeyboardButton(text="⬅️ Back",       callback_data="back")],
        ]
    )


# ── Payment flow ──────────────────────────────────────────────────────────────

def payment_details_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ I Have Paid", callback_data=f"paid:{order_id}")],
            [InlineKeyboardButton(text="❌ Cancel",       callback_data=f"cancel_order:{order_id}")],
        ]
    )


def await_proof_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_proof")],
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
    )


def approve_reject_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"approve:{order_id}"),
                InlineKeyboardButton(text="❌ Reject",  callback_data=f"reject:{order_id}"),
            ]
        ]
    )


# ── Legacy aliases (kept so older imports don't break) ────────────────────────

def product_keyboard() -> InlineKeyboardMarkup:
    """Fallback shown when no plans exist yet."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 View Plans", callback_data="show_plans")]
        ]
    )
