import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

from config import TRACK17_API_KEY

API_BASE = "https://api.17track.net/track/v2"
MAX_RETRIES = 2


class PackageStatus(Enum):
    PENDING = "PENDING"
    IN_TRANSIT = "IN_TRANSIT"
    CUSTOMS = "CUSTOMS"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    EXCEPTION = "EXCEPTION"
    UNKNOWN = "UNKNOWN"


@dataclass
class Checkpoint:
    location: str
    description: str
    timestamp: datetime | None
    raw_status: str


@dataclass
class TrackingResult:
    tracking_number: str
    carrier_code: str
    carrier_name: str
    status: PackageStatus
    checkpoints: list[Checkpoint] = field(default_factory=list)
    estimated_delivery: datetime | None = None
    last_updated: datetime | None = None


def _map_17track_status(raw: str) -> tuple[PackageStatus, str]:
    mapping: dict[str, tuple[PackageStatus, str]] = {
        "10": (PackageStatus.PENDING, "Pending"),
        "11": (PackageStatus.PENDING, "Information received"),
        "20": (PackageStatus.IN_TRANSIT, "In transit"),
        "21": (PackageStatus.IN_TRANSIT, "Departed"),
        "22": (PackageStatus.IN_TRANSIT, "Arrived"),
        "23": (PackageStatus.IN_TRANSIT, "In transit"),
        "30": (PackageStatus.CUSTOMS, "Customs clearance"),
        "31": (PackageStatus.CUSTOMS, "Customs cleared"),
        "35": (PackageStatus.CUSTOMS, "Customs hold"),
        "40": (PackageStatus.OUT_FOR_DELIVERY, "Out for delivery"),
        "41": (PackageStatus.OUT_FOR_DELIVERY, "Ready for pickup"),
        "50": (PackageStatus.DELIVERED, "Delivered"),
        "51": (PackageStatus.DELIVERED, "Delivery confirmed"),
        "60": (PackageStatus.EXCEPTION, "Exception"),
        "70": (PackageStatus.EXCEPTION, "Returning"),
        "71": (PackageStatus.EXCEPTION, "Return to sender"),
        "80": (PackageStatus.EXCEPTION, "Returned"),
    }
    return mapping.get(raw, (PackageStatus.UNKNOWN, "Unknown"))


def normalize_result(
    tracking_number: str,
    carrier_code: str,
    carrier_name: str,
    raw_data: dict[str, Any],
) -> TrackingResult:
    track_info = raw_data.get("track", {})
    last_event = track_info.get("lastEvent", "") or ""
    raw_status = str(track_info.get("statusCode", ""))

    status, _ = _map_17track_status(raw_status)

    checkpoints_raw = track_info.get("checkpoints", []) or []
    checkpoints: list[Checkpoint] = []
    for cp in checkpoints_raw:
        ts = _parse_timestamp(cp.get("time"))
        checkpoints.append(
            Checkpoint(
                location=cp.get("location", "") or "",
                description=cp.get("description", "") or "",
                timestamp=ts,
                raw_status=str(cp.get("statusCode", "")),
            )
        )
    checkpoints.reverse()

    last_updated = _parse_timestamp(track_info.get("updated"))
    est_delivery = _parse_timestamp(track_info.get("destinationEstimatedDeliveryDate"))
    if est_delivery is None:
        est_delivery = _parse_timestamp(track_info.get("originEstimatedDeliveryDate"))

    return TrackingResult(
        tracking_number=tracking_number,
        carrier_code=carrier_code,
        carrier_name=carrier_name,
        status=status,
        checkpoints=checkpoints,
        estimated_delivery=est_delivery,
        last_updated=last_updated,
    )


def _parse_timestamp(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


async def _retry_async(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    json_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.request(
                method, url, json=json_data, timeout=15
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
            continue
        except httpx.HTTPStatusError as e:
            last_exc = e
            if attempt < MAX_RETRIES and e.response.status_code >= 500:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
        except httpx.RequestError as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                continue
            raise

    raise RuntimeError(f"Request failed after {MAX_RETRIES} retries") from last_exc


async def register_number(tracking_number: str, carrier_code: str) -> dict[str, Any]:
    headers = {"17token": TRACK17_API_KEY}
    payload = [
        {
            "number": tracking_number,
            "carrier": carrier_code,
        }
    ]

    async with httpx.AsyncClient(base_url=API_BASE, headers=headers) as client:
        return await _retry_async(client, "POST", "/register", json_data=payload)


async def fetch_tracking_info(
    tracking_number: str, carrier_code: str
) -> dict[str, Any]:
    headers = {"17token": TRACK17_API_KEY}
    payload = [
        {
            "number": tracking_number,
            "carrier": carrier_code,
        }
    ]

    async with httpx.AsyncClient(base_url=API_BASE, headers=headers) as client:
        return await _retry_async(
            client, "POST", "/gettrackinfo", json_data=payload
        )


async def get_tracking_result(
    tracking_number: str,
    carrier_code: str,
    carrier_name: str,
) -> TrackingResult:
    data = await fetch_tracking_info(tracking_number, carrier_code)

    accepted = data.get("accepted", []) or []
    if not accepted:
        raise ValueError("Tracking number not found by any carrier")

    first = accepted[0]
    return normalize_result(tracking_number, carrier_code, carrier_name, first)
