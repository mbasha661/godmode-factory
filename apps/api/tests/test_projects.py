def test_create_and_get_project(client_a):
    r = client_a.post("/api/projects", json={
        "name": "Fleet app", "description": "vehicles and drivers", "project_type": "fullstack",
    })
    assert r.status_code == 201, r.text
    proj = r.json()
    assert proj["name"] == "Fleet app"
    assert proj["status"] == "draft"

    r2 = client_a.get(f"/api/projects/{proj['id']}")
    assert r2.status_code == 200
    assert r2.json()["id"] == proj["id"]


def test_list_only_own_projects(client_a, client_b):
    client_a.post("/api/projects", json={"name": "A project", "project_type": "web"})
    r = client_b.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_cannot_read_other_users_project(client_a, client_b):
    r = client_a.post("/api/projects", json={"name": "Private", "project_type": "api"})
    pid = r.json()["id"]
    r2 = client_b.get(f"/api/projects/{pid}")
    assert r2.status_code == 404  # indistinguishable from missing: no existence leak


def test_cannot_update_other_users_project(client_a, client_b):
    pid = client_a.post("/api/projects", json={"name": "Mine", "project_type": "web"}).json()["id"]
    r = client_b.patch(f"/api/projects/{pid}", json={"name": "Hijacked"})
    assert r.status_code == 404


def test_soft_delete_hides_project(client_a):
    pid = client_a.post("/api/projects", json={"name": "Temp", "project_type": "web"}).json()["id"]
    assert client_a.delete(f"/api/projects/{pid}").status_code == 204
    assert client_a.get(f"/api/projects/{pid}").status_code == 404
    ids = [p["id"] for p in client_a.get("/api/projects").json()]
    assert pid not in ids


def test_validation_rejects_bad_type(client_a):
    r = client_a.post("/api/projects", json={"name": "X", "project_type": "spaceship"})
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["code"] == "validation_error"


def test_validation_rejects_empty_name(client_a):
    r = client_a.post("/api/projects", json={"name": "", "project_type": "web"})
    assert r.status_code == 422
