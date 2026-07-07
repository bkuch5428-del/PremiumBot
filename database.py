import json
import logging
from datetime import datetime, timezone, timedelta

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = "users.db"


# ── Schema initialisation ─────────────────────────────────────────────────────

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        # Users
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

        # Plans (fully dynamic, no hardcoded data)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT    NOT NULL,
                price             TEXT    NOT NULL,
                validity          TEXT    NOT NULL,
                demo_message_ids  TEXT    NOT NULL DEFAULT '[]',
                source_channel_id TEXT    NOT NULL DEFAULT '',
                access_link       TEXT    NOT NULL DEFAULT '',
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Orders
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id       TEXT PRIMARY KEY,
                user_id        INTEGER NOT NULL,
                plan_name      TEXT    NOT NULL,
                plan_price     TEXT    NOT NULL,
                plan_validity  TEXT    NOT NULL,
                payment_status TEXT    NOT NULL DEFAULT 'created',
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Migrate orders: add columns that may be missing on existing DBs
        for col_def in (
            "subscription_start TEXT",
            "subscription_end   TEXT",
            "plan_id            INTEGER",
            "access_link        TEXT",
        ):
            try:
                await db.execute(f"ALTER TABLE orders ADD COLUMN {col_def}")
            except Exception:
                pass  # column already exists — safe to ignore

        await db.commit()
    logger.info("Database initialised at %s", DB_PATH)


# ── Users ─────────────────────────────────────────────────────────────────────

async def save_user(user_id: int, username: str | None, first_name: str) -> bool:
    """Upsert the user record. Returns True if the user is brand-new."""
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
    return is_new


async def get_all_user_ids() -> list[int]:
    """Return every registered user ID (for broadcast)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM users")
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


# ── Plans ─────────────────────────────────────────────────────────────────────

async def create_plan(
    name: str,
    price: str,
    validity: str,
    demo_message_ids: list[int],
    source_channel_id: str,
    access_link: str,
) -> int:
    """Insert a new plan. Returns the new plan's id."""
    ids_json = json.dumps(demo_message_ids)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO plans (name, price, validity, demo_message_ids, source_channel_id, access_link)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, price, validity, ids_json, source_channel_id, access_link),
        )
        plan_id = cursor.lastrowid
        await db.commit()
    logger.info("Created plan id=%s name=%r", plan_id, name)
    return plan_id


async def get_all_plans() -> list[dict]:
    """Return all plans as a list of dicts."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, price, validity, demo_message_ids, source_channel_id, access_link, created_at "
            "FROM plans ORDER BY id"
        )
        rows = await cursor.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["demo_message_ids"] = json.loads(d["demo_message_ids"] or "[]")
        except Exception:
            d["demo_message_ids"] = []
        result.append(d)
    return result


async def get_plan(plan_id: int) -> dict | None:
    """Return a single plan dict or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, price, validity, demo_message_ids, source_channel_id, access_link "
            "FROM plans WHERE id = ?",
            (plan_id,),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["demo_message_ids"] = json.loads(d["demo_message_ids"] or "[]")
    except Exception:
        d["demo_message_ids"] = []
    return d


async def update_plan(plan_id: int, **fields) -> None:
    """Update any subset of plan fields. Serialises demo_message_ids if given."""
    if "demo_message_ids" in fields:
        fields["demo_message_ids"] = json.dumps(fields["demo_message_ids"])
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [plan_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE plans SET {set_clause} WHERE id = ?", values)
        await db.commit()
    logger.info("Updated plan id=%s fields=%s", plan_id, list(fields.keys()))


async def delete_plan(plan_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        await db.commit()
    logger.info("Deleted plan id=%s", plan_id)


# ── Orders ────────────────────────────────────────────────────────────────────

async def create_order(
    user_id: int,
    plan_name: str,
    plan_price: str,
    plan_validity: str,
    order_id: str,
    plan_id: int | None = None,
    access_link: str = "",
) -> None:
    """Insert a new order row with status 'created'."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO orders
                (order_id, user_id, plan_name, plan_price, plan_validity, plan_id, access_link)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (order_id, user_id, plan_name, plan_price, plan_validity, plan_id, access_link),
        )
        await db.commit()
    logger.debug("Created order %s for user %s", order_id, user_id)


async def update_order_status(order_id: str, status: str) -> None:
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
      - payment_status   → 'approved'
      - subscription_start → now (UTC)
      - subscription_end   → now + plan validity days (UTC)

    Returns a dict with user_id, plan_name, plan_validity, subscription_end, access_link.
    Returns None if the order does not exist or is not in 'pending' state.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, plan_name, plan_validity, access_link "
            "FROM orders WHERE order_id = ? AND payment_status = 'pending'",
            (order_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

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
        "user_id":          row["user_id"],
        "plan_name":        row["plan_name"],
        "plan_validity":    row["plan_validity"],
        "subscription_end": sub_end,
        "access_link":      row["access_link"] or "",
    }


async def get_pending_orders() -> list[dict]:
    """Return all orders with payment_status='pending'."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT order_id, user_id, plan_name, plan_price, created_at "
            "FROM orders WHERE payment_status = 'pending' ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_user_active_subscription(user_id: int) -> dict | None:
    """Return the most recent approved/active order for a user, or None."""
    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT order_id, plan_name, plan_price, plan_validity,
                   subscription_start, subscription_end
            FROM orders
            WHERE user_id = ?
              AND payment_status = 'approved'
              AND subscription_end >= ?
            ORDER BY subscription_end DESC
            LIMIT 1
            """,
            (user_id, now_iso),
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


# ── Statistics ────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    """Return a stats dict for the admin statistics panel."""
    async with aiosqlite.connect(DB_PATH) as db:
        now_iso = datetime.now(timezone.utc).isoformat()

        total_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        total_plans = (await (await db.execute("SELECT COUNT(*) FROM plans")).fetchone())[0]
        total_orders = (await (await db.execute("SELECT COUNT(*) FROM orders")).fetchone())[0]
        pending = (await (await db.execute(
            "SELECT COUNT(*) FROM orders WHERE payment_status = 'pending'"
        )).fetchone())[0]
        active_subs = (await (await db.execute(
            "SELECT COUNT(*) FROM orders "
            "WHERE payment_status = 'approved' AND subscription_end >= ?",
            (now_iso,),
        )).fetchone())[0]

    return {
        "total_users":   total_users,
        "total_plans":   total_plans,
        "total_orders":  total_orders,
        "pending":       pending,
        "active_subs":   active_subs,
    }
