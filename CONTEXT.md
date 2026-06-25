# TrackWithThem — Project Context

## Goal
Universal package tracking Telegram bot with Nigerian carrier support, personality-driven messages, autonomous polling, and P2P sending (sender→receiver tracking without a carrier number).

## Stack
- Python 3.12 + python-telegram-bot v20+
- PostgreSQL + SQLAlchemy (async) + Alembic
- APScheduler (background polling)
- 17TRACK API v2.4 (global carriers, 3,400+ supported)
- GIG Logistics / NIPOST scrapers (Nigerian carriers)

## Architecture
```
bot/
  main.py          — Entrypoint, app builder, scheduler config
  phrases.py       — All user-facing strings (was copy.py)
  animation.py     — Animated reply helper (graceful degradation)
  handlers/
    track.py       — /track + auto-detect tracking number
    dashboard.py   — /mypackages with pagination, rename/stop/history
  notifier.py      — Status change pushes with progress_bar + stickers
core/
  poller.py        — APScheduler job: poll all active packages
  carrier_client.py— 17TRACK API client (unified interface)
  local_carriers/
    gig_logistics.py — GIG Logistics scraper
    nipost.py        — NIPOST scraper
    registry.py      — Carrier dispatch registry
  customs_watchdog.py — Detects packages stuck in customs
  carrier_detect.py   — Pattern-based carrier detection (regex)
config.py          — Env-based config (fails loud on missing vars)
db/
  models.py        — SQLAlchemy models (users, packages, history)
  session.py       — Async session factory
  migrations/      — Alembic (2 migrations applied)
```

## Deploy — VPS (163.245.210.70)
- **User**: `trackwiththem` (no sudo)
- **Path**: `/opt/trackwiththem`
- **Env**: `/etc/trackwiththem/.env`
- **Logs**: `/var/log/trackwiththem/` (journalctl also works)
- **Service**: `parcelmate.service` — runs `python -m bot.main`
- **DB**: PostgreSQL `trackwiththem` — user `trackwiththem`

## Bot
- **Username**: @trackwiththem_bot
- **Token**: updated 2026-06-24

## Commands
| Command | Handler |
|---|---|
| `/start` | Welcome message |
| `/track <number>` | Track a package |
| `/mypackages` | Dashboard with pagination, rename, stop, history |

## Carrier Coverage

### Trackable (via 17TRACK API — 3,400+ carriers)
All major global postal operators and couriers including:
- DHL Express, FedEx, UPS, USPS, Aramex
- China Post, Canada Post, Australia Post, Japan Post
- La Poste (Colissimo), PostNL, Swiss Post
- GLS, EVRi, OnTrac, TNT
- 3,400+ more across 230 countries

### Trackable (via local scrapers)
- GIG Logistics (Nigeria)
- NIPOST (Nigeria)

### Detection patterns exist in `carrier_detect.py` for:
DHL, FedEx, UPS, Royal Mail, USPS, China Post, Yanwen, Aramex, GIG Logistics, NIPOST

### Blocked — detected but untrackable
- **Royal Mail** — 17TRACK carrier code `11031` exists and 17TRACK's website lists Royal Mail as supported, but the API returns error `-18019911` ("carrier temporarily does not support registration"). All workarounds exhausted:
  - 17TRACK API v2.4, v1 → same error
  - 17TRACK website API (`handlertrack.ashx`) → 403
  - Royal Mail website (httpx, cloudscraper, Playwright+stealth) → Akamai 403
  - VPS IP (163.245.210.70) flagged by Akamai
  - **Only path forward**: user signs up for Royal Mail Developer Portal, TrackingMore, Ship24, or AfterShip and provides API key

## UPS Pattern Collision (FIXED)
- UPS patterns narrowed from `^[A-Z]{2}\d{9}[A-Z]{2}$` to `^1Z[A-Z0-9]{16}$` and `^\d{9}$`
- `IW750521595GB` now correctly detected as `royalmail` (confidence 0.7), not `ups`
- This also prevents collision with other UPU-format carriers (USPS, China Post, etc.)

## P2P Sending (MVP)

### Concept
Sender creates a shipment via `/send` with item description, receiver's phone, locations, and optional bus/flight number. Bot generates a shareable 6-char code. Both parties track the same shipment. Sender updates progress with buttons; receiver gets notified if they're on Telegram.

### Status Flow
```
📦 Prepared → 🚏 At Park → 🚌 In Transit → 🏁 Arrived → ✅ Delivered
```

### New Files
- `core/shipment_service.py` — Business logic (create, update, notify, claim)
- `bot/handlers/send.py` — `/send` wizard
- `bot/handlers/shipment_dashboard.py` — `/shipments`, `/update`, `/claim`

### Modified Files
- `db/models.py` — Added `Shipment` + `ShipmentStatusHistory`
- `bot/main.py` — Register new handlers
- `bot/phrases.py` — P2P copy

### Not in MVP
- Bolt/Uber integration
- Auto-polling bus/flight arrival
- Web tracking page
- SMS notifications

## Key Config
- 17TRACK API key: `6F04F20D27D0283CFB716632AFA38C6E`
- Royal Mail 17TRACK carrier code: `11031` (identifies carrier but can't register)
- VPS IP: 163.245.210.70 (blocked by Royal Mail Akamai)
- Bot token in `/etc/trackwiththem/.env`
- User Telegram ID: `1099422307`
- Playwright+Chromium installed on VPS at `/opt/trackwiththem/venv/bin/python3 -m playwright`

## Next Steps
1. **Get a Royal Mail tracking API key** — user needs to sign up for:
   - Royal Mail Developer Portal (free, 25 calls/12h): https://developer.royalmail.net
   - TrackingMore (free, 100/month): https://www.trackingmore.com/signup.html
   - AfterShip (free, 50/month): https://www.aftership.com
   - Once obtained, build `core/local_carriers/royalmail.py` and register in `registry.py`
2. Complete P2P MVP (see section above)
3. Deploy and restart bot after any changes
4. Monitor logs: `journalctl -u parcelmate -f`
5. Add webhook if polling proves unreliable
6. Scale: add more Nigerian carriers (ABC Transport, Young Shall Grow, etc.)
