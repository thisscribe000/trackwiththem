# TrackWithThem — OpenCode Build Plan

Universal package tracking Telegram bot with global carrier coverage + a dedicated Nigerian courier layer (GIG Logistics, Speedaf, NIPOST), personality-driven messaging, and autonomous status-change pushes.

**Stack:** Python · `python-telegram-bot` · PostgreSQL · APScheduler · 17TRACK API · deployed on the VPS at paperlinkos.site

**How to use this doc:** Run each phase as its own prompt to DeepSeek in OpenCode, in order. Don't move to the next phase until the current one runs cleanly. Each phase assumes the previous phases' files already exist.

---

## Phase 1 — Project scaffold + carrier auto-detection

```
Build the foundation for a Telegram bot called TrackWithThem (Python, python-telegram-bot v20+, async).

Project structure:
trackwiththem/
  bot/
    __init__.py
    main.py              # entrypoint, builds Application, registers handlers
    handlers/
      __init__.py
      track.py            # /track command + plain-text tracking number handler
  core/
    __init__.py
    carrier_detect.py     # carrier auto-detection from tracking number format
  config.py               # loads env vars (BOT_TOKEN, DATABASE_URL, TRACK17_API_KEY)
  requirements.txt
  .env.example
  README.md

Requirements:
1. config.py loads all secrets from environment variables using python-dotenv. Never hardcode secrets.
2. carrier_detect.py exports a function `detect_carrier(tracking_number: str) -> list[dict]` that returns a ranked list of possible carriers based on known tracking number patterns (length, prefix, checksum where applicable). Cover at minimum: DHL, FedEx, UPS, USPS, China Post, Yanwen, Aramex. Each result dict should have {"carrier_code": str, "carrier_name": str, "confidence": float}. If nothing matches confidently, return an empty list (the lookup phase will fall back to 17TRACK's own auto-detect).
3. The bot should respond to:
   - /start — friendly welcome explaining what TrackWithThem does in 2-3 sentences, conversational tone, not corporate.
   - /track <number> — and also accept a bare tracking number sent as plain text (no command prefix), since most users will just paste the number.
4. For now, track.py should just call detect_carrier() and reply with what it found (carrier guess + confidence) as a plain text message. We'll wire in the real lookup API in Phase 2.
5. Validate tracking number input: strip whitespace, reject obviously invalid input (too short, contains spaces in the middle, etc.) with a friendly error message — never a stack trace.
6. Use Python logging (not print) throughout, log to both stdout and a rotating file handler.

Write clean, typed, documented code. Include a requirements.txt with pinned versions. Include a README explaining setup (env vars needed, how to run locally).
```

---

## Phase 2 — 17TRACK integration + real lookup

```
Extend TrackWithThem with real tracking lookups via the 17TRACK API.

Add:
  core/
    track17_client.py     # async wrapper around 17TRACK API
  bot/
    handlers/
      track.py             # UPDATE existing file to use real lookup

Requirements:
1. track17_client.py wraps two 17TRACK API actions: registering a tracking number for tracking, and fetching its current status/checkpoints. Use httpx (async) for requests. Read the API key from config.py.
2. Define a normalized internal data model (a dataclass or Pydantic model) called TrackingResult with fields: tracking_number, carrier_code, carrier_name, status (enum: PENDING, IN_TRANSIT, CUSTOMS, OUT_FOR_DELIVERY, DELIVERED, EXCEPTION, UNKNOWN), checkpoints (list of {location, description, timestamp, raw_status}), estimated_delivery (optional date), last_updated (datetime).
3. Write a mapping function that translates 17TRACK's raw status/checkpoint format into the normalized TrackingResult. Keep this mapping in its own function so it's easy to extend later for Nigerian carriers that might need custom mapping (Phase 6).
4. Update the /track handler: when a user sends a tracking number, call carrier_detect.py first for a quick guess (purely for UX — to show "Checking with DHL..." style copy), then call track17_client to register + fetch the real result, then reply with a clean formatted summary: carrier, current status, most recent checkpoint location + time, estimated delivery if available.
5. Handle failure cases distinctly and reply with friendly, specific copy for each:
   - Tracking number not found by any carrier
   - 17TRACK API timeout/error (don't expose raw exception to user)
   - Tracking number format invalid
6. Add retry logic (max 2 retries, exponential backoff) for transient API failures using a small helper, not a third-party retry library, to keep dependencies lean.

Write unit tests for the status-mapping function using a few sample 17TRACK JSON payloads (you can construct realistic fixtures based on 17TRACK's public API docs structure).
```

---

## Phase 3 — Database layer + persistence

```
Add PostgreSQL persistence to TrackWithThem so tracked packages survive restarts and can be polled in the background.

Add:
  db/
    __init__.py
    models.py             # SQLAlchemy models (async)
    session.py            # async engine/session setup
    migrations/           # Alembic migrations
  core/
    repository.py          # data access functions, no raw SQL in handlers

Requirements:
1. Use SQLAlchemy 2.0 async style + asyncpg driver. Connection string from config.py DATABASE_URL.
2. Models:
   - User: id, telegram_user_id (unique), created_at
   - TrackedPackage: id, user_id (FK), tracking_number, carrier_code, carrier_name, nickname (optional, user-settable label like "Mum's birthday gift"), status (enum matching TrackingResult.status), last_checkpoint_location, last_checkpoint_time, estimated_delivery, is_active (bool, default True), created_at, updated_at
   - StatusHistory: id, package_id (FK), status, location, description, timestamp — append-only log of every checkpoint we've seen, used so we never re-notify on a checkpoint already shown to the user
3. repository.py exposes clear functions: get_or_create_user(), add_tracked_package(), get_active_packages_for_user(), get_all_active_packages() (for the scheduler), update_package_status(), deactivate_package(), has_seen_checkpoint() / record_checkpoint().
4. Set up Alembic for migrations. Include the initial migration.
5. Update the /track handler from Phase 2: after a successful lookup, save the package via repository.add_tracked_package() instead of just replying once. If the user re-sends the same tracking number, update the existing record rather than duplicating it.
6. Add a /mypackages command that lists all of a user's active tracked packages with a one-line status each (we'll make this visually richer in Phase 7 — for now, plain text is fine).

Include a docker-compose.yml snippet (commented, for local dev only) showing a Postgres service, since the bot will eventually connect to the VPS's own Postgres instance in production.
```

---

## Phase 4 — Background polling + autonomous notifications

```
Add the background polling engine that makes TrackWithThem proactively notify users when a package's status changes, without them having to ask again.

Add:
  core/
    poller.py              # the recurring job logic
  bot/
    notifier.py             # sends Telegram messages outside of a direct user command

Requirements:
1. Use APScheduler (AsyncIOScheduler) wired into the same event loop as python-telegram-bot's Application. Add an interval job that runs every 4 hours (configurable via env var POLL_INTERVAL_HOURS) and calls poller.poll_all_active_packages().
2. poll_all_active_packages():
   - Fetches all active packages via repository.get_all_active_packages()
   - For each, calls track17_client to get the latest TrackingResult
   - Compares the latest checkpoint against repository.has_seen_checkpoint() — only proceed if this is a genuinely new checkpoint, never re-notify on the same status
   - If new: record it via repository.record_checkpoint(), update the package's stored status, then call notifier.send_status_update() to push a Telegram message to the package's owner
   - If status is now DELIVERED: send a distinct celebratory final message, then call repository.deactivate_package() so it stops being polled (saves API calls)
   - Wrap each package's processing in its own try/except so one failure doesn't kill the whole batch — log and continue
3. Rate-limit awareness: add a small delay between consecutive 17TRACK API calls within a single poll run (e.g. 200ms) to avoid hitting rate limits when a user has many packages tracked.
4. notifier.py's send_status_update() should produce DIFFERENT copy depending on the status transition (e.g. "left origin country" vs "arrived in customs" vs "out for delivery") — write a small dict/function mapping status transitions to message templates. Keep these templates in a separate constants file (bot/copy.py) so tone can be tuned later without touching logic.
5. Add basic admin/ops logging: log every poll run's summary (packages checked, new updates sent, errors) so this is debuggable on the VPS.

Test by manually inserting a package row with an old status, then triggering poll_all_active_packages() manually and confirming a Telegram message is sent only when the live API status differs from stored status.
```

---

## Phase 5 — Personality layer (the "fun" pass)

```
Layer TrackWithThem's personality and pacing on top of the existing lookup and notification flows — this is a pure UX/copy pass, don't change the underlying data logic from Phases 1-4.

Add:
  bot/
    copy.py                 # EXTEND from Phase 4 — all user-facing strings live here
    animation.py             # message-edit sequencing helper

Requirements:
1. animation.py exports a helper `async def animated_reply(message, steps: list[str], delay_seconds: float = 1.0)` that sends the first string as a new message, then edits that SAME message in place for each subsequent string in the list, with a delay between edits. This is the "thinking out loud" effect — use it instead of multiple separate messages where it makes sense.
2. Update the /track handler (Phase 2) to use animated_reply for the lookup sequence, e.g.:
   step 1: "🔍 Looking up your package..."
   step 2: "📦 Found it — checking with {carrier_name}..."
   step 3: the final formatted result
3. Build an emoji progress indicator function in copy.py: `def progress_bar(status: PackageStatus) -> str` that renders something like 🟢🟢🟢⚪⚪ based on how far along the 5 known stages the package is (Picked up → In transit → Customs → Out for delivery → Delivered). Include this in both the lookup reply and the autonomous notification messages from Phase 4.
4. Write distinct, personality-driven copy variants (not robotic status labels) for each status, stored as lists so the bot can randomly pick a variant to avoid feeling repetitive across multiple packages. Tone: warm, a little playful, never childish, never sarcastic about delays (customs delays are genuinely stressful for users — keep that copy reassuring, not jokey).
5. Add a milestone reaction: when a package hits OUT_FOR_DELIVERY or DELIVERED, send a relevant Telegram native sticker (use send_sticker with a real public sticker file_id or sticker set — pick something simple and universally available like a package/celebration sticker) alongside the text message.
6. Make sure animated_reply degrades gracefully — if Telegram's edit_message_text throws (e.g. rate limited), catch it and just send a new message instead of crashing the flow.

Keep all copy centralized in copy.py / bot/copy.py — no user-facing strings hardcoded inline in handler files, so tone can be iterated without touching logic.
```

---

## Phase 6 — Nigerian carrier layer + customs delay flagging

```
Add a Nigeria-specific layer to TrackWithThem covering local couriers that 17TRACK handles weakly or not at all, plus a customs delay watchdog.

Add:
  core/
    local_carriers/
      __init__.py
      gig_logistics.py       # scraper/client for GIG Logistics tracking
      nipost.py               # scraper/client for NIPOST tracking
      registry.py              # maps carrier_code -> correct client (17TRACK vs local)
    customs_watchdog.py        # delay detection logic

Requirements:
1. registry.py is the single dispatch point: given a carrier_code, decide whether to route the lookup through track17_client (Phase 2) or one of the local carrier clients. Update poller.py and the /track handler to call registry.get_tracking_result(carrier_code, tracking_number) instead of calling track17_client directly — this keeps Phase 2-4 logic intact while inserting the Nigerian layer underneath.
2. gig_logistics.py and nipost.py: since these likely don't have public JSON APIs, implement them as lightweight scrapers (httpx + BeautifulSoup) against their public tracking pages. Map whatever status text they return into the SAME normalized TrackingResult model from Phase 2 — write a status-text mapping dict for each carrier's specific wording (e.g. GIG Logistics might say "In transit to destination hub" → map to IN_TRANSIT).
3. Wrap both scrapers defensively: if the carrier's site structure changes or is unreachable, log clearly and return a TrackingResult with status UNKNOWN rather than crashing — local carrier scraping is inherently fragile and the bot must never error out to the user because of it.
4. Extend carrier_detect.py (Phase 1) with pattern rules for GIG Logistics and NIPOST tracking number formats so they get auto-detected like the international carriers.
5. customs_watchdog.py: add a function `is_stuck_in_customs(package) -> bool` that checks if a package's status has been CUSTOMS for longer than a configurable threshold (env var CUSTOMS_DELAY_DAYS, default 4). Wire this into poller.py's poll loop — if true and we haven't already sent a delay warning for this package (track this with a new boolean column `customs_warning_sent` on TrackedPackage, add the migration), send a distinct "this is taking longer than usual" message via notifier.py, with brief practical context (customs clearance in Nigeria commonly takes longer for certain categories — keep the copy informative, not alarmist).
6. Add a new migration for the `customs_warning_sent` column.

This phase should not require changes to Phase 2-5 files except the two integration points called out above (registry dispatch, and the customs watchdog hook in poller.py).
```

---

## Phase 7 — `/mypackages` dashboard + management commands

```
Build out the multi-package dashboard experience and let users manage what they're tracking.

Add:
  bot/
    handlers/
      dashboard.py            # /mypackages and related callback handlers

Requirements:
1. /mypackages: fetch all active packages for the user via repository.get_active_packages_for_user(). For each, render a compact card-style message (Telegram message formatting — bold carrier/nickname, the emoji progress_bar from Phase 5, last checkpoint + relative time like "2 hours ago" not a raw timestamp).
2. If the user has more than 5 active packages, paginate (5 per message) with inline keyboard Next/Previous buttons using CallbackQueryHandler.
3. Each package card includes an inline button row: "Rename" and "Stop tracking".
   - "Stop tracking" → confirmation inline keyboard (Yes/Cancel) before calling repository.deactivate_package() — never delete on a single tap.
   - "Rename" → bot replies asking the user to send the new nickname as their next message; use python-telegram-bot's conversation state (ConversationHandler or a simple per-user pending-action dict) to capture that reply and update TrackedPackage.nickname.
4. Add /mypackages empty state: if the user has zero active packages, reply with a friendly nudge to send a tracking number to get started — never just an empty list.
5. Add a per-package detail view: tapping the carrier name/nickname in a card (inline button "Full history") shows the complete StatusHistory checkpoint list for that package, oldest to newest, each with the postmark-style ✓ styling reflected in plain text equivalent (since Telegram text can't do the HTML stamp visual, use a clean checklist format: "✓ Guangzhou, CN — picked up — 3 days ago").
6. All new user-facing strings go in bot/copy.py, consistent with Phase 5's centralization rule.

Confirm this works end to end: track 2-3 fake packages, verify dashboard pagination, rename, and stop-tracking flows all behave correctly against the real database.
```

---

## Phase 8 — Deployment to the VPS

```
Prepare TrackWithThem for production deployment on the existing VPS at paperlinkos.site (Ubuntu).

Add:
  deploy/
    parcelmate.service        # systemd unit file
    deploy.sh                  # deployment script
  .env.production.example

Requirements:
1. parcelmate.service: a systemd unit that runs the bot as a long-lived service (Restart=on-failure, reasonable RestartSec), running under a dedicated non-root system user, with the working directory set correctly and environment loaded from an env file at a fixed path (e.g. /etc/trackwiththem/.env).
2. deploy.sh: a script that — pulls latest code (git pull), installs/updates dependencies into a venv, runs Alembic migrations (alembic upgrade head), then restarts the systemd service. Make it idempotent and safe to re-run.
3. Confirm the bot's PostgreSQL connection will point at the VPS's existing Postgres instance (not a new one) — use a separate database/schema named parcelmate to avoid colliding with other projects already running on the VPS (ShareStill, PaperLink OS, etc.).
4. Add a health-check log line on startup (bot username, polling interval, DB connection confirmed) so it's easy to verify a fresh deploy actually came up correctly via `journalctl -u parcelmate -f`.
5. Document, in a short DEPLOY.md, the exact manual steps for first-time setup on the VPS: creating the Postgres database/user, placing the env file, enabling + starting the systemd service, and where to find logs.
6. Make sure config.py (Phase 1) fails loudly and immediately on startup if any required env var is missing, rather than failing later mid-request — this matters more in production than local dev.

Do a final pass across the whole codebase checking that no API keys, tokens, or the production DATABASE_URL ever get logged, committed, or exposed in error messages sent back to Telegram users.
```

---

## Notes for you (SCRIBE)

- Phases 1-4 are the load-bearing core — get those solid before touching personality/Nigeria layers.
- Phase 5 (personality) and Phase 6 (Nigeria layer) are independent of each other — you could swap their order if Nigerian coverage matters more to you upfront than the fun-pass.
- 17TRACK's free tier should be enough to validate Phases 1-5 before you need to think about paid volume.
- GIG Logistics / NIPOST scraping (Phase 6) is the most fragile part of this whole build — expect to revisit the status-text mappings as their sites change.