# telegram_bot/tasks.py
import os
import json
import logging
import asyncio
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from telegram import Bot
from telegram.ext import Application
from django.contrib.auth.models import User
from jarvis.agent import JarvisAgent  # your agent class
from jarvis.models import Reminder

logger = logging.getLogger(__name__)

BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN

# Create both sync and async bot instances
bot = Bot(BOT_TOKEN)

async def send_message_async(chat_id, text):
    """Helper function to send message asynchronously"""
    try:
        async with Bot(BOT_TOKEN) as async_bot:
            message = await async_bot.send_message(chat_id=chat_id, text=text)
            logger.info(f"✅ Message sent successfully to chat {chat_id}, message_id: {message.message_id}")
            return {"success": True, "message_id": message.message_id}
    except Exception as e:
        logger.error(f"❌ Failed to send message to chat {chat_id}: {e}")
        return {"success": False, "error": str(e)}

def send_message_sync(chat_id, text):
    """Helper function to send message synchronously"""
    try:
        logger.debug(f"Attempting to send message to chat {chat_id}: '{text[:50]}{'...' if len(text) > 50 else ''}'")
        result = asyncio.run(send_message_async(chat_id, text))
        
        if result["success"]:
            logger.debug(f"Message delivery confirmed for chat {chat_id}")
            return result
        else:
            logger.error(f"Message delivery failed for chat {chat_id}: {result['error']}")
            raise Exception(f"Failed to send message: {result['error']}")
            
    except Exception as e:
        logger.error(f"Error in send_message_sync for chat {chat_id}: {e}")
        raise

# Note: JarvisAgent requires user_id, so we'll create it per request

@shared_task(bind=True, name="process_telegram_update")
def process_telegram_update(self, update_payload):
    """Celery task that processes a Telegram update, calls the Agent, and sends replies."""
    logger.info("=== CELERY TASK STARTED ===")
    logger.info(f"Task ID: {self.request.id}")
    logger.debug(f"Starting to process Telegram update: {update_payload}")
    print(f"[CELERY TASK] Task {self.request.id} started processing update")
    try:
        # extract text and chat id (adjust to support callback_query, voice, etc)
        message = update_payload.get("message") or update_payload.get("edited_message")
        if not message:
            logger.info("No message in update, skipping")
            return {"ok": True, "note": "no message"}

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text") or message.get("caption") or ""

        user = message.get("from", {})
        user_id = user.get("id")
        
        logger.debug(f"Extracted from update - chat_id: {chat_id}, user_id: {user_id}, text: '{text}'")
        logger.info(f"Processing message from user {user_id} in chat {chat_id}")

        # Create JarvisAgent instance for this user
        logger.debug(f"Creating JarvisAgent for user {user_id}")
        user = User.objects.get(username="Jackson")
        agent = JarvisAgent(user=user)

        # Call the chat method
        logger.debug("Calling agent.chat() method")
        result = agent.chat(text)
        
        logger.debug(f"Agent returned result: {type(result)} - {result}")

        # Format and send reply(s)
        if result is None:
            logger.info("Agent returned None, sending 'Done.' message")
            msg_result = send_message_sync(chat_id, "Done.")
            logger.debug(f"'Done.' message result: {msg_result}")
        elif isinstance(result, str):
            logger.info(f"Sending string response to chat {chat_id}: '{result[:100]}{'...' if len(result) > 100 else ''}'")
            msg_result = send_message_sync(chat_id, result)
            logger.debug(f"String response result: {msg_result}")
        elif isinstance(result, list):
            # Handle tool outputs - send each result
            logger.info(f"Sending tool results to chat {chat_id}: {len(result)} items")
            for i, item in enumerate(result):
                if isinstance(item, str):
                    msg_result = send_message_sync(chat_id, item)
                else:
                    json_result = json.dumps(item, indent=2, default=str)
                    msg_result = send_message_sync(chat_id, json_result)
                logger.debug(f"Tool result {i+1} sent: {msg_result}")
        else:
            # structured results e.g., other types
            json_result = json.dumps(result, indent=2, default=str)
            logger.info(f"Sending structured response to chat {chat_id}: {type(result)}")
            logger.debug(f"Structured response content: {json_result[:200]}{'...' if len(json_result) > 200 else ''}")
            msg_result = send_message_sync(chat_id, json_result)
            logger.debug(f"Structured response result: {msg_result}")
            
        logger.info(f"Successfully processed update for user {user_id}")
        return {"ok": True, "processed": True}
        
    except Exception as e:
        logger.exception("Error processing Telegram update")
        logger.error(f"Error details: {str(e)}")
        # Optionally notify the user/admin of the error
        try:
            if 'chat_id' in locals():
                logger.debug(f"Attempting to send error message to chat {chat_id}")
                error_msg_result = send_message_sync(chat_id, "Sorry — error processing your request.")
                logger.debug(f"Error message result: {error_msg_result}")
            else:
                logger.warning("Could not send error message to user - chat_id not available")
        except Exception as send_error:
            logger.exception("Failed to send error message to user")
            logger.error(f"Send error details: {str(send_error)}")
        
        return {"ok": False, "error": str(e)}

# Optional synchronous fallback (imported by webhook fallback)
def process_telegram_update_sync(update_payload):
    """Synchronous fallback for processing Telegram updates when Celery is not available."""
    logger.info("Processing Telegram update synchronously (Celery fallback)")
    logger.debug(f"Sync processing update: {update_payload}")
    
    try:
        # Wrap the above logic but synchronous (no Celery)
        # We can call the same code but without Celery; re-use the same logic for consistency.
        # For simplicity, call the same task function directly (but it was decorated); so instead,
        # duplicate minimal logic or import a helper function.
        # Implement a minimal inline version:
        message = update_payload.get("message") or update_payload.get("edited_message")
        if not message:
            logger.info("No message in sync update, skipping")
            return
            
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text") or message.get("caption") or ""
        user = message.get("from", {})
        user_id = user.get("id")
        
        logger.debug(f"Sync extracted - chat_id: {chat_id}, user_id: {user_id}, text: '{text}'")
        logger.info(f"Sync processing message from user {user_id} in chat {chat_id}")
        
        # Create JarvisAgent instance for this user
        logger.debug(f"Sync: Creating JarvisAgent for user {user_id}")
        user = User.objects.get(username="Jackson")
        agent = JarvisAgent(user=user)
        
        # Call the chat method
        logger.debug("Sync: Calling agent.chat() method")
        result = agent.chat(text)
            
        logger.debug(f"Sync Agent returned: {type(result)} - {result}")
        
        if result is None:
            logger.info("Sync: Agent returned None, sending 'Done.' message")
            msg_result = send_message_sync(chat_id, "Done.")
            logger.debug(f"Sync: 'Done.' message result: {msg_result}")
        elif isinstance(result, str):
            logger.info(f"Sync: Sending string response: '{result[:100]}{'...' if len(result) > 100 else ''}'")
            msg_result = send_message_sync(chat_id, result)
            logger.debug(f"Sync: String response result: {msg_result}")
        elif isinstance(result, list):
            # Handle tool outputs - send each result
            logger.info(f"Sync: Sending tool results: {len(result)} items")
            for i, item in enumerate(result):
                if isinstance(item, str):
                    msg_result = send_message_sync(chat_id, item)
                else:
                    json_result = json.dumps(item, indent=2, default=str)
                    msg_result = send_message_sync(chat_id, json_result)
                logger.debug(f"Sync: Tool result {i+1} sent: {msg_result}")
        else:
            json_result = json.dumps(result, indent=2, default=str)
            logger.info(f"Sync: Sending structured response: {type(result)}")
            logger.debug(f"Sync: Structured content: {json_result[:200]}{'...' if len(json_result) > 200 else ''}")
            msg_result = send_message_sync(chat_id, json_result)
            logger.debug(f"Sync: Structured response result: {msg_result}")
            
        logger.info(f"Sync processing completed successfully for user {user_id}")
        
    except Exception as e:
        logger.exception("Error in synchronous Telegram update processing")
        logger.error(f"Sync error details: {str(e)}")
        try:
            if 'chat_id' in locals():
                logger.debug(f"Sync: Attempting to send error message to chat {chat_id}")
                error_msg_result = send_message_sync(chat_id, "Sorry — error processing your request.")
                logger.debug(f"Sync: Error message result: {error_msg_result}")
            else:
                logger.warning("Sync: Could not send error message - chat_id not available")
        except Exception as send_error:
            logger.exception("Sync: Failed to send error message to user")
            logger.error(f"Sync send error details: {str(send_error)}")




@shared_task
def check_due_reminders():
    now = timezone.now()
    reminders = Reminder.objects.filter(is_triggered=False, time__lte=now + timezone.timedelta(minutes=1))

    for reminder in reminders:
        try:
            message = f"⏰ Reminder: {reminder.title}\nScheduled for {reminder.time.strftime('%H:%M')}."
            send_message_sync(reminder.chat_id, message)
            reminder.is_triggered = True
            reminder.save()
        except Exception as e:
            print(f"Failed to send reminder: {e}")