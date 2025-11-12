import base64
import os
from openai import OpenAI
from django.conf import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def generate_voice_reminder(reminder_text: str, user_name: str = "Jackson", voice: str = "alloy") -> bytes:
    """
    Generate a friendly, natural audio reminder using GPT-4o audio model.

    Args:
        reminder_text (str): The short reminder text (e.g., "work out by 5 p.m.")
        user_name (str): Optional name for personalization.
        voice (str): Voice to use for playback ("alloy", "verse", "bright", etc.)

    Returns:
        bytes: The generated WAV audio bytes.
    """
    completion = client.chat.completions.create(
        model="gpt-4o-audio-preview",
        modalities=["text", "audio"],
        audio={"voice": voice, "format": "wav"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a friendly AI assistant that creates short, natural, and motivating spoken reminders. "
                    "Make them sound like they’re from a helpful friend. Be warm, clear, concise and most importantly a touch of Humor. "
                    "Add a touch of encouragement if the reminder is about wellness or workouts."
                ),
            },
            {
                "role": "user",
                "content": f"The reminder is for {user_name}. The reminder says: '{reminder_text}'."
            },
        ],
    )

    audio_data = completion.choices[0].message.audio.data
    wav_bytes = base64.b64decode(audio_data)
    return wav_bytes

