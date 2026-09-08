import pytest


@pytest.mark.parametrize("path", ["/api/patients", "/api/patients/pat_001",
    "/api/patients/pat_001/events", "/api/patients/pat_001/glance",
    "/api/patients/pat_001/tasks", "/api/events/evt_doc_0821/artifacts",
    "/api/events/evt_doc_0821/audit"])
def test_admin_denied_clinical_read(admin_client, path):
    assert admin_client.get(path).status_code == 403


def test_admin_identity_lookup_is_minimal(admin_client):
    response = admin_client.get('/api/admin/patient-identities')
    assert response.status_code == 200
    assert all(set(row) == {'patient_id', 'name'} for row in response.json())


def test_admin_cannot_read_clinically_visible_checkin(admin_client, patient_client, monkeypatch):
    monkeypatch.setenv('NANTINGALE_LLM_PROVIDER', 'mock')
    session_id = 'admin-denied-visible-checkin'
    assert patient_client.post('/api/patients/pat_001/check-ins',
                               json={'session_id': session_id}).status_code == 200
    response = patient_client.post(f'/api/check-ins/{session_id}/messages', json={
        'message_id': 'admin-sentinel-message', 'intent': 'answer',
        'text': 'I cannot breathe. CLINICAL_BODY_SENTINEL'})
    assert response.status_code == 200
    assert admin_client.get(f'/api/check-ins/{session_id}').status_code == 403
    for path in ('/api/admin/patient-identities', '/api/admin/users', '/api/admin/access-audit'):
        response = admin_client.get(path)
        assert response.status_code == 200
        assert 'CLINICAL_BODY_SENTINEL' not in response.text
