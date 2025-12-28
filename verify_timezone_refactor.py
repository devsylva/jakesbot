#!/usr/bin/env python
"""
Timezone Refactor Verification Script
Run this after deployment to verify all timezone handling is correct.
"""
import os
import django
import sys
import pytz

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_assistant.settings')
django.setup()

from django.utils import timezone
from jarvis.models import Reminder
from jarvis.tools.reminder_tool import parse_reminder_time, format_display_time
import datetime

def test_timezone_setup():
    """Verify Django timezone settings."""
    print("=" * 60)
    print("1. TIMEZONE SETUP VERIFICATION")
    print("=" * 60)
    
    print(f"USE_TZ setting: {django.conf.settings.USE_TZ}")
    print(f"TIME_ZONE setting: {django.conf.settings.TIME_ZONE}")
    print(f"Current UTC time: {timezone.now()}")
    local_tz = pytz.timezone('Africa/Lagos')
    print(f"Current local time (Africa/Lagos): {timezone.localtime(timezone.now(), local_tz)}")
    print()

def test_time_parser():
    """Test the parse_reminder_time function."""
    print("=" * 60)
    print("2. TIME PARSER TESTS")
    print("=" * 60)
    
    test_cases = [
        "in 2 hours",
        "in 30 minutes",
        "at 3 PM",
        "at 15:30",
        "2025-12-28T15:30:00Z",
    ]
    
    for test in test_cases:
        try:
            parsed = parse_reminder_time(test)
            local_tz = pytz.timezone('Africa/Lagos')
            local = timezone.localtime(parsed, local_tz)
            print(f"✓ '{test}' → UTC: {parsed} | Local: {local.strftime('%H:%M %Z')}")
        except Exception as e:
            print(f"✗ '{test}' → ERROR: {e}")
    print()

def test_database_reminders():
    """Check existing reminders in database."""
    print("=" * 60)
    print("3. DATABASE REMINDER CHECK")
    print("=" * 60)
    
    reminders = Reminder.objects.all()[:5]
    if not reminders:
        print("No reminders in database yet.")
    else:
        for reminder in reminders:
            display = format_display_time(reminder.time)
            print(f"ID {reminder.id}: {reminder.title}")
            print(f"  Stored (UTC): {reminder.time}")
            print(f"  Display (Lagos): {display}")
            print(f"  Triggered: {reminder.is_triggered}")
    print()

def test_reminder_creation():
    """Test creating a reminder with the new parser."""
    print("=" * 60)
    print("4. REMINDER CREATION TEST")
    print("=" * 60)
    
    # Create a test reminder
    try:
        test_time = parse_reminder_time("in 1 hour")
        reminder = Reminder(
            chat_id="test_user",
            title="Test Reminder - In 1 Hour",
            time=test_time,
            remind_before=10,
        )
        reminder.save()
        
        display = format_display_time(reminder.time)
        print(f"✓ Created reminder ID {reminder.id}")
        print(f"  Title: {reminder.title}")
        print(f"  UTC Time: {reminder.time}")
        print(f"  Display (Lagos): {display}")
        
        # Cleanup
        reminder.delete()
        print(f"✓ Test reminder cleaned up")
    except Exception as e:
        print(f"✗ Error creating reminder: {e}")
    print()

def test_celery_context():
    """Verify Celery will see correct times."""
    print("=" * 60)
    print("5. CELERY WORKER CONTEXT")
    print("=" * 60)
    
    now = timezone.now()
    test_eta = now + datetime.timedelta(hours=2)
    
    print(f"Current UTC time for Celery: {now}")
    print(f"ETA for +2h task: {test_eta}")
    print(f"Time difference: {(test_eta - now).total_seconds() / 3600:.1f} hours")
    print()

def main():
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + "  TIMEZONE REFACTOR VERIFICATION".center(58) + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    try:
        test_timezone_setup()
        test_time_parser()
        test_database_reminders()
        test_reminder_creation()
        test_celery_context()
        
        print("=" * 60)
        print("✓ ALL TESTS COMPLETED")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Verify all test outputs show UTC storage and Lagos display")
        print("2. Restart Celery workers: celery -A ai_assistant worker")
        print("3. Test setting reminders from Telegram bot")
        print("4. Monitor logs for any timezone-related errors")
        print()
        
    except Exception as e:
        print(f"\n✗ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
