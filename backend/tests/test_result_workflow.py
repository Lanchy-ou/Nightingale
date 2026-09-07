import base64
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select
from app.models import Task
from app.result_models import TestReport as Report, TestOrder as Order


@pytest.fixture(autouse=True)
def feature(monkeypatch):
    monkeypatch.setenv("NANTINGALE_TEST_RESULTS_ENABLED", "true")
    monkeypatch.setenv("NANTINGALE_NOTIFICATIONS_ENABLED", "false")


def create(client):
    r = client.post("/api/events/evt_doc_0821/test-orders", json={"idempotency_key": "order",
        "title": "Synthetic blood test", "reason": "Synthetic follow-up", "expected_at": "2026-09-10T12:00:00+08:00"})
    assert r.status_code == 200, r.text
    return r.json()


def upload(client, order, key="report", content=b"%PDF-1.4\nSynthetic report\n%%EOF"):
    r = client.post(f"/api/test-orders/{order['order_id']}/reports", json={"idempotency_key": key,
        "expected_revision": order["revision"], "filename": "synthetic.pdf", "content_type": "application/pdf",
        "file_base64": base64.b64encode(content).decode(), "issued_at": "2026-09-05T10:00:00Z", "external_source": "Synthetic laboratory"})
    assert r.status_code == 200, r.text
    return client.get(f"/api/test-orders/{order['order_id']}").json()


def test_offline_closure_revision_and_download(clinician_client, staff_client, patient_client, admin_client, db_session):
    c = clinician_client
    order = create(c)
    order = upload(staff_client, order)
    assert order["stage"] == "waiting_review"
    report_id = order["current_report_id"]
    body = {"idempotency_key": "review", "expected_revision": order["revision"], "conclusion": "Synthetic clinician conclusion", "outcome": "no_action"}
    assert staff_client.post(f"/api/test-reports/{report_id}/reviews", json=body).status_code == 403
    for denied in (patient_client, admin_client):
        assert denied.get(f"/api/test-reports/{report_id}/file").status_code == 403
    download = c.get(f"/api/test-reports/{report_id}/file")
    assert download.status_code == 200 and download.headers["cache-control"] == "no-store, private"
    assert download.content == b"%PDF-1.4\nSynthetic report\n%%EOF"
    task = db_session.scalar(select(Task).where(Task.task_kind == "result_review"))
    assert c.post(f"/api/tasks/{task.task_id}/transition", json={"expected_status": "open", "status": "completed"}).status_code == 409
    assert c.post(f"/api/test-reports/{report_id}/reviews", json=body).status_code == 200
    order = c.get(f"/api/test-orders/{order['order_id']}").json()
    for outcome, expected in (("not_reached", "waiting_communication"), ("delivered", "completed")):
        result = staff_client.post(f"/api/test-orders/{order['order_id']}/communications", json={"idempotency_key": outcome,
            "expected_revision": order["revision"], "review_id": order["current_review_id"], "method": "phone",
            "outcome": outcome, "performed_at": datetime.now(timezone.utc).isoformat()})
        assert result.status_code == 200, result.text
        assert result.json()["stage"] == expected
        order = c.get(f"/api/test-orders/{order['order_id']}").json()
    order = upload(c, order, "revision", b"%PDF-1.4\nCorrected synthetic report\n%%EOF")
    assert order["stage"] == "waiting_review" and len(order["reports"]) == 2
    assert len(order["reviews"]) == 1 and len(order["communications"]) == 2
    duplicate = upload(c, order, "old-file-retry")
    assert len(duplicate["reports"]) == 2 and duplicate["revision"] == order["revision"]
    assert c.get(f"/api/test-reports/{report_id}/file").content == download.content


def test_idempotency_and_stale_review(clinician_client):
    c = clinician_client
    first = create(c)
    assert create(c) == first
    order = upload(c, first)
    duplicate = upload(c, first, "report")
    assert duplicate["revision"] == order["revision"]
    assert len(duplicate["reports"]) == 1
    bad = c.post(f"/api/test-reports/{order['current_report_id']}/reviews", json={"idempotency_key": "stale",
        "expected_revision": 1, "conclusion": "synthetic", "outcome": "no_action"})
    assert bad.status_code == 409


def test_scope_and_required_followup(clinician_client, client):
    order = upload(clinician_client, create(clinician_client))
    other = client.get(f"/api/test-orders/{order['order_id']}", headers={"X-User-Id": "usr_clinician_02"})
    assert other.status_code == 404
    r = clinician_client.post(f"/api/test-reports/{order['current_report_id']}/reviews", json={"idempotency_key": "action",
        "expected_revision": order["revision"], "conclusion": "Synthetic follow-up", "outcome": "monitor"})
    assert r.status_code == 422


def test_portal_closure_and_old_guidance_withdrawal(clinician_client, patient_client, admin_client):
    c = clinician_client
    assert c.get('/api/test-results/team').status_code == 200
    assert admin_client.get('/api/admin/notification-settings').status_code == 200
    assert admin_client.get('/api/admin/notification-jobs').status_code == 200
    order = upload(c, create(c))
    r = c.post(f"/api/test-reports/{order['current_report_id']}/reviews", json={"idempotency_key": "review",
        "expected_revision": order['revision'], "conclusion": "Synthetic no further action", "outcome": "no_action"})
    assert r.status_code == 200
    order = c.get(f"/api/test-orders/{order['order_id']}").json()
    draft = c.post(f"/api/events/{order['result_event_id']}/notes", json={"artifact_type": "patient_instruction",
        "content": {"instruction": "Synthetic reviewed guidance"}})
    assert draft.status_code == 200, draft.text
    artifact_id = draft.json()['artifact_id']
    assert c.post(f'/api/patient-instructions/{artifact_id}/publish', json={"expected_state": "draft"}).status_code == 200
    order = c.get(f"/api/test-orders/{order['order_id']}").json()
    communication = c.post(f"/api/test-orders/{order['order_id']}/communications", json={"idempotency_key": "portal",
        "expected_revision": order['revision'], "review_id": order['current_review_id'], "method": "portal", "outcome": "delivered",
        "performed_at": datetime.now(timezone.utc).isoformat(), "publication_id": order['publications'][0]['publication_id']})
    assert communication.status_code == 200, communication.text
    assert communication.json()['stage'] == 'completed'
    assert artifact_id in str(patient_client.get('/api/patients/pat_001/patient-view').json())
    # A publication withdrawal must reopen the existing communication Task atomically.
    withdrawn = c.post(f'/api/patient-instructions/{artifact_id}/withdraw', json={"expected_state": "published", "reason_code": "entered_in_error"})
    assert withdrawn.status_code == 200, withdrawn.text
    reopened = c.get(f"/api/test-orders/{order['order_id']}").json()
    assert reopened['stage'] == 'waiting_communication'
    assert any(t['task_kind'] == 'result_communication' and t['status'] == 'open' for t in c.get('/api/patients/pat_001/tasks').json())
    order = upload(c, reopened, 'corrected', b'%PDF-1.4\nSynthetic correction\n%%EOF')
    assert artifact_id not in str(patient_client.get('/api/patients/pat_001/patient-view').json())
    assert c.get(f'/api/patient-instructions/{artifact_id}/publication').json()['state'] == 'withdrawn'
    assert admin_client.get(f"/api/events/{order['result_event_id']}/artifacts").json() == [
        row for row in admin_client.get(f"/api/events/{order['result_event_id']}/artifacts").json() if row['artifact_type'] == 'patient_instruction']


def test_two_doctors_cannot_both_review_stale_version(clinician_client):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app
    order = upload(clinician_client, create(clinician_client))
    def submit(user):
        with TestClient(app, headers={"X-User-Id": user}) as client:
            return client.post(f"/api/test-reports/{order['current_report_id']}/reviews", json={"idempotency_key": user,
                "expected_revision": order['revision'], "conclusion": "Synthetic concurrent review", "outcome": "no_action"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(submit, ['usr_clinician_01', 'usr_clinician_03']))
    assert sorted(codes) == [200, 409]
    result = clinician_client.get(f"/api/test-orders/{order['order_id']}").json()
    assert len(result['reviews']) == 1


def test_report_content_excluded_from_copilot_and_flag_rollback(clinician_client, db_session, monkeypatch):
    from app.copilot import _event_quote_rows
    from app.models import Event
    order = upload(clinician_client, create(clinician_client))
    assert _event_quote_rows(db_session, db_session.get(Event, order['result_event_id'])) == []
    monkeypatch.setenv('NANTINGALE_TEST_RESULTS_ENABLED', 'false')
    assert clinician_client.get(f"/api/test-reports/{order['current_report_id']}/file").status_code == 200
    assert clinician_client.patch(f"/api/test-orders/{order['order_id']}", json={"idempotency_key": 'disabled',
        "expected_revision": order['revision'], "cancel_reason": 'Synthetic rollback'}).status_code == 409


def test_result_closed_but_followup_remains_active(clinician_client, db_session):
    from app.models import CareWorkflow
    c = clinician_client
    order = upload(c, create(c))
    response = c.post(f"/api/test-reports/{order['current_report_id']}/reviews", json={"idempotency_key": "followup",
        "expected_revision": order['revision'], "conclusion": "Synthetic monitoring", "outcome": "monitor",
        "follow_up_title": "Synthetic follow-up", "follow_up_owner_id": "usr_clinician_01", "follow_up_due_at": "2026-09-10T12:00:00+08:00"})
    assert response.status_code == 200, response.text
    order = c.get(f"/api/test-orders/{order['order_id']}").json()
    response = c.post(f"/api/test-orders/{order['order_id']}/communications", json={"idempotency_key": "communicate",
        "expected_revision": order['revision'], "review_id": order['current_review_id'], "method": "phone", "outcome": "delivered",
        "performed_at": datetime.now(timezone.utc).isoformat()})
    assert response.json()['stage'] == 'completed'
    assert db_session.get(CareWorkflow, order['workflow_id']).status == 'active'
    task_id = order['reviews'][0]['follow_up_task_id']
    for before, after in [('open','in_progress'),('in_progress','reported_done'),('reported_done','completed')]:
        response = c.post(f'/api/tasks/{task_id}/transition', json={"expected_status": before, "status": after})
        assert response.status_code == 200, response.text
    db_session.expire_all()
    assert db_session.get(CareWorkflow, order['workflow_id']).status == 'completed'


def test_pdf_size_boundary_and_signature(clinician_client):
    order = create(clinician_client)
    content = b'%PDF-1.4\n' + b' ' * (10 * 1024 * 1024 - 15) + b'\n%%EOF'
    assert len(content) == 10 * 1024 * 1024
    result = upload(clinician_client, order, content=content)
    assert result['stage'] == 'waiting_review'


def test_report_revision_racing_review_cannot_close_wrong_version(clinician_client):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app
    order = upload(clinician_client, create(clinician_client))
    def submit(kind):
        with TestClient(app, headers={"X-User-Id": 'usr_clinician_01'}) as client:
            body = {"idempotency_key": kind, "expected_revision": order['revision']}
            if kind == 'review':
                return client.post(f"/api/test-reports/{order['current_report_id']}/reviews", json=body | {"conclusion": "Synthetic review", "outcome": "no_action"}).status_code
            return client.post(f"/api/test-orders/{order['order_id']}/reports", json=body | {"filename": "correction.pdf", "content_type": "application/pdf",
                "file_base64": base64.b64encode(b'%PDF-1.4\nSynthetic race correction\n%%EOF').decode(), "external_source": "QA", "issued_at": "2026-09-05T12:00:00Z"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, ['review', 'correction'])) == [200, 409]
    final = clinician_client.get(f"/api/test-orders/{order['order_id']}").json()
    assert final['stage'] in {'waiting_review', 'waiting_communication'}
