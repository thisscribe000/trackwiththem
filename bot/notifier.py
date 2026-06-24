import logging
import random

from telegram import Bot
from telegram.error import TelegramError

from bot.phrases import (
    CUSTOMS_DELAY_WARNING,
    DELIVERED_FINAL,
    STICKERS,
    STATUS_TRANSITION_TEMPLATES,
    progress_bar,
)
from core.track17_client import PackageStatus

logger = logging.getLogger(__name__)


async def send_status_update(
    bot: Bot,
    user_id: int,
    tracking_number: str,
    carrier_name: str,
    new_status: str,
    old_status: str,
    location: str | None = None,
) -> None:
    templates = STATUS_TRANSITION_TEMPLATES.get(new_status)
    if not templates:
        message = (
            f"📦 `{tracking_number}` ({carrier_name}) "
            f"is now **{new_status.replace('_', ' ').title()}**."
        )
    else:
        template = random.choice(templates)
        message = (
            f"📦 **{carrier_name}** — `{tracking_number}`\n\n{template}"
        )

    try:
        status = PackageStatus(new_status)
        bar = progress_bar(status)
        message += f"\n\n{bar}"
    except (ValueError, KeyError):
        pass

    if location:
        message += f"\n📍 Last seen: {location}"

    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown",
        )
        logger.info(
            "Sent status update to user %d: %s -> %s (%s)",
            user_id,
            old_status,
            new_status,
            tracking_number,
        )
    except TelegramError as e:
        logger.error(
            "Failed to send status update to user %d: %s",
            user_id,
            e,
        )

    if new_status == "OUT_FOR_DELIVERY":
        await _send_milestone_sticker(bot, user_id, "OUT_FOR_DELIVERY")


async def send_delivered_notification(
    bot: Bot,
    user_id: int,
    tracking_number: str,
    carrier_name: str,
) -> None:
    message = f"📦 **{carrier_name}** — `{tracking_number}`\n\n{DELIVERED_FINAL}"

    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown",
        )
        logger.info(
            "Sent delivered notification to user %d for %s",
            user_id,
            tracking_number,
        )
    except TelegramError as e:
        logger.error(
            "Failed to send delivered notification to user %d: %s",
            user_id,
            e,
        )

    await _send_milestone_sticker(bot, user_id, "DELIVERED")


async def send_customs_delay_warning(
    bot: Bot,
    user_id: int,
    tracking_number: str,
    carrier_name: str,
    days_in_customs: int,
) -> None:
    message = (
        f"📦 **{carrier_name}** — `{tracking_number}`\n\n"
        f"{CUSTOMS_DELAY_WARNING}\n\n"
        f"Days in customs: {days_in_customs}"
    )

    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown",
        )
        logger.info(
            "Sent customs delay warning to user %d for %s",
            user_id,
            tracking_number,
        )
    except TelegramError as e:
        logger.error(
            "Failed to send customs delay warning to user %d: %s",
            user_id,
            e,
        )


async def _send_milestone_sticker(
    bot: Bot, user_id: int, milestone: str
) -> None:
    sticker_file_id = STICKERS.get(milestone)
    if not sticker_file_id:
        return

    try:
        await bot.send_sticker(chat_id=user_id, sticker=sticker_file_id)
    except TelegramError as e:
        logger.warning(
            "Failed to send milestone sticker %s to user %d: %s",
            milestone,
            user_id,
            e,
        )
