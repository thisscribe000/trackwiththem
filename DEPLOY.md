# Deploying TrackWithThem

## Prerequisites

- Ubuntu VPS (tested on 22.04+)
- PostgreSQL instance (existing or new)
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- 17TRACK API key

## First-time setup

### 1. Create the system user

```bash
sudo adduser --system --group --home /opt/trackwiththem trackwiththem
```

### 2. Clone the repository

```bash
sudo -u trackwiththem git clone <repo-url> /opt/trackwiththem
```

### 3. Create Python virtual environment

```bash
sudo -u trackwiththem python3 -m venv /opt/trackwiththem/venv
sudo -u trackwiththem /opt/trackwiththem/venv/bin/pip install -r /opt/trackwiththem/requirements.txt
```

### 4. Create the environment file

```bash
sudo mkdir -p /etc/trackwiththem
sudo cp /opt/trackwiththem/.env.production.example /etc/trackwiththem/.env
sudo nano /etc/trackwiththem/.env   # fill in your secrets
sudo chown -R trackwiththem:trackwiththem /etc/trackwiththem
sudo chmod 600 /etc/trackwiththem/.env
```

### 5. Create PostgreSQL database

```sql
CREATE DATABASE trackwiththem;
CREATE USER trackwiththem WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE trackwiththem TO trackwiththem;
```

Update `DATABASE_URL` in `/etc/trackwiththem/.env` to match.

### 6. Create log directory

```bash
sudo mkdir -p /var/log/trackwiththem
sudo chown trackwiththem:trackwiththem /var/log/trackwiththem
```

### 7. Run migrations

```bash
sudo -u trackwiththem /opt/trackwiththem/venv/bin/alembic -c /opt/trackwiththem/alembic.ini upgrade head
```

### 8. Install systemd service

```bash
sudo cp /opt/trackwiththem/deploy/parcelmate.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable parcelmate
sudo systemctl start parcelmate
```

### 9. Verify it's running

```bash
systemctl status parcelmate
journalctl -u parcelmate -f
```

You should see a log line like:
```
TrackWithThem started — bot: @YourBot (id: 123456), poll interval: 4 hours, DB: connected
```

## Deploying updates

Run the deploy script:

```bash
sudo /opt/trackwiththem/deploy/deploy.sh
```

Or manually:

```bash
cd /opt/trackwiththem
sudo -u trackwiththem git pull origin main
sudo -u trackwiththem /opt/trackwiththem/venv/bin/pip install -r requirements.txt
sudo -u trackwiththem /opt/trackwiththem/venv/bin/alembic upgrade head
sudo systemctl restart parcelmate
```

## Logs

- Application logs: `journalctl -u parcelmate -f`
- Rotating log file: `/var/log/trackwiththem/trackwiththem.log` (configured in `.env`)
