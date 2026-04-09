import logging
from pyrogram import Client
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
        )

    async def start(self):
        await super().start()
        logging.info("✅ PaymentBot client started")

    async def stop(self):
        await super().stop()
        logging.info("✅ PaymentBot client stopped")


PayBot = PaymentBot()
