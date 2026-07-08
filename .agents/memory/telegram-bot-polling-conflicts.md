---
name: Telegram bot polling conflicts
description: How a duplicate long-polling bot instance (e.g. a stale Render/other deployment) manifests as intermittent app-level bugs, and how to diagnose it.
---

## Symptom
A single-poller Telegram bot (aiogram `dp.start_polling`) built on an in-memory
per-process conversation state (`_state` dict keyed by user id) shows
seemingly random breakage: multi-step admin wizards "stop after step 1",
some commands get no reply, list/read commands appear to return empty data
even though direct testing against the database proves the code is correct.

## Root cause
Telegram only allows one active `getUpdates` long-poll per bot token. If a
second process (an old Render/Replit/other deployment still running the
previous code version) is also polling with the same `BOT_TOKEN`, Telegram
silently alternates which process's poll succeeds. Real user updates get
randomly split between the two processes. Any handler relying on in-memory
state that only exists on one of the two processes will silently no-op on
the other ("Update id=... is not handled" in aiogram logs) — this looks
exactly like broken multi-step conversation state or missing data, even when
the code and database are fully correct.

**Why:** in-memory state (dicts, aiogram FSM MemoryStorage) is process-local;
it does not survive being split across two competing pollers or process
restarts.

## How to diagnose
- Look for `TelegramConflictError: ... terminated by other getUpdates
  request` in the workflow logs — this is the definitive signal, not a
  red herring.
- Before touching handler code, verify the bug in isolation: call the actual
  handler coroutines directly with mocked `Message`/`CallbackQuery` objects
  (bypassing the Telegram network) and assert against the real database.
  If handlers pass cleanly in isolation but fail "live," the live bot's
  environment (duplicate poller) is the suspect, not the code.
- Do NOT call `getUpdates`/`getWebhookInfo` manually from a debugging script
  while the app's own poller is running — this itself creates a second
  poller and produces a fresh conflict, confusing the diagnosis.

## Fix
Ask the user whether another deployment/environment holds the same
`BOT_TOKEN` and is still running; have them stop it. The conflict error
should clear within roughly 1–2 minutes after the second poller actually
stops (Telegram doesn't release the lock instantly).
