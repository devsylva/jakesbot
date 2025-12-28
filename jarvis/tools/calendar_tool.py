import logging
from typing import Any, Dict, List
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from django.conf import settings
import os
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']

class CalendarTool:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.service = None  
        self.creds = None
        self._load_credentials()

    def _load_credentials(self):
        """
        Load credentials using refresh token from environment variables.
        This approach works on VPS without requiring browser authentication.
        """
        token_path = os.path.join(settings.BASE_DIR, f'tokens/token_{self.user_id}.json')
        
        # Try to load existing token file first
        if os.path.exists(token_path):
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        # If no valid credentials, create from environment variables
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                # Refresh expired credentials
                logger.info(f"Refreshing expired credentials for user {self.user_id}")
                self.creds.refresh(Request())
            else:
                # Create credentials from environment variables (no browser needed)
                logger.info(f"Creating credentials from environment variables for user {self.user_id}")
                self.creds = Credentials(
                    token=None,
                    refresh_token=settings.GOOGLE_REFRESH_TOKEN,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.GOOGLE_CLIENT_ID,
                    client_secret=settings.GOOGLE_CLIENT_SECRET,
                    scopes=SCOPES
                )
                # Refresh to get access token
                self.creds.refresh(Request())
            
            # Save credentials for future use
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "w") as token:
                token.write(self.creds.to_json())
            logger.info(f"Credentials saved to {token_path}")

        self.service = build("calendar", "v3", credentials=self.creds)

    @staticmethod
    def json_schema_create_calendar_event() -> Dict[str, Any]:
        return {
            "name": "create_calendar_event",
            "description": "Create an event on Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start_iso": {"type": "string"},
                    "end_iso": {"type": "string"},
                },
                "required": ["summary", "start_iso", "end_iso"],
            },
        }

    @staticmethod
    def json_schema_list_calendar_events() -> Dict[str, Any]:
        return {
            "name": "list_calendar_events",
            "description": "List events from Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 5}
                },
            },
        }

    @staticmethod
    def json_schema_update_calendar_event() -> Dict[str, Any]:
        return {
            "name": "update_calendar_event",
            "description": "Update an event on Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "new_summary": {"type": "string"},
                    "new_start_iso": {"type": "string"},
                    "new_end_iso": {"type": "string"},
                },
                "required": ["event_id"],
            },
        }

    @staticmethod
    def json_schema_delete_calendar_event() -> Dict[str, Any]:
        return {
            "name": "delete_calendar_event",
            "description": "Delete an event from Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                },
                "required": ["event_id"],
            },
        }

    # 📅 Create event
    def create_calendar_event(self, summary: str, start_iso: str, end_iso: str) -> str:
        logger.info(f"AI Agent called create_calendar_event for user {self.user_id}: summary='{summary}', start='{start_iso}', end='{end_iso}'")
        event = {
            "summary": summary,
            "start": {"dateTime": start_iso, "timeZone": "Africa/Lagos"},
            "end": {"dateTime": end_iso, "timeZone": "Africa/Lagos"},
        }
        created_event = self.service.events().insert(calendarId="primary", body=event).execute()
        logger.info(f"Successfully created calendar event for user {self.user_id}: event_id={created_event.get('id')}")
        return f"✅ Event '{summary}' has been created successfully from {start_iso} to {end_iso}."

    # 📋 List events
    def list_calendar_events(self, max_results: int = 5) -> str:
        logger.info(f"AI Agent called list_calendar_events for user {self.user_id}: max_results={max_results}")
        from django.utils import timezone
        
        # Get current time in ISO format to filter from now onwards (UTC)
        now = timezone.now().isoformat()
        
        events_result = self.service.events().list(
            calendarId="primary", 
            timeMin=now,  # Only get events from now onwards
            maxResults=max_results, 
            singleEvents=True, 
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        logger.info(f"Retrieved {len(events)} events for user {self.user_id}")

        if not events:
            logger.info(f"No upcoming events found for user {self.user_id}")
            return "📭 You have no upcoming events."

        response_lines = ["📅 Here are your upcoming events:"]
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "(No title)")
            event_id = event.get("id", "No ID")
            response_lines.append(f"• {summary} — starts at {start} (ID: {event_id})")
        
        logger.info(f"Successfully listed {len(events)} events for user {self.user_id}")
        return "\n".join(response_lines)

    # 📝 Update event
    def update_calendar_event(self, event_id: str, new_summary: str = None, new_start_iso: str = None, new_end_iso: str = None) -> str:
        logger.info(f"AI Agent called update_calendar_event for user {self.user_id}: event_id='{event_id}', new_summary='{new_summary}', new_start='{new_start_iso}', new_end='{new_end_iso}'")
        event = self.service.events().get(calendarId="primary", eventId=event_id).execute()
        old_summary = event.get("summary", "(No title)")

        if new_summary:
            event["summary"] = new_summary
        if new_start_iso:
            event["start"]["dateTime"] = new_start_iso
        if new_end_iso:
            event["end"]["dateTime"] = new_end_iso

        updated_event = self.service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        logger.info(f"Successfully updated calendar event for user {self.user_id}: event_id={event_id}, old_summary='{old_summary}', new_summary='{event['summary']}'")
        return f"📝 Event '{old_summary}' has been updated to '{event['summary']}'."

    # 🗑️ Delete event
    def delete_calendar_event(self, event_id: str) -> str:
        logger.info(f"AI Agent called delete_calendar_event for user {self.user_id}: event_id='{event_id}'")
        try:
            self.service.events().delete(calendarId="primary", eventId=event_id).execute()
            logger.info(f"Successfully deleted calendar event for user {self.user_id}: event_id={event_id}")
            return f"🗑️ The event with ID '{event_id}' has been deleted successfully."
        except Exception as e:
            logger.error(f"Failed to delete event {event_id} for user {self.user_id}: {e}")
            return f"⚠️ Sorry, I couldn't delete the event. Reason: {e}"
