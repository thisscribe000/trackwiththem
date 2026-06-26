# TrackWithThem — Project Context

## Goal
Universal package tracking Telegram bot with Nigerian carrier support, personality-driven messages, autonomous polling, and P2P sending (sender→receiver tracking without a carrier number).

## Stack
- Python 3.12 + python-telegram-bot v20+
- PostgreSQL + SQLAlchemy (async) + Alembic
- APScheduler (background polling)
- 17TRACK API v2.4 (global carriers, 3,400+ supported)
- TrackingMore API v4 (fallback detect + track for unsupported carriers)
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
  track17_client.py— 17TRACK API client (unified interface, Checkpoint/TrackingResult dataclasses, PackageStatus enum)
  trackingmore_client.py — TrackingMore API v4 client (fallback detect + track)
  local_carriers/
    gig_logistics.py — GIG Logistics scraper
    nipost.py        — NIPOST scraper (tries domestic, international, legacy URLs)
    registry.py      — Carrier dispatch registry (local scraper → 17TRACK → TrackingMore fallback)
  customs_watchdog.py — Detects packages stuck in customs
  carrier_detect.py   — Pattern-based carrier detection (regex)
  shipment_service.py — P2P business logic (create, update, notify, claim)
config.py          — Env-based config (fails loud on missing vars)
db/
  models.py        — SQLAlchemy models (users, packages, history, shipments)
  session.py       — Async session factory
  migrations/      — Alembic (2 migrations applied)
web/
  index.html       — Landing page at track.paperlinkos.site (dark theme + P2P demo)
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
| `/send` | Create a P2P shipment wizard |
| `/shipments` | View P2P shipments (sent & received) |
| `/update <code>` | Advance a shipment's status |
| `/claim <code>` | Claim a shipment sent to you |

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
- NIPOST (Nigeria) — limited: WordPress backend returns empty data, legacy URL `track.nipost.gov.ng` DNS broken

### Trackable (via TrackingMore API v4)
- **Speedaf Express** (Chinese/Nigerian cross-border) — numbers starting with `NG` + 12 digits
- Any carrier detected by TrackingMore's detect API when 17TRACK fails

### Detection patterns in `carrier_detect.py`:
DHL, FedEx, UPS, Royal Mail, USPS, China Post, Yanwen, Aramex, GIG Logistics, NIPOST, **Speedaf Express**

## Carrier Resolution Flow
```
1. carrier_detect.py matches pattern → carrier_code
2. registry.py dispatches:
   a. Local carrier (gig-logistics, nipost, speedaf):
      - gig-logistics/nipost: scraper → if UNKNOWN → 17TRACK fallback → if still UNKNOWN → TrackingMore fallback
      - speedaf: → direct to TrackingMore (no local scraper, 17TRACK doesn't support it)
   b. Non-local carrier: 17TRACK only
3. TrackingMore fallback (for nipost failures + speedaf):
   a. detect_carrier() → find real carrier
   b. create_tracking() + get list endpoint → return checkpoints
```

### Blocked — detected but untrackable
- **Royal Mail** — 17TRACK carrier code `11031` exists but API returns error `-18019911` ("carrier temporarily does not support registration"). All workarounds exhausted:
  - 17TRACK API v2.4, v1 → same error
  - 17TRACK website API (`handlertrack.ashx`) → 403
  - Royal Mail website (httpx, cloudscraper, Playwright+stealth) → Akamai 403
  - VPS IP (163.245.210.70) flagged by Akamai
  - **Only path forward**: 3rd-party API (TrackingMore, Ship24, AfterShip)
- ABC Cargo Express — domain unreachable (DigitalOcean connection timeout)
- AAJ Express — tracking API requires JWT (partner auth only)
- Young Shall Grow — domain for sale

## Speedaf Express Discovery
- `NG021119604355` is **Speedaf Express**, not NIPOST
- TrackingMore detect API positively identifies it as speedaf (confidence 0.5+)
- 6 real checkpoints: Clearance handover → Customs → DC Warehouse → LOS-INT → DC-LOS → Distribution Center
- Speedaf is a Chinese cross-border logistics company operating in Nigeria
- Pattern `^NG\d{12}$` now routes to Speedaf instead of NIPOST
- Speedaf bypasses local scraper and 17TRACK entirely — goes straight to TrackingMore

## UPS Pattern Collision (FIXED)
- UPS patterns narrowed from `^[A-Z]{2}\d{9}[A-Z]{2}$` to `^1Z[A-Z0-9]{16}$` and `^\d{9}$`
- `IW750521595GB` now correctly detected as `royalmail` (confidence 0.7), not `ups`
- This also prevents collision with other UPU-format carriers (USPS, China Post, etc.)

## TrackingMore API v4 Notes
- **Field names**: trackinfo uses `checkpoint_date`, `checkpoint_delivery_status`, `tracking_detail` (not `Date`, `StatusDescription`, `Details`)
- **Item-level status**: `delivery_status` (not `status`)
- **List endpoint**: `GET /trackings/get?tracking_numbers={num}` — the single GET `/trackings/{carrier}/{num}` returns 404 for some carriers (e.g. speedaf)
- **Create returns 4101** "already exists" — treated as success (number already registered)
- **400 responses**: must be handled before `raise_for_status()` to extract error code 4101
- **PackageStatus**: reuses the Enum from `track17_client.py` for consistency
- **Checkpoints**: reuses `Checkpoint` dataclass from `track17_client.py` (so handler code works with `.location`, `.description` uniformly)

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
- SMS notifications

## Landing Page — track.paperlinkos.site
- **URL**: https://track.paperlinkos.site
- **Purpose**: Static landing page introducing the bot (all tracking happens on Telegram)
- **Style**: Dark/terminal theme matching PaperLink OS brand
- **Content**: Hero → Features (Global/Nigeria/P2P) → How it Works → **P2P Demo** (two phone mockups showing sender→bot→receiver flow with play/pause) → Commands table → CTA
- **SSL**: Let's Encrypt via certbot (auto-renews)
- **Nginx config**: `/etc/nginx/sites-available/track`
- **Root**: `/var/www/trackwiththem/` — serves `web/index.html`
- **DNS**: A record `track.paperlinkos.site` → `163.245.210.70`
- **Deploy**: `scp web/index.html root@163.245.210.70:/var/www/trackwiththem/index.html`

## Key Config
- 17TRACK API key: `6F04F20D27D0283CFB716632AFA38C6E`
- TrackingMore API key: set via env `TRACKINGMORE_API_KEY` (optional, key: `j5iiyhiz-...`)
- Royal Mail 17TRACK carrier code: `11031` (identifies carrier but can't register)
- VPS IP: 163.245.210.70 (blocked by Royal Mail Akamai)
- Bot token in `/etc/trackwiththem/.env`
- User Telegram ID: `1099422307`
- Playwright+Chromium installed on VPS at `/opt/trackwiththem/venv/bin/python3 -m playwright`

## Key Files
| File | Purpose |
|---|---|
| `core/trackingmore_client.py` | TrackingMore API v4 client (create, get, detect, normalize) |
| `core/track17_client.py` | 17TRACK API client + shared dataclasses (Checkpoint, TrackingResult, PackageStatus) |
| `core/carrier_detect.py` | Regex-based carrier detection (15 carriers) |
| `core/local_carriers/registry.py` | Dispatch: scraper → 17TRACK → TrackingMore fallback |
| `core/local_carriers/nipost.py` | NIPOST WordPress scraper (3 URL attempts) |
| `config.py` | Environment config (requires BOT_TOKEN, DATABASE_URL, TRACK17_API_KEY) |
| `web/index.html` | Landing page with P2P phone demo |

## Next Steps
1. **Get a Royal Mail tracking API key** — sign up for:
   - Royal Mail Developer Portal (free, 25 calls/12h): https://developer.royalmail.net
   - TrackingMore (free, 100/month)— already have key, could use it: user needs to sign up at https://www.trackingmore.com/signup.html
   - AfterShip (free, 50/month): https://www.aftership.com
   - Once obtained, add carrier mapping in `trackingmore_client.py` CARRIER_MAP
2. Deploy and restart bot after any changes: `systemctl restart parcelmate`
3. Monitor logs: `journalctl -u parcelmate -f`
4. Add webhook if polling proves unreliable
5. Scale: add more Nigerian carriers (ABC Transport — domain dead, AAJ Express — needs JWT, etc.)
