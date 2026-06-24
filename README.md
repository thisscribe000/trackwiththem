# TrackWithThem

Universal package tracking Telegram bot with global carrier coverage + a dedicated Nigerian courier layer.

**Stack:** Python · python-telegram-bot · PostgreSQL · APScheduler · 17TRACK API

## Setup

1. Clone the repo and create a virtual environment:

   ```
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your secrets:

   ```
   cp .env.example .env
   ```

   **Required:** `BOT_TOKEN` — get one from [@BotFather](https://t.me/BotFather)

4. Run the bot:

   ```
   python -m bot.main
   ```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | Yes | Telegram bot token from BotFather |
| `DATABASE_URL` | No (Phase 3+) | PostgreSQL connection string |
| `TRACK17_API_KEY` | No (Phase 2+) | 17TRACK API key |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `LOG_FILE` | No | Log file path (default: trackwiththem.log) |

## Commands

- `/start` — Welcome message
- `/track <number>` — Track a package
- `/mypackages` — List your tracked packages (coming in Phase 3+)

You can also just paste a tracking number directly — no command needed.
