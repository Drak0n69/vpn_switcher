import logging

from app.bot import VpnDeliveryBot
from app.config import Settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    settings.recipients_file.parent.mkdir(parents=True, exist_ok=True)
    application = VpnDeliveryBot(settings).build_application()
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
