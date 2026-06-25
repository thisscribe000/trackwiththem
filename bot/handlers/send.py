import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.shipment_service import (
    create_shipment,
    format_shipment_status,
)
from core.repository import get_or_create_user
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

SEND_DESC = "send_desc"
SEND_PHONE = "send_phone"
SEND_ROUTE = "send_route"
SEND_BUS = "send_bus"


async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    context.user_data["send_step"] = SEND_DESC
    await update.message.reply_text(
        "Let's create a shipment! 📦\n\n"
        "**What are you sending?**\n"
        "Describe the item (e.g. \"Birthday gift box\", \"Laptop charger\")",
        parse_mode="Markdown",
    )


async def handle_send_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or not update.message.text:
        return False

    step = context.user_data.get("send_step")
    if not step:
        return False

    text = update.message.text.strip()
    text_lower = text.lower()

    if text_lower == "/skip" and step == SEND_BUS:
        return await _finish_send(update, context, None, None)

    if text_lower in ("/cancel", "/done"):
        context.user_data.pop("send_step", None)
        await update.message.reply_text("Shipment creation cancelled. 👍")
        return True

    if step == SEND_DESC:
        if len(text) > 255:
            await update.message.reply_text(
                "Description is too long (max 255 characters). Please shorten it."
            )
            return True
        context.user_data["send_desc"] = text
        context.user_data["send_step"] = SEND_PHONE
        await update.message.reply_text(
            "**Receiver's phone number?**\n"
            "e.g. `+2348012345678` or `08012345678`",
            parse_mode="Markdown",
        )
        return True

    if step == SEND_PHONE:
        phone = _clean_phone(text)
        if not phone:
            await update.message.reply_text(
                "That doesn't look like a valid phone number. "
                "Please use international format like `+2348012345678`",
                parse_mode="Markdown",
            )
            return True
        context.user_data["send_phone"] = phone
        context.user_data["send_step"] = SEND_ROUTE
        await update.message.reply_text(
            "**From where → to where?**\n"
            "e.g. `Lagos → Abuja` or just `Lagos to Abuja`",
            parse_mode="Markdown",
        )
        return True

    if step == SEND_ROUTE:
        origin, destination = _parse_route(text)
        if not origin or not destination:
            await update.message.reply_text(
                "Couldn't understand that. Use format like:\n"
                "`Lagos → Abuja` or `Lagos to Abuja`",
                parse_mode="Markdown",
            )
            return True
        context.user_data["send_origin"] = origin
        context.user_data["send_destination"] = destination
        context.user_data["send_step"] = SEND_BUS
        await update.message.reply_text(
            "**Bus/flight number & company? (optional)**\n"
            "e.g. `GIG-12345` or `ABC Transport, Lagos-Abuja`\n\n"
            "Send /skip if you don't have one yet.",
            parse_mode="Markdown",
        )
        return True

    if step == SEND_BUS:
        bus_company, bus_flight = _parse_bus_info(text)
        return await _finish_send(update, context, bus_company, bus_flight)

    return False


async def _finish_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    bus_company: str | None,
    bus_flight: str | None,
) -> bool:
    if not update.message or not update.effective_user:
        return False

    desc = context.user_data.pop("send_desc", None)
    phone = context.user_data.pop("send_phone", None)
    origin = context.user_data.pop("send_origin", None)
    destination = context.user_data.pop("send_destination", None)
    context.user_data.pop("send_step", None)

    if not all([desc, phone, origin, destination]):
        await update.message.reply_text("Something went wrong. Try /send again.")
        return True

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        shipment = await create_shipment(
            session=session,
            sender_user_id=user.id,
            receiver_phone=phone,
            description=desc,
            origin=origin,
            destination=destination,
            bus_company=bus_company,
            bus_flight_number=bus_flight,
        )

    summary = format_shipment_status(shipment)
    msg = (
        f"✅ **Shipment created!**\n\n"
        f"{summary}\n\n"
        f"**Share code:** `{shipment.share_code}`\n"
        f"Send this to your receiver so they can track it.\n\n"
        f"To update progress: /update `{shipment.share_code}`\n"
        f"To see all shipments: /shipments"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return True


def _clean_phone(text: str) -> str | None:
    digits = "".join(c for c in text if c.isdigit() or c == "+")
    if not digits:
        return None
    if digits.startswith("+"):
        if len(digits) >= 7:
            return digits
    elif digits.startswith("0"):
        return "+234" + digits[1:]
    elif len(digits) >= 10:
        return "+" + digits
    return None


def _parse_route(text: str) -> tuple[str | None, str | None]:
    for sep in ["→", "->", " to ", " > ", " >"]:
        parts = text.split(sep, 1)
        if len(parts) == 2:
            origin = parts[0].strip()
            destination = parts[1].strip()
            if origin and destination:
                return origin, destination
    return None, None


def _parse_bus_info(text: str) -> tuple[str | None, str | None]:
    for sep in [",", ";", " - ", " – "]:
        parts = text.split(sep, 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    return text.strip(), None
