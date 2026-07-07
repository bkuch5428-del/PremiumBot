# PremiumBot

A database-driven Telegram subscription bot built with **aiogram 3.x**, **aiosqlite**, and **Flask**.

## Architecture

| File | Role |
|------|------|
| `main.py` | Entry point — starts Flask health-check thread, runs aiogram polling |
| `config.py` | All config from environment variables (no hardcoded secrets) |
| `database.py` | All DB access — users, plans, orders, stats |
| `keyboards/menu.py` | All `InlineKeyboardMarkup` builders |
| `handlers/admin.py` | `/admin` command + full admin panel wizard |
| `handlers/commands.py` | `/plans`, `/status`, `/help`, `/contact` |
| `handlers/start.py` | `/start`, plan selection, demo video delivery |
| `handlers/payment.py` | Buy → proof → approve/reject flow |
| `handlers/log_channel.py` | Activity logging to log channel |

## Running

```bash
pip install -r requirements.txt
# set environment variables (see .env.example)
python main.py
```

Flask health-check runs on port 8080 (or `$PORT`).

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | ✅ | Telegram bot token |
| `ADMIN_IDS` | ✅ | Comma-separated Telegram user IDs with admin access |
| `SOURCE_CHANNEL_ID` | ✅ | Default private channel for demo video forwarding |
| `PAYMENT_REVIEW_CHANNEL_ID` | ✅ | Channel where payment proofs are sent for review |
| `LOG_CHANNEL_ID` | — | Channel for activity logging |
| `QR_IMAGE_URL` | — | UPI QR code image URL shown at checkout |
| `SUPPORT_GROUP_URL` | — | Telegram support group link |

## Admin Panel (`/admin`)

Only users in `ADMIN_IDS` can access it. Use `/cancel` to exit any wizard.

| Feature | What it does |
|---------|-------------|
| ➕ Add Plan | 5-step wizard: name → price → validity → forward demo videos → access link |
| ✏️ Edit Plan | Edit name, price, validity, or access link on any plan |
| 🗑 Delete Plan | Delete a plan with confirmation |
| 🎥 Change Demo Videos | Replace demo video IDs for a plan (forward from source channel) |
| 🔗 Change Access Link | Update the invite link sent on approval |
| 📊 Statistics | Users, plans, orders, pending, active subscriptions |
| 📢 Broadcast | Send a message to every registered user |
| 📋 Pending Payments | List all orders awaiting admin review |
| 📦 Plans | List all active plans |

## Demo video management

Demo videos are **never downloaded or stored locally**. The wizard asks admins to **forward** messages from the private source channel. The original message IDs are stored in the DB and replayed via `copy_messages()` for each user.

## Payment flow

1. User picks a plan → taps **Buy Now** → sees UPI QR + order ID
2. User taps **I Have Paid** → sends screenshot or UTR
3. Proof is forwarded to `PAYMENT_REVIEW_CHANNEL_ID` with Approve / Reject buttons
4. Admin clicks **Approve** → user receives plan-specific access link + expiry date
5. Admin clicks **Reject** → user is notified to contact support

## User preferences
- Keep Flask health-check server untouched
- Keep aiogram polling untouched
- Do not store media locally — only message IDs
- All plans managed from Telegram, never hardcoded
