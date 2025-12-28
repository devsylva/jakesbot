"""
Script to generate a new Google OAuth refresh token.
Run this locally (not on VPS) to get a new refresh token.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from django.conf import settings
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_assistant.settings')
django.setup()

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]

def generate_refresh_token():
    """Generate a new refresh token using OAuth flow."""
    
    # Create credentials dict from environment variables
    client_config = {
        "installed": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/"]
        }
    }
    
    # Run the OAuth flow
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8080)
    
    print("\n" + "="*60)
    print("SUCCESS! Copy this refresh token to your .env file:")
    print("="*60)
    print(f"\nGOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("\n" + "="*60)
    print("\nAlso update these if they changed:")
    print("="*60)
    print(f"GOOGLE_CLIENT_ID={settings.GOOGLE_CLIENT_ID}")
    print(f"GOOGLE_CLIENT_SECRET={settings.GOOGLE_CLIENT_SECRET}")
    print("\n")

if __name__ == "__main__":
    print("Starting OAuth flow to generate refresh token...")
    print("A browser window will open for authentication.")
    print("Make sure you're logged into the correct Google account.\n")
    
    try:
        generate_refresh_token()
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure:")
        print("1. GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set in .env")
        print("2. You have google-auth-oauthlib installed")
        print("3. You're running this on a machine with a browser")
