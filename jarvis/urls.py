from django.urls import path
from .views import voice_message

urlpatterns = [
    path('voice/<str:audio_id>/', voice_message, name='voice_message'),
]