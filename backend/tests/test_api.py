"""后端冒烟测试：健康、鉴权拦截、带密钥问答、管理员统计。
不依赖外部 LLM / 完整知识库（无 Key 时走检索增强直答降级）。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

DEMO_KEY = "srm_dev_demo_key"
API = "/api"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_requires_auth(client):
    r = client.post(f"{API}/chat/sync", json={"message": "测试"})
    assert r.status_code in (401, 403)


def test_chat_with_demo_key(client):
    r = client.post(
        f"{API}/chat/sync",
        json={"message": "如何注册成为青山利康供应商？"},
        headers={"X-API-Key": DEMO_KEY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]
    assert "session_id" in body


def test_login_and_admin_stats(client):
    r = client.post(
        f"{API}/auth/login",
        json={"username": "admin", "password": "Admin@123"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert token

    s = client.get(f"{API}/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert s.status_code == 200
    data = s.json()
    assert "kb_chunks" in data
    assert "conversations" in data


def test_admin_stats_forbidden_for_supplier_key(client):
    # 服务级 demo key 非 admin 角色，访问管理接口应被拒
    s = client.get(f"{API}/admin/stats", headers={"X-API-Key": DEMO_KEY})
    assert s.status_code in (401, 403)
