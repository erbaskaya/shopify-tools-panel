import os


class Settings:
    SHOP_DOMAIN = os.getenv("SHOP_DOMAIN", "").strip()
    SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
    API_VERSION = os.getenv("API_VERSION", "2026-04").strip()
    PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "").strip()
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key").strip()

    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() not in ("0", "false", "no", "off")

    @property
    def base_rest_url(self):
        if not self.SHOP_DOMAIN:
            return ""
        return f"https://{self.SHOP_DOMAIN}/admin/api/{self.API_VERSION}"

    @property
    def graphql_url(self):
        if not self.SHOP_DOMAIN:
            return ""
        return f"https://{self.SHOP_DOMAIN}/admin/api/{self.API_VERSION}/graphql.json"

    @property
    def headers(self):
        return {
            "X-Shopify-Access-Token": self.SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


settings = Settings()


def check_config():
    missing = []

    if not settings.SHOP_DOMAIN:
        missing.append("SHOP_DOMAIN")

    if not settings.SHOPIFY_ACCESS_TOKEN:
        missing.append("SHOPIFY_ACCESS_TOKEN")

    if not settings.API_VERSION:
        missing.append("API_VERSION")

    if not settings.PANEL_PASSWORD:
        missing.append("PANEL_PASSWORD")

    if not settings.SECRET_KEY or settings.SECRET_KEY == "change-this-secret-key":
        missing.append("SECRET_KEY")

    return missing
