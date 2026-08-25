import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.fernet import Fernet


def _fernet():
    secret = os.getenv('SECRET_KEY', 'change-this-secret-key').encode('utf-8')
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_token(token: str) -> str:
    return _fernet().encrypt((token or '').encode('utf-8')).decode('utf-8')


def decrypt_token(token_enc: str) -> str:
    if not token_enc:
        return ''
    try:
        return _fernet().decrypt(token_enc.encode('utf-8')).decode('utf-8')
    except Exception:
        return ''


def normalize_domain(domain: str) -> str:
    value = (domain or '').strip().lower()
    value = re.sub(r'^https?://', '', value)
    return value.split('/')[0].strip()


def normalize_key(value: str) -> str:
    value = (value or '').strip().lower()
    value = re.sub(r'[^a-z0-9_-]+', '-', value).strip('-_')
    return value[:60]


def is_vercel() -> bool:
    return str(os.getenv('VERCEL', '')).lower() in ('1', 'true', 'yes')


def backend_name() -> str:
    return 'PostgreSQL' if os.getenv('DATABASE_URL', '').strip() else 'Yerel şifreli JSON'


def writes_are_persistent() -> bool:
    return bool(os.getenv('DATABASE_URL', '').strip()) or not is_vercel()


def _file_path() -> Path:
    custom = os.getenv('STORE_CONFIG_FILE', '').strip()
    return Path(custom) if custom else Path(__file__).resolve().parent.parent / 'data' / 'stores.json'


def _ensure_pg_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS shopify_tools_stores (
        store_key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        domain TEXT NOT NULL,
        token_enc TEXT NOT NULL,
        api_version TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )''')


def _pg_connect():
    import psycopg
    return psycopg.connect(os.environ['DATABASE_URL'])


def list_managed_stores() -> List[Dict]:
    if os.getenv('DATABASE_URL', '').strip():
        with _pg_connect() as conn:
            _ensure_pg_table(conn)
            rows = conn.execute('SELECT store_key,name,domain,token_enc,api_version,active FROM shopify_tools_stores ORDER BY name').fetchall()
        return [
            {'key': r[0], 'name': r[1], 'domain': r[2], 'token': decrypt_token(r[3]), 'api_version': r[4], 'active': bool(r[5]), 'source': 'panel'}
            for r in rows
        ]
    path = _file_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return []
    out = []
    for item in raw if isinstance(raw, list) else []:
        out.append({
            'key': item.get('key', ''), 'name': item.get('name', ''), 'domain': item.get('domain', ''),
            'token': decrypt_token(item.get('token_enc', '')), 'api_version': item.get('api_version', '2026-04'),
            'active': bool(item.get('active', True)), 'source': 'panel'
        })
    return out


def get_managed_store(key: str) -> Optional[Dict]:
    return next((s for s in list_managed_stores() if s.get('key') == key), None)


def upsert_managed_store(key: str, name: str, domain: str, token: str, api_version: str = '2026-04', active: bool = True):
    if not writes_are_persistent():
        raise RuntimeError('Vercel üzerinde kalıcı mağaza kaydı için DATABASE_URL tanımlanmalı.')
    key = normalize_key(key or name or domain.split('.')[0])
    domain = normalize_domain(domain)
    if not key or not name.strip() or not domain:
        raise ValueError('Mağaza adı, anahtar ve domain zorunludur.')
    if not token:
        existing = get_managed_store(key)
        token = existing.get('token', '') if existing else ''
    if not token:
        raise ValueError('Access Token zorunludur.')
    token_enc = encrypt_token(token)
    if os.getenv('DATABASE_URL', '').strip():
        with _pg_connect() as conn:
            _ensure_pg_table(conn)
            conn.execute('''INSERT INTO shopify_tools_stores(store_key,name,domain,token_enc,api_version,active,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,NOW())
                ON CONFLICT(store_key) DO UPDATE SET name=EXCLUDED.name,domain=EXCLUDED.domain,
                  token_enc=EXCLUDED.token_enc,api_version=EXCLUDED.api_version,active=EXCLUDED.active,updated_at=NOW()''',
                (key, name.strip(), domain, token_enc, api_version.strip() or '2026-04', bool(active)))
        return key
    path = _file_path(); path.parent.mkdir(parents=True, exist_ok=True)
    items = []
    if path.exists():
        try: items = json.loads(path.read_text(encoding='utf-8'))
        except Exception: items = []
    row = {'key': key, 'name': name.strip(), 'domain': domain, 'token_enc': token_enc, 'api_version': api_version.strip() or '2026-04', 'active': bool(active)}
    items = [x for x in items if x.get('key') != key] + [row]
    items.sort(key=lambda x: x.get('name', '').lower())
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    return key


def delete_managed_store(key: str):
    if not writes_are_persistent():
        raise RuntimeError('Vercel üzerinde kalıcı mağaza kaydı için DATABASE_URL tanımlanmalı.')
    if os.getenv('DATABASE_URL', '').strip():
        with _pg_connect() as conn:
            _ensure_pg_table(conn)
            conn.execute('DELETE FROM shopify_tools_stores WHERE store_key=%s', (key,))
        return
    path = _file_path()
    if not path.exists():
        return
    try: items = json.loads(path.read_text(encoding='utf-8'))
    except Exception: items = []
    items = [x for x in items if x.get('key') != key]
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
