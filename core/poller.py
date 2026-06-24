import asyncio
import logging
from datetime import datetime, timezone

from telegram import Bot

from config import TRACK17_API_KEY
from core.customs_watchdog import is_stuck_in_customs
from core.local_carriers.registry import get_tracking_result
from core.repository import (
    deactivate_package,
    get_all_active_packages,
    has_seen_checkpoint,
    mark_customs_warning_sent,
    record_checkpoint,
    update_package_status,
)
from core.track17_client import (
    PackageStatus,
)
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

RATE_LIMIT_DELAY = 0.2


async def poll_all_active_packages(bot: Bot) -> None:
    if not TRACK17_API_KEY:
        logger.warning("No 17TRACK API key configured, skipping poll")
        return

    async with AsyncSessionLocal() as session:
        packages = await get_all_active_packages(session)

    if not packages:
        logger.info("No active packages to poll")
        return

    logger.info("Polling %d active packages", len(packages))

    stats = {"checked": 0, "updates": 0, "delivered": 0, "errors": 0, "customs_warnings": 0}

    for pkg in packages:
        try:
            await asyncio.sleep(RATE_LIMIT_DELAY)

            result = await get_tracking_result(
                pkg.tracking_number,
                pkg.carrier_code,
                pkg.carrier_name,
            )

            stats["checked"] += 1
            new_status = result.status.value

            if new_status == "UNKNOWN":
                continue

            latest = result.checkpoints[0] if result.checkpoints else None
            desc = latest.description if latest else ""
            ts = latest.timestamp if latest else None

            from bot.notifier import (
                send_customs_delay_warning,
                send_delivered_notification,
                send_status_update,
            )

            if new_status != pkg.status:
                async with AsyncSessionLocal() as session:
                    if not await has_seen_checkpoint(session, pkg.id, desc, ts):
                        await record_checkpoint(
                            session,
                            package_id=pkg.id,
                            status=new_status,
                            location=latest.location if latest else None,
                            description=desc,
                            timestamp=ts,
                        )

                    await update_package_status(
                        session,
                        package_id=pkg.id,
                        status=new_status,
                        location=latest.location if latest else None,
                        checkpoint_time=ts,
                    )

                if new_status == "DELIVERED":
                    await send_delivered_notification(
                        bot, pkg.user_id, pkg.tracking_number, pkg.carrier_name
                    )
                    async with AsyncSessionLocal() as session:
                        await deactivate_package(session, pkg.id)
                    stats["delivered"] += 1
                else:
                    await send_status_update(
                        bot,
                        pkg.user_id,
                        pkg.tracking_number,
                        pkg.carrier_name,
                        new_status,
                        pkg.status,
                        location=latest.location if latest else None,
                    )
                stats["updates"] += 1

            if is_stuck_in_customs(pkg):
                days = (
                    (datetime.now(timezone.utc) - pkg.last_checkpoint_time).days
                    if pkg.last_checkpoint_time
                    else 0
                )

                async with AsyncSessionLocal() as session:
                    await mark_customs_warning_sent(session, pkg.id)

                await send_customs_delay_warning(
                    bot,
                    pkg.user_id,
                    pkg.tracking_number,
                    pkg.carrier_name,
                    days_in_customs=days,
                )
                stats["customs_warnings"] += 1

        except Exception as e:
            logger.error(
                "Error polling package %s: %s",
                pkg.tracking_number,
                e,
                exc_info=True,
            )
            stats["errors"] += 1

    logger.info(
        "Poll complete: %d checked, %d updates sent, %d delivered, %d customs warnings, %d errors",
        stats["checked"],
        stats["updates"],
        stats["delivered"],
        stats["customs_warnings"],
        stats["errors"],
    )
