# jarvis/models.py
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

class AgentMemory(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="jarvis_memory")
    context = models.JSONField(default=dict, blank=True)  # structured long-term memory
    conversation_history = models.JSONField(default=list, blank=True)  # rolling short-term chat
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Memory({self.user.username})"

class Reminder(models.Model):
    chat_id = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_triggered = models.BooleanField(default=False)
    remind_before = models.IntegerField(default=10)

    def is_due(self):
        now = timezone.now()
        return (
            not self.is_triggered
            and self.time - timezone.timedelta(minutes=self.remind_before) <= now
        )

    def __str__(self):
        return f"{self.title} @ {self.time.strftime('%Y-%m-%d %H:%M')}"
