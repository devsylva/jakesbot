# Timezone Refactor Summary

## Overview
Comprehensive timezone refactor to fix reminder timing issues across the Django Telegram bot. All timestamps are now stored in UTC and converted to Africa/Lagos only when displaying to users.

## Key Principles
1. **Store all datetimes in UTC**: Uniform storage format across all systems
2. **Convert to Africa/Lagos for display only**: User-facing output is localized
3. **Backend computes times**: AI agent passes intent strings, backend calculates UTC timestamps
4. **No timezone assumptions**: All times are explicitly timezone-aware

## Files Modified

### 1. [jarvis/agent.py](jarvis/agent.py)
- **Changed**: System prompt and real-time context building
- **Details**:
  - Removed pre-calculated timestamp logic from system prompt
  - Agent now passes intent strings ("in 2 hours", "at 3 PM") instead of ISO timestamps
  - Backend computes exact UTC using `timezone.now() + timedelta()`
  - Real-time context now uses `timezone.localtime(..., timezone.get_default_timezone())`

### 2. [jarvis/tools/reminder_tool.py](jarvis/tools/reminder_tool.py)
- **Added**: `format_display_time()` - converts UTC to Africa/Lagos display
- **Added**: `parse_reminder_time()` - intelligent time parser supporting:
  - ISO datetime strings (e.g., "2025-12-28T15:30:00Z")
  - Relative times (e.g., "in 2 hours", "in 30 minutes")
  - Absolute times (e.g., "at 3 PM", "at 15:30")
- **Changed**: All strftime() calls replaced with format_display_time()
- **Changed**: Timezone handling now always stores UTC in database

### 3. [jarvis/tools/calendar_tool.py](jarvis/tools/calendar_tool.py)
- **Changed**: Replaced `datetime.utcnow()` with `timezone.now()` in list_calendar_events()

### 4. [jarvis/tools/workout_diet_tool.py](jarvis/tools/workout_diet_tool.py)
- **Added**: Import `timezone` from `django.utils`
- **Changed**: All `datetime.datetime.now()` calls → `timezone.now()`
  - `get_today_workout()`
  - `get_today_diet()`
  - `update_today_workout()`
  - `update_today_diet()`
  - `_get_day_name()`

### 5. [jarvis/signals.py](jarvis/signals.py)
- **Added**: `format_reminder_display_time()` - localizes UTC to Africa/Lagos
- **Changed**: All reminder TTS text now uses localized display time

### 6. [jarvis/models.py](jarvis/models.py)
- **Changed**: `Reminder.__str__()` now converts UTC to Africa/Lagos for display

### 7. [jarvis/tasks.py](jarvis/tasks.py)
- **Added**: Transaction lock and idempotency checks in `send_reminder_task()`
- **Details**:
  - Uses `select_for_update()` to prevent duplicate calls
  - Atomic marking of `is_triggered` flag
  - Skips duplicate execution if already triggered

### 8. [telegram_bot/tasks.py](telegram_bot/tasks.py)
- **Changed**: Reminder display in `check_due_reminders()` uses localized time

### 9. [ai_assistant/settings.py](ai_assistant/settings.py)
- **Note**: `TIME_ZONE = 'Africa/Lagos'` and `USE_TZ = True` already configured

## Database Impact
All existing reminders in the database need verification:
- Run: `python manage.py shell` and check reminder times
- All stored times should be in UTC (indicated by `+00:00` offset)

## Testing Checklist
1. [ ] Set reminder "in 2 hours" → verify stored time is UTC
2. [ ] Set reminder "at 3 PM" → verify converted correctly to UTC
3. [ ] Check Telegram display → shows Africa/Lagos time
4. [ ] Multiple reminders → confirm no duplicate calls
5. [ ] Celery beat → runs reminders at correct UTC time
6. [ ] Agent doesn't calculate times → passes strings to backend

## API Changes for Frontend
If any frontend calls the reminder API directly:

**Old**: Provide ISO timestamp pre-calculated
**New**: Pass natural language strings like:
```json
{
  "title": "First meal",
  "time_iso": "in 2 hours"
}
```

Supported formats:
- `"in 2 hours"`, `"in 30 minutes"`, `"in 1 day"`
- `"at 3 PM"`, `"at 15:30"`, `"at 3:30 PM"`
- ISO format: `"2025-12-28T15:30:00Z"` (auto-converted to UTC)

## Troubleshooting

### Reminder fires at wrong time
Check: 
1. Server timezone: `python manage.py shell -c "from django.utils import timezone; print(timezone.now())"`
2. Celery worker timezone in logs
3. Celery beat schedule calculation

### Times show wrong timezone
- Verify `Africa/Lagos` is correct in settings.py
- Check `pytz.timezone('Africa/Lagos')` is loaded
- Review display helpers are being used

### Duplicate calls still happening
- Restart Celery workers
- Check database for orphaned `is_triggered=False` reminders with old timestamps
- Ensure transaction isolation level supports SELECT FOR UPDATE

## Deployment Steps
1. Backup database
2. Deploy code changes
3. Restart Django application
4. Restart Celery worker: `celery -A ai_assistant worker --loglevel=info`
5. Restart Celery beat: `celery -A ai_assistant beat --loglevel=info`
6. Test with new reminder
7. Monitor logs for timezone issues
