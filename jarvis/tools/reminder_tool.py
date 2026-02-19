import logging
import re
import datetime
import pytz
from typing import Any, Dict
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from jarvis.models import Reminder
from jarvis.tasks import send_reminder_task
from datetime import timedelta

logger = logging.getLogger(__name__)

def format_display_time(dt) -> str:
    """Convert UTC datetime to local display time (Africa/Lagos)."""
    if dt is None:
        return "Unknown"
    local_tz = pytz.timezone('Africa/Lagos')
    local_dt = timezone.localtime(dt, local_tz)
    return local_dt.strftime('%Y-%m-%d at %H:%M %Z')

def parse_reminder_time(time_input: str):
    """
    Parse reminder time from various formats:
    - ISO datetime string (e.g., "2025-12-28T15:30:00Z" or "2025-12-28T15:30:00+01:00")
    - Relative time string (e.g., "in 2 hours", "in 30 minutes")
    - Local time string (e.g., "at 3 PM", "at 15:30")
    
    Returns: UTC-aware datetime object or raises ValueError.
    """
    time_input = time_input.strip()
    
    # Try parsing as ISO datetime first
    dt = parse_datetime(time_input)
    if dt is not None:
        # Convert to UTC if already aware, otherwise assume UTC
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_default_timezone())
        return dt.astimezone(pytz.utc)
    
    # Try relative time pattern: "in X hours/minutes/days"
    match = re.match(r'^in\s+(\d+)\s+(hours?|minutes?|days?)', time_input, re.IGNORECASE)
    if match:
        value = int(match.group(1))
        unit = match.group(2).lower()
        
        now = timezone.now()
        if unit.startswith('hour'):
            return now + timedelta(hours=value)
        elif unit.startswith('minute'):
            return now + timedelta(minutes=value)
        elif unit.startswith('day'):
            return now + timedelta(days=value)
    
    # Try absolute time pattern: "at HH:MM" or "at H:MM AM/PM"
    match = re.match(r'^at\s+(\d{1,2}):(\d{2})(?:\s*(am|pm|AM|PM))?', time_input)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        period = match.group(3)
        
        # Adjust hour for AM/PM
        if period and period.upper() == 'PM' and hour != 12:
            hour += 12
        elif period and period.upper() == 'AM' and hour == 12:
            hour = 0
        
        # Create a datetime for today (Africa/Lagos timezone) and convert to UTC
        local_tz = pytz.timezone('Africa/Lagos')
        now_local = timezone.localtime(timezone.now(), local_tz)
        local_dt = local_tz.localize(
            datetime.datetime(now_local.year, now_local.month, now_local.day, hour, minute, 0)
        )
        utc_dt = local_dt.astimezone(pytz.utc)
        
        # If the time is in the past, use tomorrow
        if utc_dt <= timezone.now():
            utc_dt += timedelta(days=1)
        
        return utc_dt
    
    raise ValueError(f"Could not parse time: {time_input}. Use formats like 'in 2 hours', 'at 3 PM', or ISO timestamp.")

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

    def create_reminder(self, title: str, time_iso: str, remind_before: int = 0) -> str:
        logger.info(f"AI Agent called create_reminder for user {self.chat_id}: title='{title}', time='{time_iso}', remind_before_removed=true")
        logger.info(f"Current UTC time: {timezone.now()}")
        
        # Parse the time string (handles ISO, relative, and absolute formats)
        try:
            time = parse_reminder_time(time_iso)
        except ValueError as e:
            logger.error(f"Failed to parse reminder time: {e}")
            return f"⚠️ {str(e)}"
        
        logger.info(f"Parsed time to UTC datetime: {time}")

        reminder = Reminder.objects.create(
            chat_id=self.chat_id,
            title=title,
            time=time,
            remind_before=0,
        )
        logger.info(f"Successfully created reminder for user {self.chat_id}: reminder_id={reminder.id}")
        
        # Always schedule the final reminder at the exact time
        if time > timezone.now():
            send_reminder_task.apply_async((reminder.id, False), eta=time)
        else:
            # If the time is already past, fire immediately to avoid double scheduling at the same moment
            send_reminder_task.delay(reminder.id, False)

        display_time = format_display_time(time)
        return f"⏰ Reminder '{title}' has been set for {display_time} (ID: {reminder.id})"

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
            time_str = format_display_time(reminder.time)
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
        old_time = format_display_time(reminder.time)

        if new_title:
            reminder.title = new_title
        if new_time_iso:
            try:
                time = parse_reminder_time(new_time_iso)
            except ValueError as e:
                logger.error(f"Failed to parse updated reminder time: {e}")
                return f"⚠️ {str(e)}"
            reminder.time = time

        reminder.save()
        logger.info(f"Successfully updated reminder {id} for user {self.chat_id}: '{old_title}' -> '{reminder.title}'")
        
        if new_title and new_time_iso:
            new_time = format_display_time(reminder.time)
            return f"📝 Reminder '{old_title}' has been updated to '{reminder.title}' and rescheduled from {old_time} to {new_time}"
        elif new_title:
            return f"📝 Reminder '{old_title}' has been renamed to '{reminder.title}'"
        elif new_time_iso:
            new_time = format_display_time(reminder.time)
            return f"📝 Reminder '{reminder.title}' has been rescheduled from {old_time} to {new_time}"
        else:
            return f"📝 Reminder '{reminder.title}' updated successfully"
