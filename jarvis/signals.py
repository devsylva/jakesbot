from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import pytz
from jarvis.models import Reminder
from jarvis.tasks import generate_reminder_tts

def format_reminder_display_time(dt) -> str:
    """Convert UTC datetime to local display time for reminders."""
    if dt is None:
        return "Unknown"
    local_tz = pytz.timezone('Africa/Lagos')
    local_dt = timezone.localtime(dt, local_tz)
    return local_dt.strftime('%B %d, %Y at %I:%M %p')

@receiver(post_save, sender=Reminder)
def reminder_post_save(sender, instance, created, **kwargs):
    # Prevent duplicate queueing within the same process (Django sometimes triggers multiple imports)
    if getattr(instance, "_tts_enqueued", False):
        return

    if created:
        # Handle the creation of a new reminder
        # Generate TTS in background for instant response
        reminder_text = f"{instance.title} at {format_reminder_display_time(instance.time)}"
        user_name = "User"  # You can customize this based on your user model
        
        # Queue the TTS generation as a background task
        generate_reminder_tts.delay(instance.id, reminder_text, user_name)
        instance._tts_enqueued = True
        print(f"🚀 TTS generation queued for reminder {instance.id}")
        
    else:
        # Handle the update of an existing reminder
        # Regenerate TTS if the title or time changed
        if hasattr(instance, 'title'):  # Remove tracker dependency for now
            reminder_text = f"{instance.title} at {format_reminder_display_time(instance.time)}"
            user_name = "User"
            
            # Queue the TTS regeneration as a background task
            generate_reminder_tts.delay(instance.id, reminder_text, user_name)
            instance._tts_enqueued = True
            print(f"🔄 TTS regeneration queued for reminder {instance.id}")