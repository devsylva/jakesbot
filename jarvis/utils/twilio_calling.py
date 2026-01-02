from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from django.conf import settings

account_sid = settings.TWILIO_ACCOUNT_SID
auth_token = settings.TWILIO_AUTH_TOKEN
client = Client(account_sid, auth_token)

def send_call_reminder(reminder_id):
    try:
        base_url = settings.TWILIO_VOICE_BASE_URL  # e.g., "https://yourdomain.com/voice"
        call_url = f"{base_url}/{reminder_id}/"
        call = client.calls.create(
            to="+2349161391003",  # recipient 2349161391003
            from_=settings.TWILIO_PHONE_NUMBER,  # your Twilio number
            url=call_url
        )
        return f"📞 Call initiated! SID: {call.sid}"

    except TwilioRestException as e:
        return f"❌ Twilio Error: {e}"
        
    except Exception as e:
        return  f"❌ General Error: {e}"
