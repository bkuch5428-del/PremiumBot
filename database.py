import logging
from datetime import datetime, timezone, timedelta

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = "users.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                joined_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id       TEXT PRIMARY KEY,
                user_id        INTEGER NOT NULL,
                plan_name      TEXT NOT NULL,
                plan_price     TEXT NOT NULL,
                plan_validity  TEXT NOT NULL,
                payment_status TEXT NOT NULL DEFAULT 'created',
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Migrate: add subscription columns if this is an existing database.
        for col in ("subscription_start", "subscription_end"):
            try:
                await db.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT")
            except Exception:
                pass  # column already exists — safe to ignore
        await db.commit()
    logger.info("Database initialised at %s", DB_PATH)


async def save_user(user_id: int, username: str | None, first_name: str) -> bool:
    """Upsert the user record.  Returns True if the user is brand-new."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
        is_new = await cursor.fetchone() is None
        await db.execute(
            """
            INSERT INTO users (id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name),
        )
        await db.commit()
    logger.debug("Saved user %s (new=%s)", user_id, is_new)
    return is_new


async def create_order(
    user_id: int,
    plan_name: str,
    plan_price: str,
    plan_validity: str,
    order_id: str,
) -> None:
    """Insert a new order row with status 'created'."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO orders (order_id, user_id, plan_name, plan_price, plan_validity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, user_id, plan_name, plan_price, plan_validity),
        )
        await db.commit()
    logger.debug("Created order %s for user %s", order_id, user_id)


async def update_order_status(order_id: str, status: str) -> None:
    """Update the payment_status of an existing order."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET payment_status = ? WHERE order_id = ?",
            (status, order_id),
        )
        await db.commit()
    logger.debug("Order %s → %s", order_id, status)


async def approve_order(order_id: str) -> dict | None:
    """
    Approve an order:
      - payment_status  → 'approved'
      - subscription_start → now (UTC)
      - subscription_end   → now + plan validity days (UTC)

    Returns a dict with user_id, plan_name, plan_validity, subscription_end
    (datetime, UTC) so the caller can build the activation notification.
    Returns None if the order does not exist.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Only approve orders that are currently in 'pending' state.
        # This prevents double-approvals and acting on cancelled/rejected orders.
        cursor = await db.execute(
            "SELECT user_id, plan_name, plan_validity FROM orders "
            "WHERE order_id = ? AND payment_status = 'pending'",
            (order_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None  # not found or already actioned

        # Parse "30 Days" → 30
        try:
            days = int(str(row["plan_validity"]).strip().split()[0])
        except (ValueError, IndexError):
            days = 30

        now = datetime.now(timezone.utc)
        sub_end = now + timedelta(days=days)

        await db.execute(
            """
            UPDATE orders
               SET payment_status    = 'approved',
                   subscription_start = ?,
                   subscription_end   = ?
             WHERE order_id = ?
            """,
            (now.isoformat(), sub_end.isoformat(), order_id),
        )
        await db.commit()

    logger.info("Order %s approved; sub ends %s", order_id, sub_end.date())
    return {
        "user_id":       row["user_id"],
        "plan_name":     row["plan_name"],
        "plan_validity": row["plan_validity"],
        "subscription_end": sub_end,
    }
