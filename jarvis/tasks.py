import os
from celery import shared_task
from django.conf import settings
from jarvis.utils.gpt_tts_generator import generate_voice_reminder
from jarvis.utils.twilio_calling import send_call_reminder
from django.db import transaction

@shared_task(bind=True, max_retries=3)
def generate_reminder_tts(self, reminder_id, reminder_text, user_name="User"):
    """
    Generate TTS audio for a reminder in the background.
    
    Args:
        reminder_id (int): The ID of the reminder
        reminder_text (str): The formatted reminder text
        user_name (str): User's name for personalization
    """
    try:
        # Create static/audio directory if it doesn't exist
        audio_dir = os.path.join(settings.BASE_DIR, 'static', 'audio')
        os.makedirs(audio_dir, exist_ok=True)
        
        # Generate the audio
        audio_bytes = generate_voice_reminder(reminder_text, user_name)
        
        # Save the audio file
        audio_filename = f"{reminder_id}.wav"
        audio_path = os.path.join(audio_dir, audio_filename)
        
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
            
        print(f"✅ Background TTS generated: {audio_path}")
        return {"status": "success", "file_path": audio_path}
        
    except Exception as e:
        print(f"❌ Background TTS failed for reminder {reminder_id}: {e}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries
            raise self.retry(countdown=countdown, exc=e)
        
        return {"status": "failed", "error": str(e)}



@shared_task(bind=True, max_retries=3)
def send_reminder_task(self, reminder_id, before=False):
    """
    Send reminder via call and cleanup audio file after final reminder.
    
    Args:
        reminder_id (int): The ID of the reminder
        before (bool): True if this is the "before" reminder, False if final reminder
    """
    try:
        from jarvis.models import Reminder
        
        # Lock the reminder row to avoid duplicate triggers when Celery retries or tasks overlap
        with transaction.atomic():
            reminder = Reminder.objects.select_for_update().get(pk=reminder_id)

            # Skip if already handled (idempotency guard)
            if reminder.is_triggered:
                print(f"ℹ️ Reminder {reminder_id} already triggered; skipping duplicate call (before={before}).")
                return {"status": "skipped", "reason": "already triggered", "before": before, "cleanup": False}

        # Send the call reminder (outside the lock to keep DB lock short)
        result = send_call_reminder(reminder.id)
        print(f"📞 Call result: {result}")

        # If this is the final reminder (not the "before" reminder), mark triggered & cleanup
        if not before:
            # Mark as triggered atomically; if another worker raced, skip cleanup
            updated = Reminder.objects.filter(pk=reminder_id, is_triggered=False).update(is_triggered=True)
            if updated == 0:
                print(f"ℹ️ Reminder {reminder_id} was already marked triggered after call; skipping cleanup to avoid duplicates.")
                return {"status": "skipped", "reason": "already triggered post-call", "before": before, "cleanup": False}

            # Delete the audio file
            audio_dir = os.path.join(settings.BASE_DIR, 'static', 'audio')
            audio_filename = f"{reminder_id}.wav"
            audio_path = os.path.join(audio_dir, audio_filename)
            
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    print(f"🗑️ Deleted audio file: {audio_path}")
                except Exception as e:
                    print(f"⚠️ Failed to delete audio file {audio_path}: {e}")
            else:
                print(f"⚠️ Audio file not found: {audio_path}")
                
        return {"status": "success", "before": before, "cleanup": not before}
        
    except Exception as e:
        print(f"❌ Send reminder task failed for reminder {reminder_id}: {e}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries
            raise self.retry(countdown=countdown, exc=e)
        
        return {"status": "failed", "error": str(e)}
