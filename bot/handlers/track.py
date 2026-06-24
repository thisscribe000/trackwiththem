import asyncio
import logging

import httpx
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from bot.phrases import progress_bar
from config import DATABASE_URL
from core.carrier_detect import detect_carrier
from core.local_carriers.registry import get_tracking_result
from core.repository import add_tracked_package, get_or_create_user
from core.track17_client import (
    TRACK17_API_KEY,
    PackageStatus,
)
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

STATUS_EMOJI = {
    PackageStatus.PENDING: "📋",
    PackageStatus.IN_TRANSIT: "🚚",
    PackageStatus.CUSTOMS: "🛃",
    PackageStatus.OUT_FOR_DELIVERY: "📬",
    PackageStatus.DELIVERED: "✅",
    PackageStatus.EXCEPTION: "⚠️",
    PackageStatus.UNKNOWN: "❓",
}


async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    args = context.args
    if args:
        tracking_number = " ".join(args)
    else:
        await update.message.reply_text(
            "Please send a tracking number after /track, like:\n"
            "/track 1Z999AA10123456784"
        )
        return

    await _handle_tracking(update, tracking_number)


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if text.startswith("/"):
        return

    if context.user_data.get("pending_rename"):
        from bot.handlers.dashboard import handle_rename_text
        await handle_rename_text(update, context)
        return

    await _handle_tracking(update, text)


async def _handle_tracking(
    update: Update, tracking_number: str
) -> None:
    if not update.message:
        return

    validation_error = _validate_number(tracking_number)
    if validation_error:
        await update.message.reply_text(validation_error)
        return

    cleaned = tracking_number.strip()

    if not TRACK17_API_KEY:
        await _carrier_guess_only(update, cleaned)
        return

    carriers = detect_carrier(cleaned)
    carrier_code = carriers[0]["carrier_code"] if carriers else ""
    carrier_name = carriers[0]["carrier_name"] if carriers else "Unknown carrier"

    msg = await update.message.reply_text(
        f"🔍 Looking up `{cleaned}`...", parse_mode="Markdown"
    )

    try:
        result = await get_tracking_result(cleaned, carrier_code, carrier_name)
    except ValueError:
        await _safe_edit(
            msg,
            update,
            f"Couldn't find tracking info for `{cleaned}`.\n"
            "Double-check the number and try again.",
        )
        return
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            await _safe_edit(
                msg,
                update,
                "Tracking API isn't configured properly. "
                "Let the bot owner know the API key needs checking.",
            )
        else:
            await _safe_edit(
                msg,
                update,
                "The tracking service is having trouble right now. "
                "Please try again in a few minutes.",
            )
        logger.warning("API error for %s: %s", cleaned, e)
        return
    except httpx.TimeoutException:
        await _safe_edit(
            msg,
            update,
            "The tracking service is taking too long to respond. "
            "Please try again later.",
        )
        return
    except Exception as e:
        await _safe_edit(
            msg,
            update,
            "Something unexpected happened while looking up your package. "
            "Please try again.",
        )
        logger.error("Unexpected error tracking %s: %s", cleaned, e, exc_info=True)
        return

    await asyncio.sleep(1.0)
    msg = await _safe_edit(
        msg,
        update,
        f"📦 Found it — checking with **{carrier_name}**...",
    )

    if DATABASE_URL and update.effective_user:
        try:
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(
                    session, update.effective_user.id
                )
                latest = result.checkpoints[0] if result.checkpoints else None
                await add_tracked_package(
                    session,
                    user_id=user.id,
                    tracking_number=result.tracking_number,
                    carrier_code=result.carrier_code,
                    carrier_name=result.carrier_name,
                    status=result.status.value,
                    last_checkpoint_location=latest.location if latest else None,
                    last_checkpoint_time=latest.timestamp if latest else None,
                    estimated_delivery=result.estimated_delivery,
                )
        except Exception as e:
            logger.error("Failed to save tracking result: %s", e, exc_info=True)

    await asyncio.sleep(1.0)
    await _safe_edit(msg, update, _format_result(result))


async def _carrier_guess_only(
    update: Update, tracking_number: str
) -> None:
    carriers = detect_carrier(tracking_number)

    if not carriers:
        await update.message.reply_text(
            f"Couldn't recognise the carrier for `{tracking_number}`.\n\n"
            "I'll still check with the tracking API (if you've configured one), "
            "but knowing the carrier helps me give you a faster answer.",
            parse_mode="Markdown",
        )
        return

    lines = [f"**Tracking:** `{tracking_number}`\n"]
    for c in carriers:
        pct = int(c["confidence"] * 100)
        lines.append(f"• {c['carrier_name']} — {pct}% confident")

    lines.append(
        "\n_This is just a carrier guess. "
        "Set a 17TRACK API key to get live tracking._"
    )

    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )


def _format_result(result) -> str:
    emoji = STATUS_EMOJI.get(result.status, "❓")
    status_label = result.status.value.replace("_", " ").title()

    bar = progress_bar(result.status)

    lines = [
        f"**{result.carrier_name}** {emoji}",
        f"`{result.tracking_number}`",
        "",
        f"**Status:** {status_label}",
        bar,
    ]

    if result.checkpoints:
        latest = result.checkpoints[0]
        if latest.location:
            lines.append(f"**Location:** {latest.location}")
        if latest.description:
            lines.append(f"**Detail:** {latest.description}")
        if latest.timestamp:
            lines.append(f"**Time:** {_format_dt(latest.timestamp)}")

    if result.estimated_delivery:
        lines.append(
            f"**Estimated delivery:** {_format_dt(result.estimated_delivery)}"
        )

    if result.last_updated:
        lines.append(f"**Last updated:** {_format_dt(result.last_updated)}")

    lines.append("")
    lines.append("_Tap /mypackages to see all your tracked packages._")

    return "\n".join(lines)


def _format_dt(dt) -> str:
    return dt.strftime("%d %b %Y, %H:%M UTC")


def _validate_number(tracking_number: str) -> str | None:
    stripped = tracking_number.strip()

    if not stripped:
        return "That doesn't look like a tracking number — it's empty!"

    if len(stripped) < 5:
        return (
            f"`{stripped}` is too short to be a tracking number. "
            "Please check and try again."
        )

    if " " in stripped:
        return (
            "Tracking numbers shouldn't have spaces in the middle. "
            "Please send just the number."
        )

    if not any(c.isalnum() for c in stripped):
        return (
            "That doesn't look like a valid tracking number. "
            "Please check and try again."
        )

    return None


async def _safe_edit(
    msg, update, text: str,
) -> None:
    try:
        return await msg.edit_text(text, parse_mode="Markdown")
    except Exception:
        logger.warning("Failed to edit message, sending new one", exc_info=True)
        return await update.message.reply_text(text, parse_mode="Markdown")
