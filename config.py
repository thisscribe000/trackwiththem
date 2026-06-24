import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV_VARS = [
    "BOT_TOKEN",
    "DATABASE_URL",
    "TRACK17_API_KEY",
]

missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
if missing:
    raise RuntimeError(
        f"Missing required environment variables: {', '.join(missing)}. "
        "Check your .env file."
    )

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
DATABASE_URL: str = os.environ["DATABASE_URL"]
TRACK17_API_KEY: str = os.environ["TRACK17_API_KEY"]

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE: str = os.environ.get("LOG_FILE", "trackwiththem.log")


def setup_logging() -> None:
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    stream_handler.setFormatter(stream_formatter)
    root_logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5_242_880, backupCount=3
    )
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
