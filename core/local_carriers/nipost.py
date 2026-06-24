import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from core.track17_client import Checkpoint, PackageStatus, TrackingResult

logger = logging.getLogger(__name__)

TRACKING_URL = "https://track.nipost.gov.ng/"

STATUS_MAP: dict[str, PackageStatus] = {
    "pending": PackageStatus.PENDING,
    "accept": PackageStatus.IN_TRANSIT,
    "collected": PackageStatus.IN_TRANSIT,
    "despatch": PackageStatus.IN_TRANSIT,
    "dispatch": PackageStatus.IN_TRANSIT,
    "arrived": PackageStatus.IN_TRANSIT,
    "in transit": PackageStatus.IN_TRANSIT,
    "depart": PackageStatus.IN_TRANSIT,
    "forward": PackageStatus.IN_TRANSIT,
    "customs": PackageStatus.CUSTOMS,
    "clearance": PackageStatus.CUSTOMS,
    "out for delivery": PackageStatus.OUT_FOR_DELIVERY,
    "delivery attempt": PackageStatus.OUT_FOR_DELIVERY,
    "delivered": PackageStatus.DELIVERED,
    "signed": PackageStatus.DELIVERED,
    "exception": PackageStatus.EXCEPTION,
    "hold": PackageStatus.EXCEPTION,
    "return": PackageStatus.EXCEPTION,
    "damage": PackageStatus.EXCEPTION,
    "missing": PackageStatus.EXCEPTION,
}


def _map_status(text: str) -> PackageStatus:
    lower = text.lower().strip()
    for keyword, status in STATUS_MAP.items():
        if keyword in lower:
            return status
    return PackageStatus.UNKNOWN


async def get_tracking_result(
    tracking_number: str, carrier_code: str = "nipost", carrier_name: str = "NIPOST"
) -> TrackingResult:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(
                TRACKING_URL,
                params={"tracking_number": tracking_number},
            )
            response.raise_for_status()
    except Exception as e:
        logger.warning("NIPOST scraper failed for %s: %s", tracking_number, e)
        return TrackingResult(
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_name=carrier_name,
            status=PackageStatus.UNKNOWN,
            last_updated=datetime.now(timezone.utc),
        )

    try:
        soup = BeautifulSoup(response.text, "lxml")
        status_elements = soup.select(
            ".status, .track-result, table tr td, .event, .update, .timeline li"
        )

        checkpoints: list[Checkpoint] = []
        for el in status_elements:
            text = el.get_text(strip=True)
            if not text or len(text) < 5:
                continue
            status = _map_status(text)
            checkpoints.append(
                Checkpoint(
                    location="",
                    description=text,
                    timestamp=datetime.now(timezone.utc),
                    raw_status=status.value,
                )
            )

        latest_status = checkpoints[0].raw_status if checkpoints else PackageStatus.UNKNOWN
        try:
            latest_status = PackageStatus(latest_status)
        except ValueError:
            latest_status = PackageStatus.UNKNOWN

        return TrackingResult(
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_name=carrier_name,
            status=latest_status,
            checkpoints=checkpoints,
            last_updated=datetime.now(timezone.utc),
        )
    except Exception as e:
        logger.warning("NIPOST parsing failed for %s: %s", tracking_number, e)
        return TrackingResult(
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_name=carrier_name,
            status=PackageStatus.UNKNOWN,
            last_updated=datetime.now(timezone.utc),
        )
