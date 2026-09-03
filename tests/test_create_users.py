"""Local-only tests for scripts/create_users.py.

Nothing here touches Supabase or the network -- every Supabase interaction is
a hand-rolled fake object, and getpass is monkeypatched so no real prompt
ever blocks the test run. See docs/planning/PHASE4.md, decisions D5 / D5a.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import create_users as cu

REPO_ROOT = Path(__file__).resolve().parent.parent


class _FakeUser:
    def __init__(self, id, email, app_metadata):
        self.id = id
        self.email = email
        self.app_metadata = app_metadata


class _FakeAdmin:
    def __init__(self, existing_users=None):
        self._users = list(existing_users or [])
        self.create_calls = []
        self.update_calls = []

    def list_users(self):
        return list(self._users)

    def create_user(self, attributes):
        user = _FakeUser(
            id=f"new-{len(self._users) + 1}",
            email=attributes["email"],
            app_metadata=attributes["app_metadata"],
        )
        self._users.append(user)
        self.create_calls.append(attributes)
        return SimpleNamespace(user=user)

    def update_user_by_id(self, uid, attributes):
        self.update_calls.append((uid, attributes))
        for user in self._users:
            if user.id == uid:
                user.app_metadata = attributes["app_metadata"]
                return SimpleNamespace(user=user)
        raise AssertionError(f"no user with id {uid}")


class _FakeClient:
    def __init__(self, existing_users=None):
        self.auth = SimpleNamespace(admin=_FakeAdmin(existing_users))


def test_script_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", "scripts/create_users.py"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_make_client_exits_5_without_credentials(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setattr(cu, "load_dotenv", lambda: None)
    with pytest.raises(SystemExit) as exc:
        cu.make_client()
    assert exc.value.code == 5


def test_find_user_by_email_returns_none_when_absent():
    client = _FakeClient(existing_users=[])
    assert cu.find_user_by_email(client, "nobody@funneliq.example.com") is None


def test_find_user_by_email_finds_existing():
    existing = _FakeUser(
        "u1", "demo-northbound@funneliq.example.com", {"organization": "northbound"}
    )
    client = _FakeClient(existing_users=[existing])
    found = cu.find_user_by_email(client, "demo-northbound@funneliq.example.com")
    assert found is existing


def test_upsert_creates_when_absent():
    client = _FakeClient(existing_users=[])
    result = cu.upsert_demo_user(
        client,
        "demo-northbound@funneliq.example.com",
        {"organization": "northbound", "role": "team_member"},
        "s3cret-pw",
    )
    assert result["action"] == "created"
    assert result["email"] == "demo-northbound@funneliq.example.com"
    assert result["app_metadata"] == {"organization": "northbound", "role": "team_member"}
    assert "password" not in result  # never returned/printed
    [call] = client.auth.admin.create_calls
    assert call["email_confirm"] is True
    assert call["password"] == "s3cret-pw"


def test_upsert_updates_app_metadata_only_when_present():
    existing = _FakeUser(
        "u1", "demo-noorg@funneliq.example.com", {"role": "team_member", "stale": True}
    )
    client = _FakeClient(existing_users=[existing])
    result = cu.upsert_demo_user(
        client, "demo-noorg@funneliq.example.com", {"role": "team_member"}, "irrelevant-pw"
    )
    assert result["action"].startswith("updated")
    assert client.auth.admin.create_calls == []  # never recreated
    [(uid, attrs)] = client.auth.admin.update_calls
    assert uid == "u1"
    assert attrs == {"app_metadata": {"role": "team_member"}}
    assert "password" not in attrs  # existing password is never touched


def test_main_never_prints_the_password(monkeypatch, capsys):
    fake_client = _FakeClient(existing_users=[])
    monkeypatch.setattr(cu, "make_client", lambda: fake_client)
    sentinel_password = "sentinel-pw-should-never-appear"
    monkeypatch.setattr(cu.getpass, "getpass", lambda prompt="": sentinel_password)

    cu.main()

    captured = capsys.readouterr()
    assert sentinel_password not in captured.out
    assert sentinel_password not in captured.err
    assert "demo-northbound@funneliq.example.com" in captured.out
    assert "demo-noorg@funneliq.example.com" in captured.out


def test_main_exits_6_on_empty_password(monkeypatch):
    fake_client = _FakeClient(existing_users=[])
    monkeypatch.setattr(cu, "make_client", lambda: fake_client)
    monkeypatch.setattr(cu.getpass, "getpass", lambda prompt="": "")
    with pytest.raises(SystemExit) as exc:
        cu.main()
    assert exc.value.code == 6
