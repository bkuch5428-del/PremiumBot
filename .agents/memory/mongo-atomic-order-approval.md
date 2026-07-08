---
name: MongoDB atomic order approval
description: Use find_one_and_update instead of find_one + update_one for any status-gated state transition, to avoid double-processing races.
---

## Rule
When a write depends on the current value of a status field (e.g. approving
a "pending" order, claiming a job, consuming a one-time token), never do a
`find_one({...status: "pending"})` read followed by a separate
`update_one({_id: ...}, {$set: ...})` write. Two concurrent callers can both
pass the read check before either writes, causing the transition to run
twice (e.g. a user getting approved/notified twice for one payment).

**Why:** found during a SQLite→MongoDB (Motor) migration for a Telegram bot;
the read-then-write pattern was carried over from single-threaded SQLite
code where it happened to be safe, but async/concurrent Mongo access is not.

**How to apply:** use `find_one_and_update({_id: ..., status: "pending"},
{$set: {...}})` as a single atomic compare-and-set. If the filter no longer
matches (already transitioned), the call returns `None`/no document —
treat that as "someone else already handled it," not an error.
