from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

# Create your views here.
@csrf_exempt
@require_http_methods(["GET", "POST"])
def voice_message(request, audio_id):
    """
    Twilio will hit this URL when the call connects.
    It returns TwiML instructing Twilio to play your audio file.
    """
    audio_url = f"{settings.TELEGRAM_WEBHOOK_URL}/static/audio/{audio_id}.wav"  # use your actual domain or ngrok URL
    twiml = f"""
    <Response>
        <Play>{audio_url}</Play>
    </Response>
    """
    return HttpResponse(twiml, content_type='text/xml')