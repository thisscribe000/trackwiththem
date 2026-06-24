import logging

from core.track17_client import (
    get_tracking_result as track17_get_result,
    register_number,
)

logger = logging.getLogger(__name__)

LOCAL_CARRIERS: dict[str, str] = {
    "gig-logistics": "GIG Logistics",
    "nipost": "NIPOST",
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
    return await module.get_tracking_result(tracking_number, carrier_code, carrier_name)
