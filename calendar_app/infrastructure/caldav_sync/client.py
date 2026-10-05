# -*- coding: utf-8 -*-
"""Bounded CalDAV discovery/REPORT and conditional resource writes."""

from datetime import UTC, datetime, timedelta
import re
from urllib.parse import unquote, urljoin, urlparse
import uuid
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests

from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError

from .conversion import edited_calendar, new_calendar, records
from .profiles import PROFILES, validate_url

D = "{DAV:}"
C = "{urn:ietf:params:xml:ns:caldav}"
MAX_RESPONSE = 8 * 1024 * 1024


def multistatus(data):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise CalendarSyncError("invalid_calendar_response")
    try:
        root = ET.fromstring(data)
        if root.tag != D + "multistatus":
            raise ValueError
        rows = []
        for response in root.findall(D + "response"):
            href = response.findtext(D + "href")
            props, failures = {}, []
            status = response.findtext(D + "status")
            if status and not re.search(r"\s2\d\d(?:\s|$)", status):
                raise ValueError
            for part in response.findall(D + "propstat"):
                status = part.findtext(D + "status") or ""
                prop = part.find(D + "prop")
                if re.search(r"\s2\d\d(?:\s|$)", status) and prop is not None:
                    props.update({e.tag: e for e in prop})
                else:
                    failures.append(status)
            if not href:
                raise ValueError
            rows.append((href, props, failures))
        return rows
    except (ValueError, ET.ParseError) as exc:
        raise CalendarSyncError("invalid_calendar_response") from exc


class CalDAVClient:
    def __init__(
        self,
        service,
        username,
        password,
        session=None,
        cancelled=lambda: False,
        local_zone="Asia/Seoul",
        resource_cache=None,
    ):
        if service not in PROFILES or not username.strip() or not password:
            raise CalendarSyncError("credentials_required")
        self.service, self.profile = service, PROFILES[service]
        self.auth = (username.strip(), password)
        self.session = session or requests.Session()
        self.cancelled = cancelled
        self.local_zone = local_zone
        self.cache = {}
        self.resource_cache = resource_cache
        self.missing_resources = set()

    def request(self, method, url, *, body=None, headers=None, redirect=False):
        for _ in range(5):
            if self.cancelled():
                raise CalendarSyncError("cancelled")
            validate_url(self.service, url)
            try:
                response = self.session.request(
                    method,
                    url,
                    auth=self.auth,
                    data=body,
                    headers=headers or {},
                    timeout=(10, 30),
                    allow_redirects=False,
                    stream=True,
                )
                try:
                    if response.status_code in (301, 302, 307, 308) and redirect:
                        url = urljoin(url, response.headers.get("Location", ""))
                        validate_url(self.service, url)
                        continue
                    if response.status_code >= 300:
                        raise RemoteCalendarError(response.status_code)
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        if self.cancelled():
                            raise CalendarSyncError("cancelled")
                        size += len(chunk)
                        if size > MAX_RESPONSE:
                            raise CalendarSyncError("calendar_response_too_large")
                        chunks.append(chunk)
                    return (
                        url,
                        requests.structures.CaseInsensitiveDict(response.headers),
                        b"".join(chunks),
                    )
                finally:
                    response.close()
            except requests.RequestException as exc:
                raise CalendarSyncError("network_unavailable") from exc
        raise CalendarSyncError("too_many_redirects")

    def propfind(self, url, names, depth="0"):
        root = ET.Element(D + "propfind")
        prop = ET.SubElement(root, D + "prop")
        for name in names:
            ET.SubElement(prop, name)
        final, _, data = self.request(
            "PROPFIND",
            url,
            body=ET.tostring(root),
            headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
            redirect=True,
        )
        return final, multistatus(data)

    def calendars(self):
        url, rows = self.propfind(
            self.profile["url"], [D + "current-user-principal", C + "calendar-home-set"]
        )
        homes = []
        principal = None
        for _, props, _ in rows:
            home = props.get(C + "calendar-home-set")
            if home is not None:
                homes += [urljoin(url, e.text or "") for e in home.findall(D + "href")]
            user = props.get(D + "current-user-principal")
            if user is not None:
                principal = urljoin(url, user.findtext(D + "href") or "")
        if not homes and principal:
            url, rows = self.propfind(principal, [C + "calendar-home-set"])
            for _, props, _ in rows:
                home = props.get(C + "calendar-home-set")
                if home is not None:
                    homes += [urljoin(url, e.text or "") for e in home.findall(D + "href")]
        if not homes:
            raise CalendarSyncError("calendar_discovery_failed")
        calendars = {}
        for home in homes:
            final, rows = self.propfind(
                home,
                [
                    D + "resourcetype",
                    D + "displayname",
                    D + "current-user-privilege-set",
                    C + "supported-calendar-component-set",
                ],
                "1",
            )
            for href, props, failures in rows:
                resource = props.get(D + "resourcetype")
                if resource is None:
                    if failures:
                        raise CalendarSyncError("calendar_discovery_incomplete")
                    continue
                if resource.find(C + "calendar") is None:
                    continue
                components = props.get(C + "supported-calendar-component-set")
                if components is not None and not any(
                    e.get("name") == "VEVENT" for e in components
                ):
                    continue
                remote = validate_url(self.service, urljoin(final, href))
                privileges = props.get(D + "current-user-privilege-set")
                tags = {e.tag for e in privileges.iter()} if privileges is not None else set()
                writable = (
                    D + "all" in tags
                    or D + "write" in tags
                    or {D + "write-content", D + "bind", D + "unbind"} <= tags
                )
                name = props.get(D + "displayname")
                calendars[remote] = {
                    "id": remote,
                    "name": name.text if name is not None and name.text else urlparse(remote).path,
                    "can_edit": bool(self.profile["writable"] and writable),
                }
        if not calendars:
            raise CalendarSyncError("no_calendars")
        return list(calendars.values())

    def events(self, calendar, start, end, _full_content=False):
        start_time, end_time = [
            datetime.fromisoformat(v.replace("Z", "+00:00")) for v in (start, end)
        ]
        root = ET.Element(C + "calendar-query")
        prop = ET.SubElement(root, D + "prop")
        ET.SubElement(prop, D + "getetag")
        if _full_content:
            ET.SubElement(prop, C + "calendar-data")
        filt = ET.SubElement(root, C + "filter")
        comp = ET.SubElement(
            ET.SubElement(filt, C + "comp-filter", name="VCALENDAR"),
            C + "comp-filter",
            name="VEVENT",
        )
        ET.SubElement(
            comp,
            C + "time-range",
            start=start_time.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
            end=end_time.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        )
        final, _, data = self.request(
            "REPORT",
            calendar,
            body=ET.tostring(root),
            headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        )
        resources = {}
        cached = self.resource_cache.load(calendar) if self.resource_cache else self.cache
        requested = {}
        for href, props, failures in multistatus(data):
            etag, content = props.get(D + "getetag"), props.get(C + "calendar-data")
            if failures or etag is None or not etag.text:
                raise CalendarSyncError("calendar_report_incomplete")
            url = self.resource_url(final, href)
            if url in requested or url in resources:
                raise CalendarSyncError("duplicate_remote_event")
            if content is not None and content.text:
                resources[url] = (etag.text, content.text)
            elif url in cached and cached[url][0] == etag.text:
                try:
                    records(url, *cached[url], start_time, end_time, self.local_zone)
                    resources[url] = cached[url]
                except CalendarSyncError:
                    requested[url] = etag.text
            else:
                if _full_content:
                    raise CalendarSyncError("calendar_report_incomplete")
                requested[url] = etag.text
            if len(resources) + len(requested) > 10000:
                raise CalendarSyncError("too_many_events")
        # Validate every resource before installing a new cache snapshot.
        if requested:
            remaining = MAX_RESPONSE - sum(
                len(body.encode("utf-8", errors="strict")) for _, body in resources.values()
            )
            try:
                resources.update(self._multiget(calendar, requested, remaining))
            except RemoteCalendarError as exc:
                if not _full_content and exc.status in {405, 501}:
                    return self.events(calendar, start, end, _full_content=True)
                raise
        result = []
        for url, (etag, content) in resources.items():
            if self.cancelled():
                raise CalendarSyncError("cancelled")
            result.extend(records(url, etag, content, start_time, end_time, self.local_zone))
            if len(result) > 10000:
                raise CalendarSyncError("too_many_events")
        if (
            sum(len(content.encode("utf-8", errors="strict")) for _, content in resources.values())
            > MAX_RESPONSE
        ):
            raise CalendarSyncError("calendar_response_too_large")
        if self.cancelled():
            raise CalendarSyncError("cancelled")
        if self.resource_cache:
            self.resource_cache.save(calendar, resources)
        for href in list(self.cache):
            if href.startswith(calendar.rstrip("/") + "/") and href not in resources:
                self.cache.pop(href)
        self.cache.update(resources)
        self.missing_resources.difference_update(resources)
        return result

    def _multiget(self, calendar, requested, remaining=MAX_RESPONSE):
        result = {}
        items = list(requested)
        for offset in range(0, len(items), 50):
            expected = set(items[offset : offset + 50])
            root = ET.Element(C + "calendar-multiget")
            prop = ET.SubElement(root, D + "prop")
            ET.SubElement(prop, D + "getetag")
            ET.SubElement(prop, C + "calendar-data")
            for url in sorted(expected):
                ET.SubElement(root, D + "href").text = urlparse(url).path
            final, _, data = self.request(
                "REPORT",
                calendar,
                body=ET.tostring(root),
                headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
            )
            found = set()
            for href, props, failures in multistatus(data):
                url = self.resource_url(final, href)
                etag, content = props.get(D + "getetag"), props.get(C + "calendar-data")
                if (
                    url not in expected
                    or url in found
                    or failures
                    or etag is None
                    or etag.text != requested[url]
                    or content is None
                    or not content.text
                ):
                    raise CalendarSyncError("calendar_report_incomplete")
                found.add(url)
                remaining -= len(content.text.encode("utf-8", errors="strict"))
                if remaining < 0:
                    raise CalendarSyncError("calendar_response_too_large")
                result[url] = (etag.text, content.text)
            if found != expected:
                raise CalendarSyncError("calendar_report_incomplete")
        return result

    def resource_url(self, calendar, href):
        url = validate_url(self.service, urljoin(calendar, href))
        parent, child = urlparse(calendar), urlparse(url)
        decoded = unquote(child.path)
        if (
            parent.netloc != child.netloc
            or any(part in (".", "..") for part in decoded.split("/"))
            or not decoded.startswith(unquote(parent.path).rstrip("/") + "/")
        ):
            raise CalendarSyncError("unsafe_caldav_resource")
        return url

    def event(self, event_id):
        href, _, rid = event_id.partition("#aircal-rid=")
        validate_url(self.service, href)
        if href in self.missing_resources:
            raise RemoteCalendarError(404)
        if href in self.cache:
            etag, data = self.cache[href]
        else:
            try:
                _, headers, data = self.request("GET", href)
            except RemoteCalendarError as exc:
                if exc.status == 404:
                    self.missing_resources.add(href)
                raise
            etag = headers.get("ETag") or headers.get("Etag")
            if not etag:
                raise CalendarSyncError("etag_required")
            self.cache[href] = (etag, data)
        if rid:
            target = datetime.fromisoformat(unquote(rid))
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            events = records(
                href,
                etag,
                data,
                target - timedelta(days=2),
                target + timedelta(days=2),
                self.local_zone,
            )
        else:
            events = records(href, etag, data, zone=self.local_zone)
        match = next((e for e in events if e["id"] == event_id), None)
        if match is None:
            raise RemoteCalendarError(404)
        return match

    @staticmethod
    def to_task(event, local_zone="Asia/Seoul"):
        # Event records store canonical local task fields to make conflicts JSON-safe.
        task = dict(event["task"])
        original_zone = event.get("zone", local_zone)
        if not task["all_day"] and original_zone != local_zone:
            for key in ("deadline", "end_date"):
                task[key] = (
                    datetime.fromisoformat(task[key])
                    .replace(tzinfo=ZoneInfo(original_zone))
                    .astimezone(ZoneInfo(local_zone))
                    .replace(tzinfo=None)
                    .isoformat(timespec="seconds")
                )
        return task

    @staticmethod
    def from_task(task, local_zone="Asia/Seoul"):
        return {"task": dict(task), "zone": local_zone}

    @staticmethod
    def edit_payload(task, remote, local_zone="Asia/Seoul"):
        return edited_calendar(task, remote, local_zone)

    def create(self, calendar, payload, transaction_id):
        if not self.profile["writable"]:
            raise CalendarSyncError("calendar_read_only")
        transaction = str(uuid.UUID(transaction_id))
        href = self.resource_url(calendar, transaction + ".ics")
        self.missing_resources.discard(href)
        data = new_calendar(payload["task"], transaction, payload["zone"])
        try:
            self.request(
                "PUT",
                href,
                body=data,
                headers={"If-None-Match": "*", "Content-Type": "text/calendar; charset=utf-8"},
            )
        except RemoteCalendarError as exc:
            if exc.status != 412:
                raise
            self.cache.pop(href, None)
            existing = self.event(href)
            if existing.get("transaction_id") != transaction:
                raise CalendarSyncError("create_conflict") from exc
            return existing
        self.cache.pop(href, None)
        self.missing_resources.discard(href)
        return self.event(href)

    def update(self, event_id, payload, etag):
        if not self.profile["writable"] or self.event(event_id).get("read_only"):
            raise CalendarSyncError("event_read_only")
        if not etag:
            raise CalendarSyncError("etag_required")
        self.request(
            "PUT",
            event_id,
            body=payload,
            headers={"If-Match": etag, "Content-Type": "text/calendar; charset=utf-8"},
        )
        self.cache.pop(event_id, None)
        self.missing_resources.discard(event_id)
        return self.event(event_id)

    def delete(self, event_id, etag):
        if not self.profile["writable"] or self.event(event_id).get("read_only"):
            raise CalendarSyncError("event_read_only")
        if not etag:
            raise CalendarSyncError("etag_required")
        self.request("DELETE", event_id, headers={"If-Match": etag})
        self.cache.pop(event_id, None)
        return {}
