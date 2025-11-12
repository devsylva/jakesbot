from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from django.conf import settings

account_sid = settings.TWILIO_ACCOUNT_SID
auth_token = settings.TWILIO_AUTH_TOKEN
client = Client(account_sid, auth_token)

def send_call_reminder(reminder_id):
    try:
        call = client.calls.create(
            to="+2349132895231",  # recipient
            from_=settings.TWILIO_PHONE_NUMBER,  # your Twilio number
            url=f"https://c1dc5a17f682.ngrok-free.app/voice/{reminder_id}/"
        )
        return f"📞 Call initiated! SID: {call.sid}"

    except TwilioRestException as e:
        return f"❌ Twilio Error: {e}"
        
    except Exception as e:
        return  f"❌ General Error: {e}"
