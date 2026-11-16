import logging
from pyrogram import Client
from pyrogram.enums import ParseMode
from info import SESSION, API_ID, API_HASH, BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

class PaymentBot(Client):
    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=15,
            plugins={"root": "plugins"},  # auto-loads all plugins/*.py handlers
            sleep_threshold=60,
            # Rich look: every message is HTML (<b>, <blockquote>, ...) so the
            # bot's texts render bold with quote blocks. All message strings
            # in the repo are HTML now; user input is escaped via utils.esc.
            parse_mode=ParseMode.HTML,
        )

    async def start(self):
        await super().start()
        logging.info("✅ PaymentBot client started")

    async def stop(self):
        await super().stop()
        logging.info("✅ PaymentBot client stopped")


PayBot = PaymentBot()
