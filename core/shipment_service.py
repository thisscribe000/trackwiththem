import logging
import random
import string
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Shipment, ShipmentStatus, ShipmentStatusHistory

logger = logging.getLogger(__name__)

SHIPMENT_STATUS_FLOW: list[ShipmentStatus] = [
    ShipmentStatus.PREPARING,
    ShipmentStatus.AT_PARK,
    ShipmentStatus.IN_TRANSIT,
    ShipmentStatus.ARRIVED,
    ShipmentStatus.DELIVERED,
]

STATUS_EMOJI: dict[ShipmentStatus, str] = {
    ShipmentStatus.PREPARING: "📦",
    ShipmentStatus.AT_PARK: "🚏",
    ShipmentStatus.IN_TRANSIT: "🚌",
    ShipmentStatus.ARRIVED: "🏁",
    ShipmentStatus.DELIVERED: "✅",
    ShipmentStatus.CANCELLED: "❌",
}


def _generate_share_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=6))


async def create_shipment(
    session: AsyncSession,
    sender_user_id: int,
    receiver_phone: str,
    description: str,
    origin: str,
    destination: str,
    bus_company: str | None = None,
    bus_flight_number: str | None = None,
) -> Shipment:
    for _ in range(10):
        code = _generate_share_code()
        existing = await session.execute(
            select(Shipment).where(Shipment.share_code == code)
        )
        if not existing.scalar_one_or_none():
            break
    else:
        raise RuntimeError("Failed to generate unique share code after 10 attempts")

    shipment = Shipment(
        share_code=code,
        sender_user_id=sender_user_id,
        receiver_phone=receiver_phone,
        description=description,
        origin=origin,
        destination=destination,
        bus_company=bus_company,
        bus_flight_number=bus_flight_number,
        status=ShipmentStatus.PREPARING,
    )
    session.add(shipment)
    await session.commit()
    await session.refresh(shipment)

    await _record_history(session, shipment.id, ShipmentStatus.PREPARING, "sender", origin)
    return shipment


async def get_shipment_by_code(
    session: AsyncSession, share_code: str
) -> Shipment | None:
    result = await session.execute(
        select(Shipment).where(Shipment.share_code == share_code.upper())
    )
    return result.scalar_one_or_none()


async def get_shipments_for_user(
    session: AsyncSession, user_id: int
) -> list[Shipment]:
    result = await session.execute(
        select(Shipment)
        .where(
            (Shipment.sender_user_id == user_id)
            | (Shipment.receiver_user_id == user_id),
            Shipment.is_active == True,
        )
        .order_by(Shipment.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_sent_shipments(
    session: AsyncSession, user_id: int
) -> list[Shipment]:
    result = await session.execute(
        select(Shipment)
        .where(
            Shipment.sender_user_id == user_id,
            Shipment.is_active == True,
        )
        .order_by(Shipment.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_received_shipments(
    session: AsyncSession, user_id: int
) -> list[Shipment]:
    result = await session.execute(
        select(Shipment)
        .where(
            Shipment.receiver_user_id == user_id,
            Shipment.is_active == True,
        )
        .order_by(Shipment.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_next_status(
    current: ShipmentStatus,
) -> ShipmentStatus | None:
    try:
        idx = SHIPMENT_STATUS_FLOW.index(current)
        if idx < len(SHIPMENT_STATUS_FLOW) - 1:
            return SHIPMENT_STATUS_FLOW[idx + 1]
        return None
    except ValueError:
        return None


async def update_shipment_status(
    session: AsyncSession,
    shipment_id: int,
    new_status: ShipmentStatus,
    updated_by: str = "sender",
    location: str | None = None,
    description: str | None = None,
) -> Shipment | None:
    result = await session.execute(
        select(Shipment).where(Shipment.id == shipment_id)
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        return None

    shipment.status = new_status
    shipment.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(shipment)

    await _record_history(
        session, shipment_id, new_status, updated_by, location, description
    )
    return shipment


async def _record_history(
    session: AsyncSession,
    shipment_id: int,
    status: ShipmentStatus,
    updated_by: str,
    location: str | None = None,
    description: str | None = None,
) -> None:
    entry = ShipmentStatusHistory(
        shipment_id=shipment_id,
        status=status.value,
        location=location,
        description=description,
        updated_by=updated_by,
    )
    session.add(entry)
    await session.commit()


async def claim_shipment(
    session: AsyncSession,
    share_code: str,
    receiver_user_id: int,
    receiver_phone: str | None = None,
) -> Shipment | None:
    shipment = await get_shipment_by_code(session, share_code)
    if not shipment:
        return None
    if shipment.receiver_user_id is not None:
        return None

    if receiver_phone and shipment.receiver_phone != receiver_phone:
        return None

    shipment.receiver_user_id = receiver_user_id
    shipment.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(shipment)
    return shipment


async def cancel_shipment(
    session: AsyncSession, shipment_id: int, user_id: int
) -> Shipment | None:
    result = await session.execute(
        select(Shipment).where(
            Shipment.id == shipment_id,
            Shipment.sender_user_id == user_id,
        )
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        return None

    shipment.status = ShipmentStatus.CANCELLED
    shipment.is_active = False
    shipment.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(shipment)
    return shipment


def format_shipment_status(shipment: Shipment) -> str:
    emoji = STATUS_EMOJI.get(shipment.status, "❓")
    status_label = shipment.status.value.replace("_", " ").title()

    lines = [
        f"{emoji} **{shipment.description}**",
        f"`{shipment.share_code}`",
        "",
        f"**Status:** {status_label}",
        f"📍 {shipment.origin} → {shipment.destination}",
    ]

    if shipment.bus_company or shipment.bus_flight_number:
        bus = shipment.bus_company or ""
        flight = shipment.bus_flight_number or ""
        parts = [p for p in [bus, flight] if p]
        lines.append(f"🚌 **{', '.join(parts)}**")

    if shipment.receiver_phone:
        lines.append(f"📞 {shipment.receiver_phone}")

    lines.append("")
    lines.append(
        f"_Created {shipment.created_at.strftime('%d %b %Y, %H:%M UTC')}_"
    )
    return "\n".join(lines)
