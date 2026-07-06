import logging

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
