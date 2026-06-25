import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

CARRIER_PATTERNS: list[dict[str, Any]] = [
    {
        "carrier_code": "dhl",
        "carrier_name": "DHL Express",
        "patterns": [
            re.compile(r"^\d{10}$"),
            re.compile(r"^\d{12}$"),
            re.compile(r"^[A-Z]{3}\d{7}$"),
            re.compile(r"^\d{9}[A-Z]{2}$"),
            re.compile(r"^JD\d{9}$"),
            re.compile(r"^\d{20}$"),
        ],
    },
    {
        "carrier_code": "fedex",
        "carrier_name": "FedEx",
        "patterns": [
            re.compile(r"^\d{12}$"),
            re.compile(r"^\d{15}$"),
            re.compile(r"^\d{20}$"),
            re.compile(r"^[0-9]{12}[A-Z]{2}$"),
            re.compile(r"^[A-Z]{2}\d{14}$"),
        ],
    },
    {
        "carrier_code": "ups",
        "carrier_name": "UPS",
        "patterns": [
            re.compile(r"^1Z[A-Z0-9]{16}$"),
            re.compile(r"^\d{9}$"),
        ],
    },
    {
        "carrier_code": "royalmail",
        "carrier_name": "Royal Mail",
        "patterns": [
            re.compile(r"^[A-Z]{2}\d{9}GB$"),
        ],
    },
    {
        "carrier_code": "usps",
        "carrier_name": "USPS",
        "patterns": [
            re.compile(r"^\d{20}$"),
            re.compile(r"^9\d{15}$"),
            re.compile(r"^[A-Z]{2}\d{9}US$"),
            re.compile(r"^EA\d{9}US$"),
            re.compile(r"^CP\d{9}US$"),
            re.compile(r"^L[N]\d{9}US$"),
        ],
    },
    {
        "carrier_code": "china_post",
        "carrier_name": "China Post",
        "patterns": [
            re.compile(r"^[A-Z]{2}\d{9}CN$"),
            re.compile(r"^R[A-Z]\d{9}CN$"),
            re.compile(r"^E[A-Z]\d{9}CN$"),
            re.compile(r"^C[A-Z]\d{9}CN$"),
        ],
    },
    {
        "carrier_code": "yanwen",
        "carrier_name": "Yanwen Logistics",
        "patterns": [
            re.compile(r"^YT\d{9}$"),
            re.compile(r"^Y[A-Z]\d{9}$"),
            re.compile(r"^U[A-Z]\d{9}$"),
            re.compile(r"^LP\d{9}$"),
            re.compile(r"^[A-Z]{2}\d{9}YW$"),
        ],
    },
    {
        "carrier_code": "aramex",
        "carrier_name": "Aramex",
        "patterns": [
            re.compile(r"^\d{10}$"),
            re.compile(r"^\d{12}$"),
            re.compile(r"^[A-Z]{3}\d{10}$"),
            re.compile(r"^\d{15}$"),
        ],
    },
    {
        "carrier_code": "gig-logistics",
        "carrier_name": "GIG Logistics",
        "patterns": [
            re.compile(r"^GI\d{8,12}$", re.IGNORECASE),
            re.compile(r"^GIG\d{8,12}$", re.IGNORECASE),
        ],
    },
    {
        "carrier_code": "nipost",
        "carrier_name": "NIPOST",
        "patterns": [
            re.compile(r"^[A-Z]{2}\d{9}NG$"),
            re.compile(r"^NP\d{9,12}$", re.IGNORECASE),
        ],
    },
]


def detect_carrier(tracking_number: str) -> list[dict[str, Any]]:
    stripped = tracking_number.strip().upper()

    if len(stripped) < 6:
        logger.debug("Tracking number too short: %s", tracking_number)
        return []

    results: list[dict[str, Any]] = []

    for carrier in CARRIER_PATTERNS:
        for pattern in carrier["patterns"]:
            if pattern.match(stripped):
                match_strength = _score_match(stripped, pattern)
                confidence = _compute_confidence(
                    carrier["carrier_code"], stripped, match_strength
                )
                results.append(
                    {
                        "carrier_code": carrier["carrier_code"],
                        "carrier_name": carrier["carrier_name"],
                        "confidence": confidence,
                    }
                )
                break

    results.sort(key=lambda r: r["confidence"], reverse=True)

    logger.debug(
        "detect_carrier(%s) => %s", tracking_number, results
    )
    return results


def _score_match(tracking_number: str, pattern: re.Pattern) -> int:
    total_length = len(tracking_number)
    expected_length = _expected_length(pattern)

    if expected_length and total_length == expected_length:
        return 3
    if expected_length and abs(total_length - expected_length) <= 1:
        return 2

    return 1


def _expected_length(pattern: re.Pattern) -> int | None:
    pattern_str = pattern.pattern
    literal_len = 0
    has_variable = False

    i = 0
    while i < len(pattern_str):
        if pattern_str[i] == "\\":
            if i + 1 < len(pattern_str):
                if pattern_str[i + 1] == "d":
                    has_variable = True
                i += 2
        elif pattern_str[i] in ("^", "$"):
            i += 1
        elif pattern_str[i] == "[":
            has_variable = True
            i += 1
            while i < len(pattern_str) and pattern_str[i] != "]":
                i += 1
            i += 1
        elif pattern_str[i] == "{":
            has_variable = True
            i += 1
            num_str = ""
            while i < len(pattern_str) and pattern_str[i] != "}":
                num_str += pattern_str[i]
                i += 1
            if num_str.isdigit():
                return int(num_str)
            i += 1
        elif pattern_str[i] in ("+", "*", "?"):
            has_variable = True
            i += 1
        else:
            if pattern_str[i] != "(":
                literal_len += 1
            i += 1

    return literal_len if not has_variable else None


def _compute_confidence(
    carrier_code: str, _tracking_number: str, match_strength: int
) -> float:
    base = 0.6 + (match_strength - 1) * 0.15

    unique_prefixes: dict[str, float] = {
        "ups": 0.15,
        "usps": 0.10,
        "fedex": 0.05,
        "royalmail": 0.10,
    }

    bonus = unique_prefixes.get(carrier_code, 0.0)
    return round(min(base + bonus, 0.99), 2)
