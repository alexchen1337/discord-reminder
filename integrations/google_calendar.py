import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
import config
from utils.encryption import encrypt_token, decrypt_token


class GoogleCalendarClient:
    BASE_URL = "https://www.googleapis.com/calendar/v3"
    
    def __init__(self):
        self.client_config = {
            "web": {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uris": [config.GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    
    def get_auth_url(self, state: str) -> str:
        """Generate OAuth2 authorization URL"""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=config.GOOGLE_SCOPES,
            redirect_uri=config.GOOGLE_REDIRECT_URI
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state
        )
        return auth_url
    
    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens"""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=config.GOOGLE_SCOPES,
            redirect_uri=config.GOOGLE_REDIRECT_URI
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # get user email
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {credentials.token}"}
            ) as resp:
                user_info = await resp.json()
        
        return {
            "email": user_info.get("email"),
            "access_token": encrypt_token(credentials.token),
            "refresh_token": encrypt_token(credentials.refresh_token) if credentials.refresh_token else None,
            "token_expires_at": credentials.expiry,
        }
    
    async def _get_valid_token(
        self,
        access_token: str,
        refresh_token: str,
        token_expires_at: Optional[datetime]
    ) -> tuple[str, Optional[str], Optional[datetime]]:
        """Get valid access token, refreshing if needed"""
        decrypted_access = decrypt_token(access_token)
        decrypted_refresh = decrypt_token(refresh_token) if refresh_token else None
        
        # check if token is expired or about to expire
        if token_expires_at and datetime.utcnow() >= token_expires_at - timedelta(minutes=5):
            if decrypted_refresh:
                credentials = Credentials(
                    token=decrypted_access,
                    refresh_token=decrypted_refresh,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=config.GOOGLE_CLIENT_ID,
                    client_secret=config.GOOGLE_CLIENT_SECRET,
                )
                credentials.refresh(Request())
                return (
                    credentials.token,
                    encrypt_token(credentials.token),
                    credentials.expiry
                )
        
        return decrypted_access, None, None
    
    async def get_events(
        self,
        access_token: str,
        refresh_token: str,
        token_expires_at: Optional[datetime],
        time_min: datetime,
        time_max: datetime,
        calendar_id: str = "primary"
    ) -> tuple[List[Dict[str, Any]], Optional[str], Optional[datetime]]:
        """Fetch events from Google Calendar"""
        token, new_encrypted_token, new_expiry = await self._get_valid_token(
            access_token, refresh_token, token_expires_at
        )
        
        events = []
        page_token = None
        
        async with aiohttp.ClientSession() as session:
            while True:
                params = {
                    "timeMin": time_min.isoformat() + "Z",
                    "timeMax": time_max.isoformat() + "Z",
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": 250,
                }
                if page_token:
                    params["pageToken"] = page_token
                
                async with session.get(
                    f"{self.BASE_URL}/calendars/{calendar_id}/events",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params
                ) as resp:
                    if resp.status != 200:
                        break
                    
                    data = await resp.json()
                    
                    for item in data.get("items", []):
                        start = item.get("start", {})
                        start_time = start.get("dateTime") or start.get("date")
                        
                        events.append({
                            "id": item.get("id"),
                            "title": item.get("summary", "Untitled"),
                            "date": start_time,
                            "end": item.get("end", {}).get("dateTime") or item.get("end", {}).get("date"),
                            "description": item.get("description"),
                            "location": item.get("location"),
                            "source": "google",
                        })
                    
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
        
        return events, new_encrypted_token, new_expiry
    
    async def get_upcoming_events(
        self,
        access_token: str,
        refresh_token: str,
        token_expires_at: Optional[datetime],
        days: int = 7
    ) -> tuple[List[Dict[str, Any]], Optional[str], Optional[datetime]]:
        """Get events in the next N days"""
        time_min = datetime.utcnow()
        time_max = time_min + timedelta(days=days)
        return await self.get_events(
            access_token, refresh_token, token_expires_at, time_min, time_max
        )
    
    async def get_events_starting_soon(
        self,
        access_token: str,
        refresh_token: str,
        token_expires_at: Optional[datetime],
        hours: int = 1
    ) -> tuple[List[Dict[str, Any]], Optional[str], Optional[datetime]]:
        """Get events starting in the next N hours"""
        time_min = datetime.utcnow()
        time_max = time_min + timedelta(hours=hours)
        return await self.get_events(
            access_token, refresh_token, token_expires_at, time_min, time_max
        )
    
    async def get_calendars(
        self,
        access_token: str,
        refresh_token: str,
        token_expires_at: Optional[datetime]
    ) -> tuple[List[Dict[str, Any]], Optional[str], Optional[datetime]]:
        """Get list of user's calendars"""
        token, new_encrypted_token, new_expiry = await self._get_valid_token(
            access_token, refresh_token, token_expires_at
        )
        
        calendars = []
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/users/me/calendarList",
                headers={"Authorization": f"Bearer {token}"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("items", []):
                        calendars.append({
                            "id": item.get("id"),
                            "name": item.get("summary"),
                            "primary": item.get("primary", False),
                        })
        
        return calendars, new_encrypted_token, new_expiry

