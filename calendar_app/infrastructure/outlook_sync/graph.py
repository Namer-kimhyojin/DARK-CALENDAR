# -*- coding: utf-8 -*-
"""Bounded Graph requests, safe pagination and conditional writes."""

from urllib.parse import quote, urlparse
import uuid

import requests

from calendar_app.application.calendar_sync_contract import RemoteCalendarError
from calendar_app.infrastructure.calendar_sync.http_retry import retry_after_seconds

from .auth import OutlookError

BASE = "https://graph.microsoft.com/v1.0"


class GraphError(RemoteCalendarError):
    def __init__(self, status: int, retry_after=None):
        super().__init__(status)
        self.retry_after = retry_after
        self.args = (f"graph_http_{status}",)


class GraphClient:
    def __init__(self, token: str, session=None, cancelled=lambda: False):
        self.session = session or requests.Session()
        self.cancelled = cancelled
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": 'outlook.timezone="UTC", IdType="ImmutableId", outlook.body-content-type="text"',
        }

    def request(self, method, path, *, params=None, payload=None, etag=None):
        if self.cancelled():
            raise OutlookError("cancelled")
        url = path if path.startswith("https://") else BASE + path
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "graph.microsoft.com"
            or not parsed.path.startswith("/v1.0/")
        ):
            raise OutlookError("unsafe_graph_url")
        headers = dict(self.headers)
        if etag:
            headers["If-Match"] = etag
        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=payload,
                timeout=(10, 30),
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise OutlookError("network_unavailable") from exc
        if response.status_code >= 300:
            raise GraphError(
                response.status_code,
                retry_after_seconds(response.headers.get("Retry-After")),
            )
        if response.status_code == 204:
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise OutlookError("invalid_graph_response") from exc
        if not isinstance(data, dict):
            raise OutlookError("invalid_graph_response")
        values = data.get("value", [])
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            raise OutlookError("invalid_graph_response")
        for event in [data, *values]:
            if any(
                key in event and not isinstance(event[key], bool)
                for key in ("isCancelled", "isAllDay")
            ):
                raise OutlookError("invalid_graph_response")
            if "@odata.etag" in event:
                revision = event["@odata.etag"]
                if (
                    not isinstance(revision, str)
                    or not revision.strip()
                    or "\r" in revision
                    or "\n" in revision
                ):
                    raise OutlookError("invalid_graph_response")
                event["etag"] = event["@odata.etag"]
            if "transactionId" in event:
                if event["transactionId"] is not None and not isinstance(
                    event["transactionId"], str
                ):
                    raise OutlookError("invalid_graph_response")
                event["transaction_id"] = event["transactionId"]
            if "isCancelled" in event:
                event["cancelled"] = event["isCancelled"]
        return data

    def collection(self, path, params=None):
        result, seen, identities = [], set(), set()
        for _ in range(1000):
            if path in seen:
                raise OutlookError("pagination_loop")
            seen.add(path)
            page = self.request("GET", path, params=params)
            if not isinstance(page.get("value"), list):
                raise OutlookError("invalid_graph_response")
            for item in page["value"]:
                identifier = item.get("id")
                if not isinstance(identifier, str) or not identifier.strip():
                    raise OutlookError("invalid_graph_response")
                if identifier in identities:
                    raise OutlookError("duplicate_remote_event")
                identities.add(identifier)
            result.extend(page["value"])
            path = page.get("@odata.nextLink")
            if path is not None and not isinstance(path, str):
                raise OutlookError("invalid_graph_response")
            if not path:
                return result
            params = None
        raise OutlookError("pagination_limit")

    def profile(self):
        profile = self.request(
            "GET", "/me", params={"$select": "id,displayName,mail,userPrincipalName"}
        )
        identifier = profile.get("id")
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or any(
                profile.get(key) is not None and not isinstance(profile[key], str)
                for key in ("mail", "userPrincipalName", "displayName")
            )
        ):
            raise OutlookError("invalid_graph_response")
        return profile

    def calendars(self):
        calendars = self.collection("/me/calendars")
        if any(
            not isinstance(calendar.get("name"), str)
            or not isinstance(calendar.get("canEdit", False), bool)
            for calendar in calendars
        ):
            raise OutlookError("invalid_graph_response")
        for calendar in calendars:
            calendar["can_edit"] = calendar.get("canEdit", False)
        return calendars

    def events(self, calendar, start, end):
        return self.collection(
            f"/me/calendars/{quote(calendar, safe='')}/calendarView",
            {"startDateTime": start, "endDateTime": end, "$top": 200},
        )

    def event(self, event_id):
        return self._event_response(
            self.request("GET", f"/me/events/{quote(event_id, safe='')}"), event_id
        )

    def create(self, calendar, payload, transaction_id):
        return self._event_response(
            self.request(
                "POST",
                f"/me/calendars/{quote(calendar, safe='')}/events",
                payload={**payload, "transactionId": str(uuid.UUID(transaction_id))},
            )
        )

    def update(self, event_id, payload, etag):
        if not etag:
            raise OutlookError("etag_required")
        return self._event_response(
            self.request(
                "PATCH", f"/me/events/{quote(event_id, safe='')}", payload=payload, etag=etag
            ),
            event_id,
        )

    @staticmethod
    def _event_response(event, expected_id=None):
        identifier = event.get("id")
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or (expected_id is not None and identifier != expected_id)
        ):
            raise OutlookError("invalid_graph_response")
        return event

    def delete(self, event_id, etag):
        if not etag:
            raise OutlookError("etag_required")
        return self.request("DELETE", f"/me/events/{quote(event_id, safe='')}", etag=etag)

    @staticmethod
    def to_task(event, local_zone):
        from .conversion import from_graph

        return from_graph(event, local_zone)

    @staticmethod
    def from_task(task, local_zone):
        from .conversion import to_graph

        return to_graph(task, local_zone)

    @classmethod
    def edit_payload(cls, task, remote, local_zone):
        original = cls.to_task(remote, local_zone)
        payload = cls.from_task(task, local_zone)
        result = {}
        for local, graph in (
            ("name", "subject"),
            ("description", "body"),
            ("location", "location"),
        ):
            if (task.get(local) or "") != (original.get(local) or ""):
                if graph == "body" and remote.get("isOnlineMeeting"):
                    raise OutlookError("online_meeting_body_not_supported")
                result[graph] = payload[graph]
        if any(
            str(task.get(key) or "") != str(original.get(key) or "")
            for key in ("deadline", "end_date", "all_day")
        ):
            result.update({key: payload[key] for key in ("start", "end", "isAllDay")})
        return result
