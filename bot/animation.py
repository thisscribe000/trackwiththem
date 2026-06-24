import asyncio
import logging

from telegram import Message

logger = logging.getLogger(__name__)


async def animated_reply(
    message: Message,
    steps: list[str],
    delay_seconds: float = 1.0,
) -> Message:
    msg = await message.reply_text(steps[0], parse_mode="Markdown")

    for step in steps[1:]:
        await asyncio.sleep(delay_seconds)
        try:
            msg = await msg.edit_text(step, parse_mode="Markdown")
        except Exception:
            logger.warning(
                "Failed to edit animated message, sending new one",
                exc_info=True,
            )
            msg = await message.reply_text(step, parse_mode="Markdown")

    return msg
