"""Интеграционные тесты: веб-приложение + PostgreSQL (отдельная база portagraph_test).

Запуск: python -m unittest discover tests
Адрес сервера берётся из TEST_DATABASE_URL (по умолчанию локальный postgres/postgres).
"""
import hashlib
import hmac
import json
import os
import pathlib
import re
import tempfile
import unittest

from portagraph import create_app
from portagraph.config import Settings
from portagraph.db import Connection, DatabaseError

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/portagraph_test")


def _reset_db():
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(TEST_DSN)
    name = parts.path.lstrip("/")
    admin = Connection(urlunsplit(parts._replace(path="/postgres")))
    try:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        admin.close()


def setUpModule():
    global APP, TMP
    try:
        _reset_db()
    except (DatabaseError, OSError) as e:  # pragma: no cover
        raise unittest.SkipTest(f"PostgreSQL недоступен: {e}")
    TMP = tempfile.TemporaryDirectory()
    settings = Settings.from_env(database_url=TEST_DSN, data_dir=pathlib.Path(TMP.name), secret_key="test-secret",
                                 demo_seed=True, testing=True, workers=1, public_url="http://test")
    APP = create_app(settings)


def tearDownModule():
    TMP.cleanup()


class Client:
    def __init__(self, email=None, password="portagraph"):
        self.c = APP.test_client()
        self.csrf = None
        if email:
            self.login(email, password)

    def _token(self):
        with self.c.session_transaction() as s:
            if "_csrf" not in s:
                s["_csrf"] = "tok-" + os.urandom(6).hex()
            return s["_csrf"]

    def login(self, email, password):
        r = self.c.post("/login", data={"email": email, "password": password, "_csrf": self._token()})
        assert r.status_code == 302, r.data

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, json_body=None, **kw):
        tok = self._token()
        if json_body is not None:
            return self.c.post(url, json=json_body, headers={"X-CSRF-Token": tok}, **kw)
        return self.c.post(url, data={**(data or {}), "_csrf": tok}, **kw)


OWNER, DEV, VIEWER = "anastasia@portagraph.local", "maxim@portagraph.local", "guest@portagraph.local"


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = Client(OWNER)
        cls.pid = cls.owner.get("/api/projects").get_json()[0]["id"]

    def test_01_pages_render(self):
        for path in ["/projects", f"/p/{self.pid}", f"/p/{self.pid}/repositories", f"/p/{self.pid}/runs", f"/p/{self.pid}/map",
                     f"/p/{self.pid}/graph", f"/p/{self.pid}/code", f"/p/{self.pid}/assistant", f"/p/{self.pid}/impact",
                     f"/p/{self.pid}/docs", f"/p/{self.pid}/settings"]:
            r = self.owner.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("PortaGraph", r.get_data(as_text=True))

    def test_02_anonymous_redirect_and_api_401(self):
        c = Client()
        self.assertEqual(c.get("/projects").status_code, 302)
        self.assertEqual(c.get(f"/api/projects/{self.pid}/graph/overview").status_code, 401)

    def test_03_csrf_required(self):
        r = self.owner.c.post(f"/api/projects/{self.pid}/assistant", json={"question": "x"})
        self.assertEqual(r.status_code, 400)

    def test_04_overview_graph(self):
        g = self.owner.get(f"/api/projects/{self.pid}/graph/overview").get_json()
        names = {n["label"] for n in g["nodes"]}
        for expected in ["auth-service", "order-service", "orders.created", "common-dto", "api.mailgun.net"]:
            self.assertIn(expected, names)
        ids = {n["label"]: n["id"] for n in g["nodes"]}
        pairs = {(e["source"], e["target"], e["type"]) for e in g["edges"]}
        self.assertIn((ids["order-service"], ids["auth-service"], "CALLS_HTTP"), pairs)
        self.assertIn((ids["billing-service"], ids["orders.created"], "CONSUMES"), pairs)
        low = [e for e in g["edges"] if e["confidence"] < 0.7]
        self.assertTrue(low, "в демо есть связь по переменной окружения с уверенностью 0,5")
        self.assertEqual([r["name"] for r in g["other_repositories"]], ["infra"])

    def test_05_node_detail_and_file(self):
        g = self.owner.get(f"/api/projects/{self.pid}/graph/overview").get_json()
        nid = next(n["id"] for n in g["nodes"] if n["label"] == "order-service")
        d = self.owner.get(f"/api/projects/{self.pid}/nodes/{nid}").get_json()
        self.assertTrue(d["outgoing"])
        ev = next(e for r in d["outgoing"] for e in r["evidence"])
        fid = d["file_ids"][f"{ev['repo']}/{ev['path']}"]
        r = self.owner.get(f"/p/{self.pid}/files/{fid}?l={ev['line']}")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="L-1"', r.get_data(as_text=True))

    def test_06_assistant(self):
        m = self.owner.post(f"/api/projects/{self.pid}/assistant", json_body={"question": "Кто использует auth-service?"}).get_json()
        self.assertIn("api-gateway", m["content"])
        self.assertIn("order-service", m["content"])
        self.assertGreaterEqual(m["confidence"], 0.7)
        self.assertTrue(m["citations"])
        m2 = self.owner.post(f"/api/projects/{self.pid}/assistant", json_body={"question": "квантовая телепортация", "session_id": m["session_id"]}).get_json()
        self.assertLess(m2["confidence"], 0.4)
        self.assertIn("неполных данных", m2["content"])
        self.assertEqual(m2["session_id"], m["session_id"])

    def test_07_impact(self):
        g = self.owner.get(f"/api/projects/{self.pid}/graph/overview").get_json()
        nid = next(n["id"] for n in g["nodes"] if n["label"] == "auth-service")
        r = self.owner.post(f"/api/projects/{self.pid}/impact", json_body={"node_ids": [nid], "depth": 1, "description": "test"}).get_json()
        self.assertEqual({c["name"] for c in r["components"]}, {"api-gateway", "order-service"})
        self.assertEqual(r["risk_level"], "HIGH")
        bad = self.owner.post(f"/api/projects/{self.pid}/impact", json_body={"node_ids": [nid], "depth": 9, "description": "x"})
        self.assertEqual(bad.status_code, 400)

    def test_08_docs_flow(self):
        r = self.owner.post(f"/p/{self.pid}/docs", data={"type": "ONBOARDING_GUIDE"})
        self.assertEqual(r.status_code, 302)
        doc_id = int(re.search(r"/docs/(\d+)", r.headers["Location"]).group(1))
        self.assertEqual(self.owner.post(f"/p/{self.pid}/docs/{doc_id}/approve").status_code, 302)
        exp = self.owner.get(f"/p/{self.pid}/docs/{doc_id}/export")
        self.assertIn("Онбординг", exp.get_data(as_text=True))
        self.assertIn("attachment", exp.headers["Content-Disposition"])

    def test_09_permissions(self):
        viewer, dev = Client(VIEWER), Client(DEV)
        self.assertEqual(viewer.post(f"/api/projects/{self.pid}/assistant", json_body={"question": "x"}).status_code, 403)
        self.assertEqual(dev.post(f"/api/projects/{self.pid}/analysis", json_body={}).status_code, 403)
        g = dev.get(f"/api/projects/{self.pid}/graph/overview").get_json()
        eid = next(e["edge_id"] for e in g["edges"] if e["edge_id"])
        self.assertEqual(dev.post(f"/api/projects/{self.pid}/verifications", json_body={"subject": "EDGE", "id": eid, "decision": "REJECT"}).status_code, 403)
        # чужой проект не виден
        other = Client()
        other.post("/register", data={"email": "x@y.ru", "full_name": "Посторонний", "password": "password1", "password2": "password1"})
        self.assertEqual(other.get(f"/api/projects/{self.pid}/graph/overview").status_code, 404)
        self.assertEqual(other.get(f"/p/{self.pid}").status_code, 404)

    def test_10_verification_survives_reanalysis(self):
        g = self.owner.get(f"/api/projects/{self.pid}/graph/overview").get_json()
        low = next(e for e in g["edges"] if e["confidence"] < 0.7 and e["edge_id"])
        r = self.owner.post(f"/api/projects/{self.pid}/verifications", json_body={"subject": "EDGE", "id": low["edge_id"], "decision": "REJECT"})
        self.assertEqual(r.status_code, 200)
        pipe = APP.extensions["portagraph"]["pipeline"]
        run = pipe.enqueue(self.pid, "MANUAL", None, wait=True)
        ctx = APP.extensions["portagraph"]["ctx"]
        self.assertEqual(ctx.db.scalar("SELECT status FROM analysis_runs WHERE id = %s", run["id"]), "COMPLETED")
        g2 = self.owner.get(f"/api/projects/{self.pid}/graph/overview").get_json()
        self.assertFalse([e for e in g2["edges"] if e["confidence"] < 0.7 and not e["verified"]])
        stats = ctx.db.scalar("SELECT stats FROM analysis_runs WHERE id = %s", run["id"])
        self.assertEqual(stats["files_indexed"], 0, "повторный анализ инкрементальный")

    def test_11_webhook(self):
        ctx = APP.extensions["portagraph"]["ctx"]
        repo = ctx.db.one("SELECT id, webhook_secret FROM repositories WHERE project_id = %s ORDER BY id LIMIT 1", self.pid)
        body = json.dumps({"ref": "refs/heads/main", "after": "abc"}).encode()
        sig = "sha256=" + hmac.new(repo["webhook_secret"].encode(), body, hashlib.sha256).hexdigest()
        c = APP.test_client()
        bad = c.post(f"/hooks/repositories/{repo['id']}", data=body, headers={"X-Hub-Signature-256": "sha256=00", "X-GitHub-Event": "push"})
        self.assertEqual(bad.status_code, 403)
        h = {"X-Hub-Signature-256": sig, "X-GitHub-Event": "push", "X-GitHub-Delivery": "d-1", "Content-Type": "application/json"}
        first = c.post(f"/hooks/repositories/{repo['id']}", data=body, headers=h).get_json()
        self.assertIn(first["status"], ("accepted", "queued_later"))
        second = c.post(f"/hooks/repositories/{repo['id']}", data=body, headers=h).get_json()
        self.assertEqual(second["status"], "duplicate")
        # дождаться фонового анализа, чтобы не мешать остальным тестам
        import time
        for _ in range(100):
            if not ctx.db.scalar("SELECT count(*) FROM analysis_runs WHERE project_id = %s AND status NOT IN ('COMPLETED','FAILED','CANCELLED')", self.pid):
                break
            time.sleep(0.1)

    def test_12_zip_upload_with_secret(self):
        import io
        import zipfile
        r = self.owner.post("/projects", data={"name": "ZIP-проект"})
        pid = int(re.search(r"/p/(\d+)/", r.headers["Location"]).group(1))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("svc/app.py", "from fastapi import FastAPI\napp = FastAPI()\nAPI_KEY = 'sk_live_1234567890abcdef'\n@app.get('/ping')\ndef ping():\n    return 1\n")
            z.writestr("svc/Dockerfile", "FROM python:3.12\nCMD uvicorn app:app\n")
            z.writestr("svc/.env", "PASSWORD=supersecret")
        evil = io.BytesIO()
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("a.txt", "x")
            z.writestr("../evil.txt", "x")
        evil.seek(0)
        ctx = APP.extensions["portagraph"]["ctx"]
        self.owner.c.post(f"/p/{pid}/repositories/zip", data={"archive": (evil, "evil.zip"), "_csrf": self.owner._token()},
                          content_type="multipart/form-data")
        self.assertEqual(ctx.db.scalar("SELECT count(*) FROM repositories WHERE project_id = %s", pid), 0, "zip-slip отклонён")
        buf.seek(0)
        r = self.owner.c.post(f"/p/{pid}/repositories/zip", data={"archive": (buf, "svc.zip"), "_csrf": self.owner._token()},
                              content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        pipe = APP.extensions["portagraph"]["pipeline"]
        pipe.enqueue(pid, "MANUAL", None, wait=True)
        files = ctx.db.all("SELECT f.path, f.content FROM source_files f JOIN repositories r ON r.id = f.repository_id WHERE r.project_id = %s", pid)
        paths = {f["path"] for f in files}
        self.assertNotIn(".env", paths)
        app_py = next(f["content"] for f in files if f["path"] == "app.py")
        self.assertNotIn("sk_live_1234567890abcdef", app_py)
        role = ctx.db.scalar("SELECT detected_role FROM repositories WHERE project_id = %s", pid)
        self.assertEqual(role, "SERVICE")


if __name__ == "__main__":
    unittest.main()
