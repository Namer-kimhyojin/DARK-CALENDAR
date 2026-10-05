# -*- coding: utf-8 -*-
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.outlook_sync.auth import OutlookError
from calendar_app.infrastructure.outlook_sync.graph import GraphClient, GraphError


def response(data, status=200):
    reply = Mock(status_code=status)
    reply.json.return_value = data
    return reply


def test_pagination_normalizes_revisions_and_keeps_headers():
    session = Mock()
    session.request.side_effect = [
        response(
            {
                "value": [{"id": "1", "@odata.etag": "tag", "transactionId": "tx"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/events?page=2",
            }
        ),
        response({"value": [{"id": "2"}]}),
    ]
    events = GraphClient("private-token", session).collection("/me/events")
    assert len(events) == 2
    assert events[0]["etag"] == "tag"
    assert events[0]["transaction_id"] == "tx"
    for call in session.request.call_args_list:
        assert call.kwargs["allow_redirects"] is False
        assert call.kwargs["timeout"] == (10, 30)


def test_untrusted_nextlink_never_receives_token():
    session = Mock()
    session.request.return_value = response(
        {"value": [], "@odata.nextLink": "https://other.invalid/v1.0/me/events"}
    )
    with pytest.raises(OutlookError, match="unsafe_graph_url"):
        GraphClient("secret", session).collection("/me/events")
    assert session.request.call_count == 1


def test_cancelled_worker_never_starts_another_graph_request():
    session = Mock()
    client = GraphClient("synthetic", session, cancelled=lambda: True)
    with pytest.raises(OutlookError, match="cancelled"):
        client.collection("/me/events")
    session.request.assert_not_called()


def test_update_requires_revision_and_error_omits_response():
    session = Mock()
    client = GraphClient("secret", session)
    with pytest.raises(OutlookError, match="etag_required"):
        client.update("event", {}, None)
    session.request.return_value = response({"secret": "do not reveal"}, 403)
    with pytest.raises(GraphError) as error:
        client.update("event", {}, 'W/"revision"')
    assert str(error.value) == "graph_http_403"
    assert session.request.call_args.kwargs["headers"]["If-Match"] == 'W/"revision"'


def test_title_edit_does_not_replace_online_meeting_body():
    from calendar_app.infrastructure.outlook_sync.conversion import to_graph

    task = {
        "name": "Old",
        "deadline": "2026-10-05T10:00:00",
        "end_date": "2026-10-05T11:00:00",
        "description": "Teams meeting link",
        "location": "",
        "all_day": 0,
    }
    event = {**to_graph(task), "isOnlineMeeting": True}
    payload = GraphClient.edit_payload({**task, "name": "New"}, event, "Asia/Seoul")
    assert payload == {"subject": "New"}
    with pytest.raises(OutlookError, match="online_meeting_body_not_supported"):
        GraphClient.edit_payload({**task, "description": "Replaced"}, event, "Asia/Seoul")
