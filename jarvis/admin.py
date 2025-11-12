from django.contrib import admin
from .models import AgentMemory, Reminder

# Register your models here.
admin.site.register(AgentMemory)
admin.site.register(Reminder)
