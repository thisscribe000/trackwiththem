import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.copy import (
    DASHBOARD_EMPTY,
    DASHBOARD_HEADER,
    HISTORY_EMPTY,
    HISTORY_HEADER,
    RENAME_CONFIRMED,
    RENAME_PROMPT,
    STOP_CANCELLED,
    STOP_CONFIRM_PROMPT,
    STOP_CONFIRMED,
    progress_bar,
)
from core.repository import (
    add_tracked_package,
    deactivate_package,
    get_active_packages_for_user,
    get_or_create_user,
)
from core.track17_client import PackageStatus
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

PAGE_SIZE = 5

PAGE_PREFIX = "dash_page_"
RENAME_PREFIX = "dash_rename_"
STOP_PREFIX = "dash_stop_"
CONFIRM_STOP_PREFIX = "dash_cstop_"
CANCEL_STOP_PREFIX = "dash_xstop_"
HISTORY_PREFIX = "dash_hist_"
BACK_ACTION = "dash_back"


def _status_emoji(status: str) -> str:
    mapping = {
        "PENDING": "📋",
        "IN_TRANSIT": "🚚",
        "CUSTOMS": "🛃",
        "OUT_FOR_DELIVERY": "📬",
        "DELIVERED": "✅",
        "EXCEPTION": "⚠️",
    }
    return mapping.get(status, "❓")


def _relative_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    if not dt.tzinfo:
        now = datetime.now(timezone.utc)
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    if weeks < 4:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    return dt.strftime("%d %b %Y")


async def mypackages_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.message or not update.effective_user:
        return

    telegram_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id)
        packages = await get_active_packages_for_user(session, user.id)

    if not packages:
        await update.message.reply_text(DASHBOARD_EMPTY)
        return

    await _send_package_page(update.message, packages, page=0)


async def _send_package_page(
    message, packages: list, page: int,
) -> None:
    total = len(packages)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_packages = packages[start:end]

    lines = [DASHBOARD_HEADER, ""]
    for pkg in page_packages:
        emoji = _status_emoji(pkg.status)
        nickname = f" ({pkg.nickname})" if pkg.nickname else ""
        try:
            bar = progress_bar(PackageStatus(pkg.status))
        except (ValueError, KeyError):
            bar = ""
        location = (
            f" — {pkg.last_checkpoint_location}" if pkg.last_checkpoint_location else ""
        )
        relative = (
            f" · {_relative_time(pkg.last_checkpoint_time)}"
            if pkg.last_checkpoint_time
            else ""
        )
        lines.append(
            f"{emoji} **{pkg.carrier_name}**{nickname}"
            f"\n`{pkg.tracking_number}`"
            f"\n{bar}"
            f"\n{pkg.status.replace('_', ' ').title()}{location}{relative}"
        )

    if total > PAGE_SIZE:
        lines.append(f"\n_Page {page + 1} of {(total + PAGE_SIZE - 1) // PAGE_SIZE}_")

    keyboard = []
    for pkg in page_packages:
        keyboard.append([
            InlineKeyboardButton(
                "✏️ Rename", callback_data=f"{RENAME_PREFIX}{pkg.id}"
            ),
            InlineKeyboardButton(
                "⏹ Stop", callback_data=f"{STOP_PREFIX}{pkg.id}"
            ),
            InlineKeyboardButton(
                "📜 History", callback_data=f"{HISTORY_PREFIX}{pkg.id}"
            ),
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("◀️ Prev", callback_data=f"{PAGE_PREFIX}{page - 1}")
        )
    if end < total:
        nav_buttons.append(
            InlineKeyboardButton("Next ▶️", callback_data=f"{PAGE_PREFIX}{page + 1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=reply_markup
    )


async def dashboard_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if not query or not query.data or not query.message:
        return

    await query.answer()
    data = query.data

    if data.startswith(PAGE_PREFIX):
        page = int(data[len(PAGE_PREFIX):])
        await _handle_page(query, page)
    elif data.startswith(RENAME_PREFIX):
        pkg_id = int(data[len(RENAME_PREFIX):])
        await _handle_rename(query, context, pkg_id)
    elif data.startswith(STOP_PREFIX):
        pkg_id = int(data[len(STOP_PREFIX):])
        await _handle_stop_confirm(query, pkg_id)
    elif data.startswith(CONFIRM_STOP_PREFIX):
        pkg_id = int(data[len(CONFIRM_STOP_PREFIX):])
        await _handle_stop_execute(query, pkg_id)
    elif data.startswith(CANCEL_STOP_PREFIX):
        pkg_id = int(data[len(CANCEL_STOP_PREFIX):])
        await _handle_stop_cancel(query, pkg_id)
    elif data.startswith(HISTORY_PREFIX):
        pkg_id = int(data[len(HISTORY_PREFIX):])
        await _handle_history(query, pkg_id)
    elif data == BACK_ACTION:
        await _handle_back(query)


async def _handle_page(query, page: int) -> None:
    telegram_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id)
        packages = await get_active_packages_for_user(session, user.id)

    if not packages:
        await query.edit_message_text(DASHBOARD_EMPTY)
        return

    total = len(packages)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_packages = packages[start:end]

    lines = [DASHBOARD_HEADER, ""]
    for pkg in page_packages:
        emoji = _status_emoji(pkg.status)
        nickname = f" ({pkg.nickname})" if pkg.nickname else ""
        try:
            bar = progress_bar(PackageStatus(pkg.status))
        except (ValueError, KeyError):
            bar = ""
        location = (
            f" — {pkg.last_checkpoint_location}" if pkg.last_checkpoint_location else ""
        )
        relative = (
            f" · {_relative_time(pkg.last_checkpoint_time)}"
            if pkg.last_checkpoint_time
            else ""
        )
        lines.append(
            f"{emoji} **{pkg.carrier_name}**{nickname}"
            f"\n`{pkg.tracking_number}`"
            f"\n{bar}"
            f"\n{pkg.status.replace('_', ' ').title()}{location}{relative}"
        )

    if total > PAGE_SIZE:
        lines.append(f"\n_Page {page + 1} of {(total + PAGE_SIZE - 1) // PAGE_SIZE}_")

    keyboard = []
    for pkg in page_packages:
        keyboard.append([
            InlineKeyboardButton(
                "✏️ Rename", callback_data=f"{RENAME_PREFIX}{pkg.id}"
            ),
            InlineKeyboardButton(
                "⏹ Stop", callback_data=f"{STOP_PREFIX}{pkg.id}"
            ),
            InlineKeyboardButton(
                "📜 History", callback_data=f"{HISTORY_PREFIX}{pkg.id}"
            ),
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("◀️ Prev", callback_data=f"{PAGE_PREFIX}{page - 1}")
        )
    if end < total:
        nav_buttons.append(
            InlineKeyboardButton("Next ▶️", callback_data=f"{PAGE_PREFIX}{page + 1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _handle_rename(query, context, pkg_id: int) -> None:
    context.user_data["pending_rename"] = pkg_id
    await query.edit_message_text(RENAME_PROMPT)


async def _handle_stop_confirm(query, pkg_id: int) -> None:
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Yes, stop", callback_data=f"{CONFIRM_STOP_PREFIX}{pkg_id}"
            ),
            InlineKeyboardButton(
                "❌ Cancel", callback_data=f"{CANCEL_STOP_PREFIX}{pkg_id}"
            ),
        ]
    ]
    await query.edit_message_text(
        STOP_CONFIRM_PROMPT,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _handle_stop_execute(query, pkg_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await deactivate_package(session, pkg_id)
    await query.edit_message_text(
        STOP_CONFIRMED,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to packages", callback_data=BACK_ACTION)]
        ]),
    )


async def _handle_stop_cancel(query, pkg_id: int) -> None:
    await query.edit_message_text(
        STOP_CANCELLED,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to packages", callback_data=BACK_ACTION)]
        ]),
    )


async def _handle_history(query, pkg_id: int) -> None:
    from db.models import StatusHistory, TrackedPackage
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        pkg_result = await session.execute(
            select(TrackedPackage).where(TrackedPackage.id == pkg_id)
        )
        pkg = pkg_result.scalar_one_or_none()
        if not pkg:
            await query.edit_message_text("Package not found.")
            return

        hist_result = await session.execute(
            select(StatusHistory)
            .where(StatusHistory.package_id == pkg_id)
            .order_by(StatusHistory.timestamp.asc())
        )
        history = list(hist_result.scalars().all())

    header = HISTORY_HEADER.format(
        tracking_number=pkg.tracking_number, carrier_name=pkg.carrier_name
    )
    lines = [header, ""]

    if not history:
        lines.append(HISTORY_EMPTY)
    else:
        for entry in history:
            relative = _relative_time(entry.timestamp) if entry.timestamp else ""
            loc = f" — {entry.location}" if entry.location else ""
            desc = f" — {entry.description}" if entry.description else ""
            status_label = entry.status.replace("_", " ").title()
            lines.append(f"✓ {status_label}{loc}{desc}")
            if relative:
                lines[-1] += f" _{relative}_"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back to packages", callback_data=BACK_ACTION)]
    ])
    await query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=keyboard
    )


async def _handle_back(query) -> None:
    telegram_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id)
        packages = await get_active_packages_for_user(session, user.id)

    if not packages:
        await query.edit_message_text(DASHBOARD_EMPTY)
        return

    await _send_package_page(query.message, packages, page=0)


async def handle_rename_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.message or not update.message.text:
        return

    pkg_id = context.user_data.pop("pending_rename", None)
    if pkg_id is None:
        return

    nickname = update.message.text.strip()
    if not nickname:
        await update.message.reply_text("Nickname can't be empty. Try again or send /cancel.")
        context.user_data["pending_rename"] = pkg_id
        return

    if len(nickname) > 255:
        await update.message.reply_text(
            "Nickname is too long (max 255 characters). Try a shorter one."
        )
        context.user_data["pending_rename"] = pkg_id
        return

    from db.models import TrackedPackage
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrackedPackage).where(TrackedPackage.id == pkg_id)
        )
        pkg = result.scalar_one_or_none()
        if pkg:
            pkg.nickname = nickname
            await session.commit()

    await update.message.reply_text(
        RENAME_CONFIRMED.format(nickname=nickname), parse_mode="Markdown"
    )
