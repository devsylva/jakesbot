# ai_assistant/celery.py
import os
from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_assistant.settings')

app = Celery('ai_assistant')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Configure periodic tasks
app.conf.beat_schedule = {
    'check-due-reminders-every-minute': {
        'task': 'telegram_bot.tasks.check_due_reminders',
        'schedule': 60.0,
    },
}

@setup_logging.connect
def config_loggers(*args, **kwargs):
    """Configure Django logging for Celery workers"""
    from django.conf import settings
    import logging.config
    
    if hasattr(settings, 'LOGGING'):
        logging.config.dictConfig(settings.LOGGING)
