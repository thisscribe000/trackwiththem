from datetime import datetime, timezone

from core.track17_client import (
    PackageStatus,
    normalize_result,
)


def _make_raw(
    status_code: str = "20",
    last_event: str = "",
    checkpoints: list | None = None,
    updated: str = "",
    estimated_delivery: str = "",
) -> dict:
    return {
        "track": {
            "statusCode": status_code,
            "lastEvent": last_event,
            "checkpoints": checkpoints or [],
            "updated": updated,
            "destinationEstimatedDeliveryDate": estimated_delivery,
        }
    }


def test_maps_pending():
    raw = _make_raw(status_code="10")
    result = normalize_result("TN123", "dhl", "DHL", raw)
    assert result.status == PackageStatus.PENDING


def test_maps_in_transit():
    raw = _make_raw(status_code="20")
    result = normalize_result("TN123", "fedex", "FedEx", raw)
    assert result.status == PackageStatus.IN_TRANSIT


def test_maps_customs():
    raw = _make_raw(status_code="30")
    result = normalize_result("TN123", "ups", "UPS", raw)
    assert result.status == PackageStatus.CUSTOMS


def test_maps_out_for_delivery():
    raw = _make_raw(status_code="40")
    result = normalize_result("TN123", "usps", "USPS", raw)
    assert result.status == PackageStatus.OUT_FOR_DELIVERY


def test_maps_delivered():
    raw = _make_raw(status_code="50")
    result = normalize_result("TN123", "dhl", "DHL", raw)
    assert result.status == PackageStatus.DELIVERED


def test_maps_exception():
    raw = _make_raw(status_code="60")
    result = normalize_result("TN123", "dhl", "DHL", raw)
    assert result.status == PackageStatus.EXCEPTION


def test_maps_unknown_status():
    raw = _make_raw(status_code="999")
    result = normalize_result("TN123", "dhl", "DHL", raw)
    assert result.status == PackageStatus.UNKNOWN


def test_checkpoints_parsed_in_order():
    raw = _make_raw(
        status_code="50",
        checkpoints=[
            {
                "location": "Lagos, NG",
                "description": "Out for delivery",
                "time": "2024-03-15T08:00:00Z",
                "statusCode": "40",
            },
            {
                "location": "Lagos, NG",
                "description": "Package delivered",
                "time": "2024-03-15T14:00:00Z",
                "statusCode": "50",
            },
        ],
    )
    result = normalize_result("TN123", "dhl", "DHL", raw)

    assert len(result.checkpoints) == 2
    assert result.checkpoints[0].location == "Lagos, NG"
    assert result.checkpoints[0].description == "Package delivered"


def test_estimated_delivery_parsed():
    raw = _make_raw(
        status_code="20",
        estimated_delivery="2024-03-20T23:59:00Z",
    )
    result = normalize_result("TN123", "dhl", "DHL", raw)

    assert result.estimated_delivery is not None
    assert result.estimated_delivery.year == 2024


def test_empty_checkpoints():
    raw = _make_raw(status_code="10", checkpoints=None)
    result = normalize_result("TN123", "dhl", "DHL", raw)
    assert result.checkpoints == []


def test_last_updated():
    raw = _make_raw(status_code="20", updated="2024-03-15T10:00:00Z")
    result = normalize_result("TN123", "dhl", "DHL", raw)
    assert result.last_updated is not None
    assert result.last_updated == datetime(
        2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc
    )


def test_handles_missing_track_key():
    raw = {}
    result = normalize_result("TN123", "dhl", "DHL", raw)
    assert result.status == PackageStatus.UNKNOWN
    assert result.checkpoints == []
