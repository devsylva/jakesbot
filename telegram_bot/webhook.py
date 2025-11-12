# telegram_bot/webhook.py
import os
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from telegram import Bot

logger = logging.getLogger(__name__)

BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
SECRET_TOKEN = settings.WEBHOOK_SECRET_TOKEN  # must match the secret you set in set_webhook
ADMIN_ID = settings.TELEGRAM_ADMIN_ID

bot = Bot(BOT_TOKEN)

@csrf_exempt
def telegram_webhook(request):
    """
    Receives Telegram updates from Telegram webhook.
    - Verifies X-Telegram-Bot-Api-Secret-Token header (if SECRET_TOKEN set)
    - Returns 200 quickly after enqueuing the update for background processing
    """
    logger.debug(f"Webhook called with method: {request.method}")
    logger.debug(f"Request headers: {dict(request.headers)}")
    
    if request.method != "POST":
        logger.debug("Non-POST request rejected")
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    # Verify Telegram secret header (set when you call set_webhook)
    logger.debug(f"SECRET_TOKEN configured: {bool(SECRET_TOKEN)}")
    if SECRET_TOKEN:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        logger.debug(f"Secret header present: {bool(header)}")
        logger.debug(f"Secret header matches: {header == SECRET_TOKEN}")
        if header != SECRET_TOKEN:
            logger.warning("Invalid Telegram secret token on webhook")
            logger.debug("Secret token validation failed")
            return JsonResponse({"ok": False, "error": "invalid token"}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        print("Received Telegram update:", payload)
        logger.debug(f"Update type: {list(payload.keys())}")
    except Exception as e:
        logger.exception("Invalid JSON on webhook")
        logger.debug(f"JSON parsing failed: {e}")
        logger.debug(f"Raw request body: {request.body}")
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    # Basic extraction: message / edited_message / callback_query / etc. Adjust as needed.
    update = payload

    # Optional: restrict usage to your Telegram user id
    # (we only check sender id if there's a message payload)
    logger.debug(f"ADMIN_ID configured: {ADMIN_ID}")
    from_user = None
    if "message" in update and update["message"].get("from"):
        from_user = update["message"]["from"]
        logger.debug(f"Found user in message: {from_user}")
    elif "edited_message" in update and update["edited_message"].get("from"):
        from_user = update["edited_message"]["from"]
        logger.debug(f"Found user in edited_message: {from_user}")
    else:
        logger.debug("No user found in update")

    if ADMIN_ID and from_user:
        logger.debug(f"Checking authorization for user: {from_user}")
        try:
            user_id = int(from_user.get("id"))
            logger.debug(f"User ID: {user_id}, Admin ID: {ADMIN_ID}")
        except Exception as e:
            user_id = None
            logger.debug(f"Failed to parse user ID: {e}")
        if user_id and user_id != ADMIN_ID:
            # optionally notify sender and drop
            chat_id = update.get("message", {}).get("chat", {}).get("id")
            logger.debug(f"Unauthorized user {user_id}, chat_id: {chat_id}")
            if chat_id:
                logger.debug("Sending unauthorized message to user")
                bot.send_message(chat_id=chat_id, text="Unauthorized.")
            logger.warning(f"Unauthorized telegram user {user_id} attempted to use the bot.")
            return JsonResponse({"ok": False, "error": "unauthorized"}, status=403)
        else:
            logger.debug("User authorization passed")
    else:
        logger.debug("Skipping authorization check (no ADMIN_ID or no user found)")

    # Enqueue for processing by background worker (Celery recommended)
    logger.debug("Attempting to enqueue update for processing")
    try:
        # Import inside function to avoid heavy import at module load time if Celery not configured
        from telegram_bot.tasks import process_telegram_update  # celery task
        logger.debug("Celery task imported successfully")
        result = process_telegram_update.delay(update)
        logger.debug(f"Update enqueued to Celery with task ID: {result.id}")
    except Exception as e:
        # If Celery is not available, fall back to a synchronous process function
        logger.exception("Failed to enqueue update to Celery, processing synchronously as fallback")
        logger.debug(f"Celery failed: {e}, trying synchronous fallback")
        try:
            from telegram_bot.tasks import process_telegram_update_sync
            logger.debug("Synchronous task imported successfully")
            process_telegram_update_sync(update)
            logger.debug("Synchronous processing completed")
        except Exception as sync_e:
            logger.exception("Synchronous fallback also failed")
            logger.debug(f"Synchronous fallback failed: {sync_e}")

    # Acknowledge quickly
    logger.debug("Returning success response")
    return JsonResponse({"ok": True})
