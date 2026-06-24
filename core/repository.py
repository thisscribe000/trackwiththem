from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import StatusHistory, TrackedPackage, User


async def get_or_create_user(
    session: AsyncSession, telegram_user_id: int
) -> User:
    result = await session.execute(
        select(User).where(User.telegram_user_id == telegram_user_id)
    )
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(telegram_user_id=telegram_user_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def add_tracked_package(
    session: AsyncSession,
    user_id: int,
    tracking_number: str,
    carrier_code: str,
    carrier_name: str,
    status: str = "UNKNOWN",
    last_checkpoint_location: str | None = None,
    last_checkpoint_time: datetime | None = None,
    estimated_delivery: datetime | None = None,
) -> TrackedPackage:
    existing = await session.execute(
        select(TrackedPackage).where(
            TrackedPackage.user_id == user_id,
            TrackedPackage.tracking_number == tracking_number,
        )
    )
    pkg = existing.scalar_one_or_none()
    if pkg:
        pkg.status = status
        pkg.carrier_code = carrier_code
        pkg.carrier_name = carrier_name
        pkg.last_checkpoint_location = last_checkpoint_location
        pkg.last_checkpoint_time = last_checkpoint_time
        pkg.estimated_delivery = estimated_delivery
        pkg.is_active = True
        pkg.updated_at = datetime.now(timezone.utc)
    else:
        pkg = TrackedPackage(
            user_id=user_id,
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_name=carrier_name,
            status=status,
            last_checkpoint_location=last_checkpoint_location,
            last_checkpoint_time=last_checkpoint_time,
            estimated_delivery=estimated_delivery,
        )
        session.add(pkg)

    await session.commit()
    await session.refresh(pkg)
    return pkg


async def get_active_packages_for_user(
    session: AsyncSession, user_id: int
) -> list[TrackedPackage]:
    result = await session.execute(
        select(TrackedPackage)
        .where(
            TrackedPackage.user_id == user_id,
            TrackedPackage.is_active == True,
        )
        .order_by(TrackedPackage.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_all_active_packages(
    session: AsyncSession,
) -> list[TrackedPackage]:
    result = await session.execute(
        select(TrackedPackage).where(TrackedPackage.is_active == True)
    )
    return list(result.scalars().all())


async def update_package_status(
    session: AsyncSession,
    package_id: int,
    status: str,
    location: str | None = None,
    checkpoint_time: datetime | None = None,
) -> None:
    await session.execute(
        update(TrackedPackage)
        .where(TrackedPackage.id == package_id)
        .values(
            status=status,
            last_checkpoint_location=location,
            last_checkpoint_time=checkpoint_time,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()


async def mark_customs_warning_sent(
    session: AsyncSession, package_id: int
) -> None:
    await session.execute(
        update(TrackedPackage)
        .where(TrackedPackage.id == package_id)
        .values(customs_warning_sent=True, updated_at=datetime.now(timezone.utc))
    )
    await session.commit()


async def deactivate_package(
    session: AsyncSession, package_id: int
) -> None:
    await session.execute(
        update(TrackedPackage)
        .where(TrackedPackage.id == package_id)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    await session.commit()


async def has_seen_checkpoint(
    session: AsyncSession,
    package_id: int,
    description: str,
    timestamp: datetime | None,
) -> bool:
    query = select(StatusHistory).where(
        StatusHistory.package_id == package_id,
        StatusHistory.description == description,
    )
    if timestamp:
        query = query.where(StatusHistory.timestamp == timestamp)

    result = await session.execute(query)
    return result.scalar_one_or_none() is not None


async def record_checkpoint(
    session: AsyncSession,
    package_id: int,
    status: str,
    location: str | None = None,
    description: str | None = None,
    timestamp: datetime | None = None,
) -> StatusHistory:
    entry = StatusHistory(
        package_id=package_id,
        status=status,
        location=location,
        description=description,
        timestamp=timestamp,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry
