import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

from config import TRACK17_API_KEY

API_BASE = "https://api.17track.net/track/v2.4"
MAX_RETRIES = 2

CARRIER_CODE_MAP: dict[str, int] = {
    "royalmail": 11031,
    "parcelforce": 11033,
}


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


STATUS_MAP: dict[str, PackageStatus] = {
    "NotFound": PackageStatus.PENDING,
    "InfoReceived": PackageStatus.PENDING,
    "InTransit": PackageStatus.IN_TRANSIT,
    "Expired": PackageStatus.EXCEPTION,
    "AvailableForPickup": PackageStatus.OUT_FOR_DELIVERY,
    "OutForDelivery": PackageStatus.OUT_FOR_DELIVERY,
    "PickUp": PackageStatus.OUT_FOR_DELIVERY,
    "Delivered": PackageStatus.DELIVERED,
    "Alert": PackageStatus.EXCEPTION,
}


def normalize_result(
    tracking_number: str,
    carrier_code: str,
    carrier_name: str,
    raw_data: dict[str, Any],
) -> TrackingResult:
    track_info = raw_data.get("track_info", {})
    latest_status = track_info.get("latest_status", {}) or {}
    raw_status = str(latest_status.get("status", ""))
    status = STATUS_MAP.get(raw_status, PackageStatus.UNKNOWN)

    providers = (track_info.get("tracking") or {}).get("providers", []) or []
    events: list[dict] = []
    for p in providers:
        events.extend(p.get("events", []) or [])

    checkpoints: list[Checkpoint] = []
    for ev in events:
        ts = _parse_timestamp(ev.get("event_timestamp") or ev.get("time_raw"))
        checkpoints.append(
            Checkpoint(
                location=ev.get("event_location", "") or "",
                description=ev.get("event_description", "") or "",
                timestamp=ts,
                raw_status=str(ev.get("event_status_code", "")),
            )
        )

    last_updated = None
    for p in providers:
        sync_time = _parse_timestamp(p.get("latest_sync_time"))
        if sync_time and (last_updated is None or sync_time > last_updated):
            last_updated = sync_time

    time_metrics = track_info.get("time_metrics", {}) or {}
    est_date = time_metrics.get("estimated_delivery_date", {}) or {}
    est_delivery = _parse_timestamp(est_date.get("from"))
    if est_delivery is None:
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


def _resolve_carrier_code(carrier_code: str) -> int | str:
    return CARRIER_CODE_MAP.get(carrier_code, carrier_code)


def _make_payload(tracking_number: str, carrier_code: str) -> list[dict[str, Any]]:
    entry: dict[str, Any] = {"number": tracking_number}
    resolved = _resolve_carrier_code(carrier_code)
    if resolved:
        entry["carrier"] = resolved
    return [entry]


async def register_number(tracking_number: str, carrier_code: str) -> dict[str, Any]:
    headers = {"17token": TRACK17_API_KEY}
    payload = _make_payload(tracking_number, carrier_code)

    async with httpx.AsyncClient(base_url=API_BASE, headers=headers) as client:
        return await _retry_async(client, "POST", "/register", json_data=payload)


async def fetch_tracking_info(
    tracking_number: str, carrier_code: str
) -> dict[str, Any]:
    headers = {"17token": TRACK17_API_KEY}
    payload = _make_payload(tracking_number, carrier_code)

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

    inner = data.get("data", {}) or {}
    accepted = inner.get("accepted", []) or []
    if not accepted:
        raise ValueError("Tracking number not found by any carrier")

    first = accepted[0]
    return normalize_result(tracking_number, carrier_code, carrier_name, first)
