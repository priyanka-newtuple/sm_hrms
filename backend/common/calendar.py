"""Calendar contracts shared by modular modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime


@dataclass
class CalendarEvent:
    title: str
    start_time: datetime
    end_time: datetime
    attendees: list[str]
    description: str | None = None
    location: str | None = None
    timezone: str = "UTC"

    def to_google_format(self) -> dict:
        event = {
            "summary": self.title,
            "start": {"dateTime": self.start_time.isoformat(), "timeZone": self.timezone},
            "end": {"dateTime": self.end_time.isoformat(), "timeZone": self.timezone},
            "attendees": [{"email": email} for email in self.attendees],
        }
        if self.description:
            event["description"] = self.description
        if self.location:
            event["location"] = self.location
        return event


@dataclass
class CalendarEventResult:
    success: bool
    message: str = ""
    event_id: str | None = None
    html_link: str | None = None
    ics_content: str | None = None
    method: str = "unknown"
    metadata: dict = field(default_factory=dict)


@dataclass
class FreeBusySlot:
    start: datetime
    end: datetime


class CalendarProvider(Protocol):
    async def create_event(
        self, event: CalendarEvent, send_invites: bool = True
    ) -> CalendarEventResult: ...
    async def update_event(
        self, event_id: str, event: CalendarEvent, send_updates: bool = True
    ) -> CalendarEventResult: ...
    async def cancel_event(
        self, event_id: str, send_cancellation: bool = True
    ) -> CalendarEventResult: ...
    async def check_availability(
        self, attendees: list[str], start_time: datetime, end_time: datetime
    ) -> dict[str, list[FreeBusySlot]]: ...
