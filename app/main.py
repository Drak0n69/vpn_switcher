from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.telegram import TelegramBot


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    bot = TelegramBot(settings)

    async def runner() -> None:
        try:
            await bot.run()
        finally:
            await bot.close()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
