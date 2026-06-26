import logging

from core.track17_client import (
    get_tracking_result as track17_get_result,
    register_number,
)

logger = logging.getLogger(__name__)

LOCAL_CARRIERS: dict[str, str] = {
    "gig-logistics": "GIG Logistics",
    "nipost": "NIPOST",
    "speedaf": "Speedaf Express",
}


def is_local_carrier(carrier_code: str) -> bool:
    return carrier_code in LOCAL_CARRIERS


async def get_tracking_result(
    tracking_number: str,
    carrier_code: str,
    carrier_name: str,
) -> "TrackingResult":
    from core.track17_client import TrackingResult

    if not is_local_carrier(carrier_code):
        await register_number(tracking_number, carrier_code)
        return await track17_get_result(tracking_number, carrier_code, carrier_name)

    carrier_lookup: dict[str, str] = {
        "gig-logistics": "core.local_carriers.gig_logistics",
        "nipost": "core.local_carriers.nipost",
    }

    module_path = carrier_lookup.get(carrier_code)

    if carrier_code == "speedaf":
        return await _trackingmore_fallback(tracking_number, carrier_code, carrier_name)

    if not module_path:
        logger.error("Unknown local carrier code: %s", carrier_code)
        return TrackingResult(
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_name=carrier_name,
            status=__import__("core.track17_client", fromlist=["PackageStatus"]).PackageStatus.UNKNOWN,
            last_updated=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
        )

    import importlib

    module = importlib.import_module(module_path)
    result = await module.get_tracking_result(tracking_number, carrier_code, carrier_name)

    PackageStatus_cls = __import__("core.track17_client", fromlist=["PackageStatus"]).PackageStatus
    if result and result.status in (PackageStatus_cls.UNKNOWN, None):
        logger.info("Local carrier %s returned UNKNOWN for %s; falling back to 17TRACK", carrier_code, tracking_number)
        try:
            await register_number(tracking_number, "")
            result = await track17_get_result(tracking_number, "", carrier_name)
        except Exception as e:
            logger.warning("17TRACK fallback also failed for %s: %s", tracking_number, e)

        if result and result.status in (PackageStatus_cls.UNKNOWN, None) and carrier_code == "nipost":
            logger.info("17TRACK also failed for NIPOST %s; trying TrackingMore", tracking_number)
            result = await _trackingmore_fallback(tracking_number, carrier_code, carrier_name)

    return result


async def _trackingmore_fallback(tracking_number: str, carrier_code: str, carrier_name: str):
    from core.track17_client import PackageStatus, TrackingResult as TR
    from datetime import datetime, timezone
    try:
        from core.trackingmore_client import (
            get_tracking_result as tm_get_result,
            detect_carrier as tm_detect,
        )

        carriers_to_try = [carrier_code]

        detected = await tm_detect(tracking_number)
        for d in detected:
            code = d.get("carrier_code")
            if code and code not in carriers_to_try:
                carriers_to_try.append(code)

        for cc in carriers_to_try:
            tm_result = await tm_get_result(tracking_number, cc, carrier_name)
            if tm_result and tm_result.checkpoints:
                if carrier_code in ("nipost",) and cc != carrier_code:
                    tm_result.carrier_name = carrier_name
                return tm_result

        return TR(
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_name=carrier_name,
            status=PackageStatus.UNKNOWN,
            last_updated=datetime.now(timezone.utc),
        )
    except Exception as e:
        logger.warning("TrackingMore fallback failed for %s: %s", tracking_number, e)
        return TR(
            tracking_number=tracking_number,
            carrier_code=carrier_code,
            carrier_name=carrier_name,
            status=PackageStatus.UNKNOWN,
            last_updated=datetime.now(timezone.utc),
        )
