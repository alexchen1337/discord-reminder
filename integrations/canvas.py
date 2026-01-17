import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from utils.encryption import encrypt_token, decrypt_token


class CanvasClient:
    def __init__(self):
        pass
    
    async def validate_token(self, canvas_url: str, api_token: str) -> Optional[Dict[str, Any]]:
        """Validate Canvas API token and get user info"""
        canvas_url = canvas_url.rstrip("/")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{canvas_url}/api/v1/users/self",
                headers={"Authorization": f"Bearer {api_token}"}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    
    async def get_assignments(
        self,
        canvas_url: str,
        encrypted_token: str,
        days_ahead: int = 7
    ) -> List[Dict[str, Any]]:
        """Get assignments due in the next N days"""
        canvas_url = canvas_url.rstrip("/")
        token = decrypt_token(encrypted_token)
        
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=days_ahead)
        
        assignments = []
        
        async with aiohttp.ClientSession() as session:
            # get user's courses
            courses = []
            async with session.get(
                f"{canvas_url}/api/v1/courses",
                headers={"Authorization": f"Bearer {token}"},
                params={"enrollment_state": "active", "per_page": 100}
            ) as resp:
                if resp.status == 200:
                    courses = await resp.json()
            
            # get assignments for each course
            for course in courses:
                course_id = course.get("id")
                course_name = course.get("name", "Unknown Course")
                
                async with session.get(
                    f"{canvas_url}/api/v1/courses/{course_id}/assignments",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "per_page": 100,
                        "order_by": "due_at",
                    }
                ) as resp:
                    if resp.status != 200:
                        continue
                    
                    course_assignments = await resp.json()
                    
                    for assignment in course_assignments:
                        due_at = assignment.get("due_at")
                        if not due_at:
                            continue
                        
                        # parse due date
                        try:
                            due_datetime = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            continue
                        
                        # filter by date range
                        if start_date <= due_datetime.replace(tzinfo=None) <= end_date:
                            assignments.append({
                                "id": assignment.get("id"),
                                "title": assignment.get("name", "Untitled"),
                                "due_at": due_at,
                                "date": due_at,  # for calendar rendering
                                "course": course_name,
                                "course_id": course_id,
                                "points": assignment.get("points_possible"),
                                "url": assignment.get("html_url"),
                                "source": "canvas",
                            })
        
        return sorted(assignments, key=lambda x: x.get("due_at", ""))
    
    async def get_all_assignments(
        self,
        canvas_url: str,
        encrypted_token: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get all assignments in a date range"""
        canvas_url = canvas_url.rstrip("/")
        token = decrypt_token(encrypted_token)
        
        assignments = []
        
        async with aiohttp.ClientSession() as session:
            # use calendar_events endpoint for broader date range
            params = {
                "type": "assignment",
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "per_page": 100,
            }
            
            async with session.get(
                f"{canvas_url}/api/v1/calendar_events",
                headers={"Authorization": f"Bearer {token}"},
                params=params
            ) as resp:
                if resp.status == 200:
                    events = await resp.json()
                    
                    for event in events:
                        assignment = event.get("assignment", {})
                        context = event.get("context_name", "Unknown Course")
                        
                        due_at = assignment.get("due_at") or event.get("end_at")
                        
                        assignments.append({
                            "id": assignment.get("id") or event.get("id"),
                            "title": event.get("title", "Untitled"),
                            "due_at": due_at,
                            "date": due_at,
                            "course": context,
                            "url": event.get("html_url"),
                            "source": "canvas",
                        })
        
        return sorted(assignments, key=lambda x: x.get("due_at", ""))
    
    async def get_upcoming_calendar_events(
        self,
        canvas_url: str,
        encrypted_token: str,
        days_ahead: int = 7
    ) -> List[Dict[str, Any]]:
        """Get calendar events (not just assignments) in the next N days"""
        canvas_url = canvas_url.rstrip("/")
        token = decrypt_token(encrypted_token)
        
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=days_ahead)
        
        events = []
        
        async with aiohttp.ClientSession() as session:
            params = {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "per_page": 100,
            }
            
            async with session.get(
                f"{canvas_url}/api/v1/calendar_events",
                headers={"Authorization": f"Bearer {token}"},
                params=params
            ) as resp:
                if resp.status == 200:
                    calendar_events = await resp.json()
                    
                    for event in calendar_events:
                        event_type = event.get("type", "event")
                        start_at = event.get("start_at") or event.get("all_day_date")
                        
                        events.append({
                            "id": event.get("id"),
                            "title": event.get("title", "Untitled"),
                            "date": start_at,
                            "end": event.get("end_at"),
                            "course": event.get("context_name"),
                            "type": event_type,
                            "url": event.get("html_url"),
                            "source": "canvas",
                        })
        
        return sorted(events, key=lambda x: x.get("date", ""))
    
    async def get_announcements(
        self,
        canvas_url: str,
        encrypted_token: str,
        since: datetime = None
    ) -> List[Dict[str, Any]]:
        """Get announcements from all courses, optionally since a specific time"""
        canvas_url = canvas_url.rstrip("/")
        token = decrypt_token(encrypted_token)
        
        if since is None:
            since = datetime.utcnow() - timedelta(days=1)
        
        announcements = []
        
        async with aiohttp.ClientSession() as session:
            # get user's courses
            courses = []
            async with session.get(
                f"{canvas_url}/api/v1/courses",
                headers={"Authorization": f"Bearer {token}"},
                params={"enrollment_state": "active", "per_page": 100}
            ) as resp:
                if resp.status == 200:
                    courses = await resp.json()
            
            # get announcements for each course
            for course in courses:
                course_id = course.get("id")
                course_name = course.get("name", "Unknown Course")
                
                async with session.get(
                    f"{canvas_url}/api/v1/courses/{course_id}/discussion_topics",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "only_announcements": "true",
                        "per_page": 20,
                        "order_by": "recent_activity",
                    }
                ) as resp:
                    if resp.status != 200:
                        continue
                    
                    course_announcements = await resp.json()
                    
                    for ann in course_announcements:
                        posted_at = ann.get("posted_at")
                        if not posted_at:
                            continue
                        
                        try:
                            posted_datetime = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            continue
                        
                        # filter by since date
                        if posted_datetime.replace(tzinfo=None) >= since:
                            # strip HTML from message
                            message = ann.get("message", "")
                            # basic HTML stripping
                            import re
                            message = re.sub(r'<[^>]+>', '', message)
                            
                            announcements.append({
                                "id": ann.get("id"),
                                "title": ann.get("title", "Untitled"),
                                "message": message,
                                "posted_at": posted_at,
                                "course": course_name,
                                "course_id": course_id,
                                "author": ann.get("author", {}).get("display_name"),
                                "url": ann.get("html_url"),
                            })
        
        return sorted(announcements, key=lambda x: x.get("posted_at", ""), reverse=True)

