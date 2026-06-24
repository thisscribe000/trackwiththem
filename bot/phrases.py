from core.track17_client import PackageStatus

STATUS_TRANSITION_TEMPLATES: dict[str, list[str]] = {
    "PENDING": [
        "📋 Your package is registered and waiting to be picked up. "
        "The journey hasn't started yet, but we're watching!",
        "📋 Just got word of your shipment. The carrier should pick it up soon — "
        "I'll let you know the moment it moves.",
    ],
    "IN_TRANSIT": [
        "🚚 Your package is on the move! It's making its way through the network.",
        "🚚 Good news — your package is in transit and heading your way.",
        "🚚 Rolling along! Your package has left one stop and is on to the next. "
        "Every mile gets it closer.",
    ],
    "CUSTOMS": [
        "🛃 Your package has reached customs clearance. "
        "This is usually quick, but sometimes takes a few days.",
        "🛃 Customs checkpoint reached. Hang tight while they process the shipment.",
        "🛃 Sitting with customs at the moment. "
        "Most shipments clear in a day or two — I'll update you as soon as it moves.",
    ],
    "OUT_FOR_DELIVERY": [
        "📬 Your package is out for delivery today! Keep an eye out.",
        "📬 Great news — it's on the delivery truck and headed your way!",
        "📬 Driver's got it! Your package is on the last leg of the journey. "
        "Today's the day.",
    ],
    "DELIVERED": [
        "✅ Package delivered! Hope it was worth the wait. 🎉",
        "✅ Delivered! Enjoy your package. 🎉",
        "✅ It's here! Your package has arrived safe and sound. 🎉",
    ],
    "EXCEPTION": [
        "⚠️ There's an issue with your delivery. "
        "Check with the carrier for details.",
        "⚠️ Something went wrong along the way. "
        "The carrier should be able to help sort it out.",
        "⚠️ Hit a snag in transit. "
        "This doesn't always mean a big delay, but you might want to check with the carrier.",
    ],
}

DELIVERED_FINAL = (
    "✅ **Delivered!** 🎉\n\n"
    "This package has reached its destination. "
    "I'll stop watching it now to save API calls.\n\n"
    "Send me another tracking number anytime!"
)

CUSTOMS_DELAY_WARNING = (
    "⏳ Your package has been in customs for a while.\n\n"
    "Customs clearance can sometimes take longer than expected — "
    "this isn't unusual. If it's been more than a week, "
    "you might want to contact the carrier directly for an update."
)

STICKERS = {
    "OUT_FOR_DELIVERY": "CAACAgIAAxkBA0APDGo7HyarjiUabR3vSzThUHWUFFhTAAIjDAACKlUYAtr2SxOW0WIjPAQ",
    "DELIVERED": "CAACAgIAAxkBA0APDGo7HyarjiUabR3vSzThUHWUFFhTAAIjDAACKlUYAtr2SxOW0WIjPAQ",
}


DASHBOARD_EMPTY = (
    "You're not tracking any packages yet.\n\n"
    "Just send me a tracking number and I'll start watching it for you!"
)

DASHBOARD_HEADER = "**📦 Your tracked packages**"

RENAME_PROMPT = (
    "Send me a new nickname for this package.\n"
    "Just type and send — it can be anything like \"Mum's birthday gift\" or \"Laptop\"."
)

RENAME_CONFIRMED = 'Renamed to **"{nickname}"** ✅'

STOP_CONFIRM_PROMPT = (
    "Are you sure you want to stop tracking this package?\n"
    "I'll no longer check for updates on it."
)

STOP_CONFIRMED = (
    "Stopped tracking that package. "
    "Send me the tracking number again if you ever want to resume."
)

STOP_CANCELLED = "Alright, I'll keep watching it! 👀"

HISTORY_HEADER = "📜 **Full history for** `{tracking_number}` — **{carrier_name}**"

HISTORY_EMPTY = "No checkpoint history yet."


def progress_bar(status: PackageStatus) -> str:
    filled = "🟢"
    empty = "⚪"
    error = "🔴"
    unknown = "❓"
    stages = 5

    mapping = {
        PackageStatus.PENDING: 1,
        PackageStatus.IN_TRANSIT: 2,
        PackageStatus.CUSTOMS: 3,
        PackageStatus.OUT_FOR_DELIVERY: 4,
        PackageStatus.DELIVERED: 5,
    }

    if status == PackageStatus.EXCEPTION:
        return error * stages

    if status == PackageStatus.UNKNOWN:
        return unknown * stages

    count = mapping.get(status, 0)
    return filled * count + empty * (stages - count)
