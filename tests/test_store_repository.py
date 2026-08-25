import json
from pathlib import Path

from core import store_repository as repo


def test_store_roundtrip_local_json(tmp_path, monkeypatch):
    target = tmp_path / 'stores.json'
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setenv('STORE_CONFIG_FILE', str(target))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-long-enough')

    key = repo.upsert_managed_store('Test Store', 'Test Mağaza', 'https://abc.myshopify.com/', 'shpat_secret123', '2026-04')
    assert key == 'test-store'
    stores = repo.list_managed_stores()
    assert len(stores) == 1
    assert stores[0]['domain'] == 'abc.myshopify.com'
    assert stores[0]['token'] == 'shpat_secret123'

    raw = target.read_text(encoding='utf-8')
    assert 'shpat_secret123' not in raw

    repo.upsert_managed_store('test-store', 'Yeni İsim', 'abc.myshopify.com', '', '2026-04')
    stores = repo.list_managed_stores()
    assert stores[0]['name'] == 'Yeni İsim'
    assert stores[0]['token'] == 'shpat_secret123'

    repo.delete_managed_store('test-store')
    assert repo.list_managed_stores() == []


def test_vercel_without_database_is_read_only(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('VERCEL', '1')
    assert repo.writes_are_persistent() is False
