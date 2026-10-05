# -*- coding: utf-8 -*-
"""Bounded Graph requests, safe pagination and conditional writes."""

from urllib.parse import quote, urlparse
import uuid

import requests

from calendar_app.application.calendar_sync_contract import RemoteCalendarError

from .auth import OutlookError

BASE = "https://graph.microsoft.com/v1.0"


class GraphError(RemoteCalendarError):
    def __init__(self, status: int):
        super().__init__(status)
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
            raise GraphError(response.status_code)
        if response.status_code == 204:
            return {}
        try:
            data = response.json()
            if "@odata.etag" in data:
                data["etag"] = data["@odata.etag"]
            if "transactionId" in data:
                data["transaction_id"] = data["transactionId"]
            if "isCancelled" in data:
                data["cancelled"] = data["isCancelled"]
            for event in data.get("value", []):
                if "@odata.etag" in event:
                    event["etag"] = event["@odata.etag"]
                if "transactionId" in event:
                    event["transaction_id"] = event["transactionId"]
                if "isCancelled" in event:
                    event["cancelled"] = event["isCancelled"]
            return data
        except ValueError as exc:
            raise OutlookError("invalid_graph_response") from exc

    def collection(self, path, params=None):
        result, seen = [], set()
        for _ in range(1000):
            if path in seen:
                raise OutlookError("pagination_loop")
            seen.add(path)
            page = self.request("GET", path, params=params)
            if not isinstance(page.get("value"), list):
                raise OutlookError("invalid_graph_response")
            result.extend(page["value"])
            path = page.get("@odata.nextLink")
            if not path:
                return result
            params = None
        raise OutlookError("pagination_limit")

    def profile(self):
        return self.request(
            "GET", "/me", params={"$select": "id,displayName,mail,userPrincipalName"}
        )

    def calendars(self):
        return self.collection("/me/calendars")

    def events(self, calendar, start, end):
        return self.collection(
            f"/me/calendars/{quote(calendar, safe='')}/calendarView",
            {"startDateTime": start, "endDateTime": end, "$top": 200},
        )

    def event(self, event_id):
        return self.request("GET", f"/me/events/{quote(event_id, safe='')}")

    def create(self, calendar, payload, transaction_id):
        return self.request(
            "POST",
            f"/me/calendars/{quote(calendar, safe='')}/events",
            payload={**payload, "transactionId": str(uuid.UUID(transaction_id))},
        )

    def update(self, event_id, payload, etag):
        if not etag:
            raise OutlookError("etag_required")
        return self.request(
            "PATCH", f"/me/events/{quote(event_id, safe='')}", payload=payload, etag=etag
        )

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
