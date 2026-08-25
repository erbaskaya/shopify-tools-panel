import json
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StoreConfig:
    key: str
    name: str
    domain: str
    token: str
    api_version: str = "2026-04"

    @property
    def base_rest_url(self):
        return f"https://{self.domain}/admin/api/{self.api_version}"

    @property
    def graphql_url(self):
        return f"https://{self.domain}/admin/api/{self.api_version}/graphql.json"

    @property
    def headers(self):
        return {
            "X-Shopify-Access-Token": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


class Settings:
    def __init__(self):
        self.API_VERSION = os.getenv("API_VERSION", "2026-04").strip()
        self.SHOP_DOMAIN = os.getenv("SHOP_DOMAIN", "").strip()
        self.SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
        self.SHOPIFY_STORES_JSON = os.getenv("SHOPIFY_STORES_JSON", "").strip()
        self.PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "").strip()
        self.SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key").strip()
        self.COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() not in (
            "0", "false", "no", "off"
        )
        self._stores = self._load_stores()

        # Eski tek mağaza ayarlarını kullanan mevcut araçlar bozulmasın.
        if (not self.SHOP_DOMAIN or not self.SHOPIFY_ACCESS_TOKEN) and self._stores:
            first = next(iter(self._stores.values()))
            self.SHOP_DOMAIN = first.domain
            self.SHOPIFY_ACCESS_TOKEN = first.token
            self.API_VERSION = first.api_version

    def _load_stores(self) -> Dict[str, StoreConfig]:
        stores: Dict[str, StoreConfig] = {}

        if self.SHOPIFY_STORES_JSON:
            try:
                raw = json.loads(self.SHOPIFY_STORES_JSON)
                if isinstance(raw, dict):
                    raw = raw.get("stores", [])
                if not isinstance(raw, list):
                    raise ValueError("SHOPIFY_STORES_JSON bir JSON liste olmalı.")

                for idx, item in enumerate(raw, start=1):
                    if not isinstance(item, dict):
                        continue
                    domain = str(item.get("domain") or item.get("shop_domain") or "").strip()
                    token = str(item.get("token") or item.get("access_token") or "").strip()
                    if not domain or not token:
                        continue
                    key = str(item.get("key") or item.get("id") or f"store{idx}").strip()
                    name = str(item.get("name") or domain).strip()
                    api_version = str(item.get("api_version") or self.API_VERSION or "2026-04").strip()
                    stores[key] = StoreConfig(
                        key=key,
                        name=name,
                        domain=domain,
                        token=token,
                        api_version=api_version,
                    )
            except Exception:
                # check_config içinde anlaşılır hata olarak gösterilir.
                return {}

        # Geriye uyumluluk: SHOP_DOMAIN + SHOPIFY_ACCESS_TOKEN varsa tek mağaza olarak ekle.
        if self.SHOP_DOMAIN and self.SHOPIFY_ACCESS_TOKEN:
            legacy_key = "default"
            if legacy_key not in stores:
                stores[legacy_key] = StoreConfig(
                    key=legacy_key,
                    name=os.getenv("SHOP_NAME", self.SHOP_DOMAIN).strip() or self.SHOP_DOMAIN,
                    domain=self.SHOP_DOMAIN,
                    token=self.SHOPIFY_ACCESS_TOKEN,
                    api_version=self.API_VERSION,
                )

        return stores

    @property
    def stores(self) -> List[StoreConfig]:
        return list(self._stores.values())

    def get_store(self, key: Optional[str] = None) -> Optional[StoreConfig]:
        if key and key in self._stores:
            return self._stores[key]
        return next(iter(self._stores.values()), None)

    @property
    def base_rest_url(self):
        store = self.get_store()
        return store.base_rest_url if store else ""

    @property
    def graphql_url(self):
        store = self.get_store()
        return store.graphql_url if store else ""

    @property
    def headers(self):
        store = self.get_store()
        return store.headers if store else {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


settings = Settings()


def get_stores() -> List[StoreConfig]:
    return settings.stores


def get_store(key: Optional[str] = None) -> Optional[StoreConfig]:
    return settings.get_store(key)


def check_config():
    missing = []

    if settings.SHOPIFY_STORES_JSON:
        try:
            raw = json.loads(settings.SHOPIFY_STORES_JSON)
            if isinstance(raw, dict):
                raw = raw.get("stores", [])
            if not isinstance(raw, list):
                missing.append("SHOPIFY_STORES_JSON (geçersiz JSON)")
        except Exception:
            missing.append("SHOPIFY_STORES_JSON (geçersiz JSON)")

    if not settings.stores:
        missing.append("SHOP_DOMAIN/SHOPIFY_ACCESS_TOKEN veya SHOPIFY_STORES_JSON")

    if not settings.PANEL_PASSWORD:
        missing.append("PANEL_PASSWORD")

    if not settings.SECRET_KEY or settings.SECRET_KEY == "change-this-secret-key":
        missing.append("SECRET_KEY")

    return missing
