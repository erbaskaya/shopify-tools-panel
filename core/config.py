import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core.store_repository import list_managed_stores


@dataclass(frozen=True)
class StoreConfig:
    key: str
    name: str
    domain: str
    token: str
    api_version: str = '2026-04'
    source: str = 'env'

    @property
    def base_rest_url(self): return f'https://{self.domain}/admin/api/{self.api_version}'
    @property
    def graphql_url(self): return f'https://{self.domain}/admin/api/{self.api_version}/graphql.json'
    @property
    def headers(self):
        return {'X-Shopify-Access-Token': self.token, 'Content-Type': 'application/json', 'Accept': 'application/json'}


class Settings:
    def __init__(self):
        self.API_VERSION = os.getenv('API_VERSION', '2026-04').strip()
        self.SHOP_DOMAIN = os.getenv('SHOP_DOMAIN', '').strip()
        self.SHOPIFY_ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN', '').strip()
        self.SHOPIFY_STORES_JSON = os.getenv('SHOPIFY_STORES_JSON', '').strip()
        self.PANEL_PASSWORD = os.getenv('PANEL_PASSWORD', '').strip()
        self.SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-secret-key').strip()
        self.COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'true').strip().lower() not in ('0','false','no','off')

    def _env_stores(self) -> Dict[str, StoreConfig]:
        stores = {}
        if self.SHOPIFY_STORES_JSON:
            try:
                raw = json.loads(self.SHOPIFY_STORES_JSON)
                if isinstance(raw, dict): raw = raw.get('stores', [])
                for idx, item in enumerate(raw if isinstance(raw, list) else [], 1):
                    domain = str(item.get('domain') or item.get('shop_domain') or '').strip()
                    token = str(item.get('token') or item.get('access_token') or '').strip()
                    if domain and token:
                        key = str(item.get('key') or item.get('id') or f'store{idx}').strip()
                        stores[key] = StoreConfig(key, str(item.get('name') or domain).strip(), domain, token, str(item.get('api_version') or self.API_VERSION), 'env')
            except Exception:
                pass
        if self.SHOP_DOMAIN and self.SHOPIFY_ACCESS_TOKEN and 'default' not in stores:
            stores['default'] = StoreConfig('default', os.getenv('SHOP_NAME', self.SHOP_DOMAIN).strip() or self.SHOP_DOMAIN, self.SHOP_DOMAIN, self.SHOPIFY_ACCESS_TOKEN, self.API_VERSION, 'env')
        return stores

    def _all_stores(self) -> Dict[str, StoreConfig]:
        stores = self._env_stores()
        try:
            for item in list_managed_stores():
                if item.get('active', True) and item.get('domain') and item.get('token'):
                    stores[item['key']] = StoreConfig(item['key'], item['name'], item['domain'], item['token'], item.get('api_version') or self.API_VERSION, 'panel')
        except Exception:
            pass
        return stores

    @property
    def stores(self) -> List[StoreConfig]: return list(self._all_stores().values())
    def get_store(self, key: Optional[str] = None) -> Optional[StoreConfig]:
        stores = self._all_stores()
        return stores.get(key) if key and key in stores else next(iter(stores.values()), None)
    @property
    def base_rest_url(self):
        s = self.get_store(); return s.base_rest_url if s else ''
    @property
    def graphql_url(self):
        s = self.get_store(); return s.graphql_url if s else ''
    @property
    def headers(self):
        s = self.get_store(); return s.headers if s else {'Content-Type':'application/json','Accept':'application/json'}


settings = Settings()
def get_stores(): return settings.stores
def get_store(key=None): return settings.get_store(key)
def get_env_stores(): return list(settings._env_stores().values())
def check_config():
    missing = []
    if not settings.stores: missing.append('En az bir Shopify mağazası')
    if not settings.PANEL_PASSWORD: missing.append('PANEL_PASSWORD')
    if not settings.SECRET_KEY or settings.SECRET_KEY == 'change-this-secret-key': missing.append('SECRET_KEY')
    return missing
