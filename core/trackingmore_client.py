import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import TRACKINGMORE_API_KEY
from core.track17_client import Checkpoint, PackageStatus, TrackingResult

API_BASE = "https://api.trackingmore.com/v4"

CARRIER_MAP: dict[str, str] = {
    "nipost": "nigeria-post",
    "gig-logistics": "gig-logistics",
}

logger = logging.getLogger(__name__)


STATUS_MAP: dict[str, PackageStatus] = {
    "pending": PackageStatus.PENDING,
    "info received": PackageStatus.PENDING,
    "in transit": PackageStatus.IN_TRANSIT,
    "transit": PackageStatus.IN_TRANSIT,
    "out for delivery": PackageStatus.OUT_FOR_DELIVERY,
    "delivered": PackageStatus.DELIVERED,
    "exception": PackageStatus.EXCEPTION,
    "expired": PackageStatus.EXCEPTION,
    "available for pickup": PackageStatus.OUT_FOR_DELIVERY,
}


async def _request(
    method: str, path: str, json_data: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    if not TRACKINGMORE_API_KEY:
        logger.debug("TrackingMore API key not configured")
        return None

    headers = {
        "Tracking-Api-Key": TRACKINGMORE_API_KEY,
        "Content-Type": "application/json",
    }

    url = f"{API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(method, url, json=json_data, headers=headers)
            if response.status_code == 429:
                logger.warning("TrackingMore rate limited")
                return None
            if response.status_code in (401, 403):
                logger.warning("TrackingMore auth failed (check API key)")
                return None
            try:
                body = response.json()
            except Exception:
                body = {"meta": {"code": response.status_code, "message": response.text[:200]}}

            if response.status_code >= 500:
                logger.warning("TrackingMore server error: %s", response.status_code)
                return None

            if response.status_code >= 400:
                code = body.get("meta", {}).get("code", 0)
                if code == 4101:
                    return body

            response.raise_for_status()
            return body
    except httpx.TimeoutException:
        logger.warning("TrackingMore request timed out")
        return None
    except Exception as e:
        logger.warning("TrackingMore request failed: %s", e)
        return None


def _map_status(raw_status: str) -> PackageStatus:
    return STATUS_MAP.get(raw_status.lower().strip(), PackageStatus.UNKNOWN)


def _normalize_item(
    tracking_number: str,
    carrier_code: str,
    carrier_name: str,
    item: dict[str, Any],
) -> TrackingResult | None:
    try:
        origin_info = item.get("origin_info", {}) or {}
        track_info = origin_info.get("trackinfo", []) or []

        checkpoints = []
        for ev in track_info:
            ts = None
            raw_date = ev.get("checkpoint_date") or ""
            try:
                if raw_date:
                    ts = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

            raw_status = ev.get("checkpoint_delivery_status", "") or ""
            status = _map_status(raw_status)
            description = ev.get("tracking_detail", "") or ""
            location = ev.get("location", "") or ""

            checkpoints.append(Checkpoint(
                location=location,
                description=description,
                timestamp=ts,
                raw_status=status,
            ))

        checkpoints.reverse()

        latest_status = PackageStatus.UNKNOWN
        item_status = item.get("delivery_status", "") or item.get("status", "") or ""
        if item_status:
            mapped = _map_status(item_status)
            if mapped != PackageStatus.UNKNOWN:
                latest_status = mapped

        if latest_status == PackageStatus.UNKNOWN and checkpoints:
            latest_status = checkpoints[-1].raw_status

        return TrackingResult(
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_name=carrier_name,
            status=latest_status,
            checkpoints=checkpoints,
            last_updated=datetime.now(timezone.utc),
        )
    except Exception as e:
        logger.warning("TrackingMore normalize failed: %s", e)
        return None


async def create_tracking(tracking_number: str, carrier_code: str) -> dict[str, Any] | None:
    payload = {
        "tracking_number": tracking_number,
        "courier_code": carrier_code,
    }
    result = await _request("POST", "/trackings/create", payload)
    if result is None:
        return None
    meta = result.get("meta", {}) or {}
    code = meta.get("code", 0)
    if code in (200, 201, 202):
        return result
    if code == 4101:
        return result
    logger.info("TrackingMore create returned code %s for %s", code, tracking_number)
    return None


async def get_tracking_result(
    tracking_number: str,
    carrier_code: str,
    carrier_name: str,
) -> TrackingResult | None:
    if not TRACKINGMORE_API_KEY:
        return None

    resolved_carrier = CARRIER_MAP.get(carrier_code, carrier_code)

    await create_tracking(tracking_number, resolved_carrier)

    path = f"/trackings/get?tracking_numbers={tracking_number}"
    data = await _request("GET", path)

    if data:
        items = data.get("data", [])
        if items:
            for item in items:
                if item.get("courier_code") == resolved_carrier:
                    result = _normalize_item(tracking_number, carrier_code, carrier_name, item)
                    if result:
                        return result

            result = _normalize_item(tracking_number, carrier_code, carrier_name, items[0])
            if result:
                return result

    return None


async def detect_carrier(tracking_number: str) -> list[dict[str, Any]]:
    if not TRACKINGMORE_API_KEY:
        return []

    payload = {"tracking_number": tracking_number}
    result = await _request("POST", "/couriers/detect", payload)
    if result is None:
        return []

    data = result.get("data", [])
    if not data:
        return []

    carriers = []
    for item in data if isinstance(data, list) else [data]:
        carriers.append({
            "carrier_code": item.get("courier_code", "") or item.get("code", ""),
            "carrier_name": item.get("courier_name", "") or item.get("name", ""),
            "confidence": 0.5,
        })
    return carriers
