def test_health(client_a):
    r = client_a.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_system_status_reports_limits(client_a):
    r = client_a.get("/api/system/status")
    assert r.status_code == 200
    body = r.json()
    assert body["limits"]["max_concurrent_ai_tasks"] == 1
    assert body["limits"]["max_repair_attempts"] == 2
    assert body["limits"]["max_tasks_per_run"] == 30
    # honestly reports unconfigured backends
    assert body["supabase_configured"] is False
    assert body["ai_provider_configured"] is False
