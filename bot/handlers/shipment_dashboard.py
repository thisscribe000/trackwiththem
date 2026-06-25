import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.repository import get_or_create_user
from core.shipment_service import (
    STATUS_EMOJI,
    cancel_shipment,
    claim_shipment,
    format_shipment_status,
    get_next_status,
    get_received_shipments,
    get_sent_shipments,
    get_shipment_by_code,
    update_shipment_status,
)
from db.models import ShipmentStatus
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

SHIP_PAGE_SIZE = 5

SHIP_LIST = "ship_list"
SHIP_VIEW = "ship_view_"
SHIP_UPDATE = "ship_upd_"
SHIP_CONFIRM = "ship_cfm_"
SHIP_CANCEL = "ship_cnl_"
SHIP_BACK = "ship_back"


async def shipments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        sent = await get_sent_shipments(session, user.id)
        received = await get_received_shipments(session, user.id)

    if not sent and not received:
        await update.message.reply_text(
            "No P2P shipments yet.\n\n"
            "Send something to a friend with /send",
            parse_mode="Markdown",
        )
        return

    await _send_shipment_list(update.message, sent, received)


async def _send_shipment_list(message, sent: list, received: list) -> None:
    lines = ["**📬 Your Shipments**", ""]

    if sent:
        lines.append("**Sent by you:**")
        for s in sent[:SHIP_PAGE_SIZE]:
            emoji = STATUS_EMOJI.get(s.status, "❓")
            status_label = s.status.value.replace("_", " ").title()
            lines.append(
                f"{emoji} **{s.description}** — {status_label}\n"
                f"`{s.share_code}`  📍 {s.origin} → {s.destination}"
            )
        lines.append("")

    if received:
        lines.append("**Sent to you:**")
        for s in received[:SHIP_PAGE_SIZE]:
            emoji = STATUS_EMOJI.get(s.status, "❓")
            status_label = s.status.value.replace("_", " ").title()
            lines.append(
                f"{emoji} **{s.description}** — {status_label}\n"
                f"`{s.share_code}`  📍 {s.origin} → {s.destination}"
            )
        lines.append("")

    all_shipments = sent + received
    keyboard = []
    for s in all_shipments[:SHIP_PAGE_SIZE]:
        keyboard.append([
            InlineKeyboardButton(
                f"👁 View {s.share_code}", callback_data=f"{SHIP_VIEW}{s.id}"
            ),
            InlineKeyboardButton(
                "⏹ Cancel", callback_data=f"{SHIP_CANCEL}{s.id}"
            ),
        ])

    if len(all_shipments) > SHIP_PAGE_SIZE:
        keyboard.append([
            InlineKeyboardButton(
                f"Show all ({len(all_shipments)})",
                callback_data=SHIP_LIST,
            )
        ])

    await message.reply_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


async def shipment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.message:
        return

    await query.answer()
    data = query.data

    if data == SHIP_LIST:
        await _show_all_shipments(query)
    elif data.startswith(SHIP_VIEW):
        ship_id = int(data[len(SHIP_VIEW):])
        await _view_shipment(query, ship_id)
    elif data.startswith(SHIP_UPDATE):
        ship_id = int(data[len(SHIP_UPDATE):])
        await _show_update_buttons(query, ship_id)
    elif data.startswith(SHIP_CONFIRM):
        parts = data[len(SHIP_CONFIRM):].split("_", 1)
        ship_id = int(parts[0])
        status_str = parts[1]
        await _execute_update(query, ship_id, status_str)
    elif data.startswith(SHIP_CANCEL):
        ship_id = int(data[len(SHIP_CANCEL):])
        await _cancel_shipment(query, ship_id)
    elif data == SHIP_BACK:
        await _back_to_list(query)


async def _show_all_shipments(query) -> None:
    telegram_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id)
        sent = await get_sent_shipments(session, user.id)
        received = await get_received_shipments(session, user.id)

    sent_lines = []
    for s in sent:
        emoji = STATUS_EMOJI.get(s.status, "❓")
        st = s.status.value.replace("_", " ").title()
        sent_lines.append(f"{emoji} `{s.share_code}` **{s.description}** — {st}")

    received_lines = []
    for s in received:
        emoji = STATUS_EMOJI.get(s.status, "❓")
        st = s.status.value.replace("_", " ").title()
        received_lines.append(f"{emoji} `{s.share_code}` **{s.description}** — {st}")

    lines = ["**📬 All Shipments**", ""]
    if sent_lines:
        lines.append("**Sent by you:**")
        lines.extend(sent_lines)
        lines.append("")
    if received_lines:
        lines.append("**Sent to you:**")
        lines.extend(received_lines)
        lines.append("")

    keyboard = [[InlineKeyboardButton("« Back", callback_data=SHIP_BACK)]]
    await query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _view_shipment(query, ship_id: int) -> None:
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from db.models import Shipment, ShipmentStatusHistory

        result = await session.execute(
            select(Shipment).where(Shipment.id == ship_id)
        )
        shipment = result.scalar_one_or_none()
        if not shipment:
            await query.edit_message_text("Shipment not found.")
            return

        hist_result = await session.execute(
            select(ShipmentStatusHistory)
            .where(ShipmentStatusHistory.shipment_id == ship_id)
            .order_by(ShipmentStatusHistory.timestamp.asc())
        )
        history = list(hist_result.scalars().all())

    header = format_shipment_status(shipment)

    lines = [header, ""]
    if history:
        lines.append("**Timeline:**")
        for entry in history:
            emoji = STATUS_EMOJI.get(ShipmentStatus(entry.status), "❓")
            ts = entry.timestamp.strftime("%d %b, %H:%M") if entry.timestamp else ""
            loc = f" — {entry.location}" if entry.location else ""
            desc = f" — {entry.description}" if entry.description else ""
            label = entry.status.replace("_", " ").title()
            lines.append(f"{emoji} {label}{loc}{desc}")
            if ts:
                lines[-1] += f" _{ts}_"
    else:
        lines.append("_No updates yet._")

    is_sender = query.from_user.id == (
        await _get_telegram_id(shipment.sender_user_id)
    )
    keyboard = []
    if is_sender:
        next_status = await get_next_status(shipment.status)
        if next_status and next_status != ShipmentStatus.CANCELLED:
            keyboard.append([
                InlineKeyboardButton(
                    f"▶️ Update to {next_status.value.replace('_', ' ').title()}",
                    callback_data=f"{SHIP_UPDATE}{ship_id}",
                )
            ])
    keyboard.append([
        InlineKeyboardButton("« Back to shipments", callback_data=SHIP_BACK)
    ])

    await query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _show_update_buttons(query, ship_id: int) -> None:
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from db.models import Shipment

        result = await session.execute(
            select(Shipment).where(Shipment.id == ship_id)
        )
        shipment = result.scalar_one_or_none()

    if not shipment:
        await query.edit_message_text("Shipment not found.")
        return

    next_status = await get_next_status(shipment.status)
    if not next_status:
        await query.edit_message_text(
            "This shipment has already reached its final status.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=SHIP_BACK)]
            ]),
        )
        return

    emoji = STATUS_EMOJI.get(next_status, "❓")
    label = next_status.value.replace("_", " ").title()

    keyboard = [
        [
            InlineKeyboardButton(
                f"{emoji} {label}",
                callback_data=f"{SHIP_CONFIRM}{ship_id}_{next_status.value}",
            )
        ],
        [InlineKeyboardButton("« Cancel", callback_data=f"{SHIP_VIEW}{ship_id}")],
    ]

    await query.edit_message_text(
        f"**Update shipment `{shipment.share_code}`**\n\n"
        f"Current: {shipment.status.value.replace('_', ' ').title()}\n\n"
        f"Advance to next status?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _execute_update(
    query, ship_id: int, status_str: str
) -> None:
    telegram_id = query.from_user.id
    new_status = ShipmentStatus(status_str)

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id)
        shipment = await update_shipment_status(
            session, ship_id, new_status, updated_by="sender"
        )

    if not shipment:
        await query.edit_message_text("Shipment not found.")
        return

    emoji = STATUS_EMOJI.get(new_status, "❓")
    label = new_status.value.replace("_", " ").title()

    await query.edit_message_text(
        f"✅ **Status updated!**\n\n"
        f"`{shipment.share_code}` — {emoji} {label}\n"
        f"{shipment.origin} → {shipment.destination}\n\n"
        f"Receiver will be notified if they're on Telegram.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to shipments", callback_data=SHIP_BACK)]
        ]),
    )

    if shipment.receiver_user_id:
        try:
            receiver_tg_id = await _get_telegram_id(shipment.receiver_user_id)
            if receiver_tg_id:
                await query.message.bot.send_message(
                    chat_id=receiver_tg_id,
                    text=(
                        f"📬 **Your shipment has been updated!**\n\n"
                        f"{emoji} **{shipment.description}**\n"
                        f"📍 {shipment.origin} → {shipment.destination}\n"
                        f"**Status:** {label}\n\n"
                        f"Use /shipments to view details."
                    ),
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.warning("Failed to notify receiver: %s", e)


async def _cancel_shipment(query, ship_id: int) -> None:
    telegram_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id)
        shipment = await cancel_shipment(session, ship_id, user.id)

    if not shipment:
        await query.edit_message_text(
            "Couldn't cancel. Either not found or you're not the sender.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=SHIP_BACK)]
            ]),
        )
        return

    await query.edit_message_text(
        f"❌ Shipment `{shipment.share_code}` cancelled.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to shipments", callback_data=SHIP_BACK)]
        ]),
    )


async def _back_to_list(query) -> None:
    telegram_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id)
        sent = await get_sent_shipments(session, user.id)
        received = await get_received_shipments(session, user.id)

    await _send_shipment_list(query.message, sent, received)


async def _get_telegram_id(user_id: int) -> int | None:
    from db.models import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user.telegram_user_id if user else None


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /update `<share_code>`\n"
            "e.g. `/update ABC7X2`",
            parse_mode="Markdown",
        )
        return

    share_code = args[0].upper()
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        shipment = await get_shipment_by_code(session, share_code)

    if not shipment:
        await update.message.reply_text(
            f"No shipment found with code `{share_code}`.",
            parse_mode="Markdown",
        )
        return

    if shipment.sender_user_id != user.id:
        await update.message.reply_text(
            "Only the sender can update this shipment's status."
        )
        return

    next_status = await get_next_status(shipment.status)
    if not next_status:
        await update.message.reply_text(
            "This shipment has already reached its final status."
        )
        return

    emoji = STATUS_EMOJI.get(next_status, "❓")
    label = next_status.value.replace("_", " ").title()

    keyboard = [
        [
            InlineKeyboardButton(
                f"{emoji} {label}",
                callback_data=f"{SHIP_CONFIRM}{shipment.id}_{next_status.value}",
            )
        ],
        [InlineKeyboardButton("« Cancel", callback_data=f"{SHIP_VIEW}{shipment.id}")],
    ]

    await update.message.reply_text(
        f"**Shipment:** `{share_code}`\n"
        f"{shipment.description}\n"
        f"📍 {shipment.origin} → {shipment.destination}\n"
        f"**Current status:** {shipment.status.value.replace('_', ' ').title()}\n\n"
        f"Advance to next status?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def claim_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /claim `<share_code>`\n"
            "e.g. `/claim ABC7X2`",
            parse_mode="Markdown",
        )
        return

    share_code = args[0].upper()
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        shipment = await claim_shipment(session, share_code, user.id)

    if not shipment:
        await update.message.reply_text(
            f"Couldn't claim `{share_code}`. "
            "It might not exist or is already claimed by someone else.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(
        f"✅ **Shipment claimed!**\n\n"
        f"You can now track `{shipment.description}` "
        f"({shipment.origin} → {shipment.destination}).\n\n"
        f"Use /shipments to view details.",
        parse_mode="Markdown",
    )
