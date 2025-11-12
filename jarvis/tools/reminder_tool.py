import logging
from typing import Any, Dict
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from jarvis.models import Reminder
from jarvis.tasks import send_reminder_task
from datetime import timedelta

logger = logging.getLogger(__name__)

class ReminderTool:
    def __init__(self, user_id: int):
        self.chat_id = user_id

    @staticmethod
    def json_schema_create_reminder() -> Dict[str, Any]:
        return {
            "name": "create_reminder",
            "description": "Create a reminder in the local system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "time_iso": {"type": "string"},
                    "remind_before": {"type": "integer", "default": 10},
                },
                "required": ["title", "time_iso"],
            },
        }

    @staticmethod
    def json_schema_list_reminders() -> Dict[str, Any]:
        return {
            "name": "list_reminders",
            "description": "List active reminders for the user.",
            "parameters": {"type": "object", "properties": {}},
        }

    @staticmethod
    def json_schema_update_reminder() -> Dict[str, Any]:
        return {
            "name": "update_reminder",
            "description": "Update a reminder’s title or time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "new_title": {"type": "string"},
                    "new_time_iso": {"type": "string"},
                },
                "required": ["id"],
            },
        }

    def create_reminder(self, title: str, time_iso: str, remind_before: int = 10) -> str:
        logger.info(f"AI Agent called create_reminder for user {self.chat_id}: title='{title}', time='{time_iso}', remind_before={remind_before}")
        logger.info(f"Current timezone: {timezone.get_current_timezone()}")
        logger.info(f"Current time: {timezone.now()}")
        
        time = parse_datetime(time_iso)
        logger.info(f"Parsed datetime: {time} (naive: {timezone.is_naive(time)})")
        
        # Handle timezone conversion properly
        if timezone.is_naive(time):
            # If the time is naive, assume it's in the Django default timezone
            time = timezone.make_aware(time, timezone.get_default_timezone())
        
        logger.info(f"Final datetime for storage: {time} (timezone: {time.tzinfo})")

        reminder = Reminder.objects.create(
            chat_id=self.chat_id,
            title=title,
            time=time,
            remind_before=remind_before,
        )
        logger.info(f"Successfully created reminder for user {self.chat_id}: reminder_id={reminder.id}")

        # Schedule 10 minutes before
        send_reminder_task.apply_async((reminder.id, True), eta=time - timedelta(minutes=remind_before))
        
        # Schedule at the exact time
        send_reminder_task.apply_async((reminder.id, False), eta=time)

        return f"⏰ Reminder '{title}' has been set for {time.strftime('%Y-%m-%d at %H:%M')} (ID: {reminder.id})"

    def list_reminders(self) -> str:
        logger.info(f"AI Agent called list_reminders for user {self.chat_id}")
        reminders = Reminder.objects.filter(
            chat_id=self.chat_id,
            is_triggered=False,
            time__gte=timezone.now()
        )
        logger.info(f"Retrieved {len(reminders)} active reminders for user {self.chat_id}")
        
        if not reminders:
            logger.info(f"No active reminders found for user {self.chat_id}")
            return "⏰ You have no active reminders."
        
        response_lines = ["⏰ Here are your active reminders:"]
        for reminder in reminders:
            time_str = reminder.time.strftime('%Y-%m-%d at %H:%M')
            response_lines.append(f"• {reminder.title} — {time_str} (ID: {reminder.id})")
        
        logger.info(f"Successfully listed {len(reminders)} reminders for user {self.chat_id}")
        return "\n".join(response_lines)

    def update_reminder(self, id: int, new_title: str = None, new_time_iso: str = None) -> str:
        logger.info(f"AI Agent called update_reminder for user {self.chat_id}: id={id}, new_title='{new_title}', new_time='{new_time_iso}'")
        try:
            reminder = Reminder.objects.get(id=id, chat_id=self.chat_id)
        except Reminder.DoesNotExist:
            logger.warning(f"Reminder with id {id} not found for user {self.chat_id}")
            return f"⚠️ Sorry, I couldn't find a reminder with ID {id}."

        old_title = reminder.title
        old_time = reminder.time.strftime('%Y-%m-%d at %H:%M')

        if new_title:
            reminder.title = new_title
        if new_time_iso:
            time = parse_datetime(new_time_iso)
            if timezone.is_naive(time):
                # If the time is naive, assume it's in the Django default timezone
                time = timezone.make_aware(time, timezone.get_default_timezone())
            reminder.time = time

        reminder.save()
        logger.info(f"Successfully updated reminder {id} for user {self.chat_id}: '{old_title}' -> '{reminder.title}'")
        
        if new_title and new_time_iso:
            new_time = reminder.time.strftime('%Y-%m-%d at %H:%M')
            return f"📝 Reminder '{old_title}' has been updated to '{reminder.title}' and rescheduled from {old_time} to {new_time}"
        elif new_title:
            return f"📝 Reminder '{old_title}' has been renamed to '{reminder.title}'"
        elif new_time_iso:
            new_time = reminder.time.strftime('%Y-%m-%d at %H:%M')
            return f"📝 Reminder '{reminder.title}' has been rescheduled from {old_time} to {new_time}"
        else:
            return f"📝 Reminder '{reminder.title}' updated successfully"
