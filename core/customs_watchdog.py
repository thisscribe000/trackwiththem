import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CUSTOMS_DELAY_DAYS = int(os.environ.get("CUSTOMS_DELAY_DAYS", "4"))


def is_stuck_in_customs(package) -> bool:
    if package.status != "CUSTOMS":
        return False

    if getattr(package, "customs_warning_sent", False):
        return False

    if not package.last_checkpoint_time:
        return False

    if not package.last_checkpoint_time.tzinfo:
        now = datetime.now(timezone.utc)
        elapsed = now - package.last_checkpoint_time.replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
        elapsed = now - package.last_checkpoint_time

    return elapsed.days >= CUSTOMS_DELAY_DAYS
