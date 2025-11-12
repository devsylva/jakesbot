from django.core.management.base import BaseCommand
from django.conf import settings
from telegram import Bot
import asyncio

class Command(BaseCommand):
    help = 'Sets up Telegram webhook'

    def handle(self, *args, **kwargs):
        async def setup():
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            webhook_url = f"{settings.TELEGRAM_WEBHOOK_URL}/{settings.TELEGRAM_WEBHOOK_PATH}"
            SECRET = settings.WEBHOOK_SECRET_TOKEN  
            # Remove any existing webhook
            await bot.delete_webhook()
            
            # Set new webhook
            success = await bot.set_webhook(url=webhook_url, secret_token=SECRET)
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully set webhook to {webhook_url}')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to set webhook')
                )

        # Run the async function
        asyncio.run(setup())