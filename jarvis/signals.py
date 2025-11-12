from django.db.models.signals import post_save
from django.dispatch import receiver
from jarvis.models import Reminder
from jarvis.tasks import generate_reminder_tts

@receiver(post_save, sender=Reminder)
def reminder_post_save(sender, instance, created, **kwargs):
    if created:
        # Handle the creation of a new reminder
        # Generate TTS in background for instant response
        reminder_text = f"{instance.title} at {instance.time.strftime('%B %d, %Y at %I:%M %p')}"
        user_name = "User"  # You can customize this based on your user model
        
        # Queue the TTS generation as a background task
        generate_reminder_tts.delay(instance.id, reminder_text, user_name)
        print(f"🚀 TTS generation queued for reminder {instance.id}")
        
    else:
        # Handle the update of an existing reminder
        # Regenerate TTS if the title or time changed
        if hasattr(instance, 'title'):  # Remove tracker dependency for now
            reminder_text = f"{instance.title} at {instance.time.strftime('%B %d, %Y at %I:%M %p')}"
            user_name = "User"
            
            # Queue the TTS regeneration as a background task
            generate_reminder_tts.delay(instance.id, reminder_text, user_name)
            print(f"🔄 TTS regeneration queued for reminder {instance.id}")