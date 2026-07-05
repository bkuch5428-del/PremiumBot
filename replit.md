# PremiumBot

A production-ready Telegram bot built with Python and aiogram 3.

## Stack
- **Language:** Python 3.11
- **Framework:** aiogram 3.21.0
- **Database:** SQLite via aiosqlite
- **HTTP client:** aiohttp
- **Config:** python-dotenv

## Project structure
```
main.py          # Entry point — boots bot and registers routers
config.py        # Loads env vars; raises on missing BOT_TOKEN
database.py      # SQLite init and user upsert helpers
handlers/
  start.py       # /start command + Demo/Buy Now callbacks
keyboards/
  menu.py        # Inline keyboard for product listing
requirements.txt
.env.example
```

## Running locally
1. Copy `.env.example` to `.env` and fill in `BOT_TOKEN`.
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python main.py`

## Render deployment
- **Runtime:** Python 3
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `python main.py`
- Set `BOT_TOKEN` as an environment variable in Render's dashboard.

## User preferences
- Keep code modular (one concern per file/handler).
- No admin panel, payment gateway, coupons, referrals, broadcast, or premium system.
- Render-compatible deployment.
