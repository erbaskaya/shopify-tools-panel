import time

import requests

from core.config import settings
from core.job_manager import log


class ShopifyClient:
    def __init__(self, job_id=None):
        self.job_id = job_id

    def _log(self, message):
        if self.job_id:
            log(self.job_id, message)

    def rest_request(self, method, path_or_url, **kwargs):
        if path_or_url.startswith("http"):
            url = path_or_url
        else:
            url = f"{settings.base_rest_url}{path_or_url}"

        for attempt in range(8):
            response = requests.request(
                method,
                url,
                headers=settings.headers,
                timeout=90,
                **kwargs,
            )

            if response.status_code == 429:
                wait_time = float(response.headers.get("Retry-After", 2))
                self._log(f"REST RATE LIMIT: {wait_time} saniye bekleniyor...")
                time.sleep(wait_time)
                continue

            if 500 <= response.status_code < 600:
                wait_time = 2 + attempt
                self._log(f"REST SERVER HATASI {response.status_code}: {wait_time} saniye bekleniyor...")
                time.sleep(wait_time)
                continue

            if response.status_code >= 400:
                raise Exception(f"REST API hata: {response.status_code} | {response.text[:1000]}")

            return response

        raise Exception("REST API isteği tekrar denemelere rağmen başarısız oldu.")

    def gql(self, query, variables=None, retries=8):
        payload = {
            "query": query,
            "variables": variables or {},
        }

        for attempt in range(retries):
            response = requests.post(
                settings.graphql_url,
                headers=settings.headers,
                json=payload,
                timeout=90,
            )

            if response.status_code == 429:
                wait_time = float(response.headers.get("Retry-After", 2))
                self._log(f"GRAPHQL RATE LIMIT: {wait_time} saniye bekleniyor...")
                time.sleep(wait_time)
                continue

            if 500 <= response.status_code < 600:
                wait_time = 2 + attempt
                self._log(f"GRAPHQL SERVER HATASI {response.status_code}: {wait_time} saniye bekleniyor...")
                time.sleep(wait_time)
                continue

            if response.status_code >= 400:
                raise Exception(f"GraphQL HTTP hata: {response.status_code} | {response.text[:1000]}")

            data = response.json()

            if "errors" in data:
                errors_text = str(data["errors"])

                if "THROTTLED" in errors_text or "Throttled" in errors_text:
                    wait_time = 2 + attempt
                    self._log(f"GRAPHQL THROTTLED: {wait_time} saniye bekleniyor...")
                    time.sleep(wait_time)
                    continue

                raise Exception(f"GraphQL hata: {data['errors']}")

            return data["data"]

        raise Exception("GraphQL isteği tekrar denemelere rağmen başarısız oldu.")


def get_next_link(response):
    link_header = response.headers.get("Link", "")

    if not link_header:
        return None

    for part in link_header.split(","):
        if 'rel="next"' in part:
            start = part.find("<") + 1
            end = part.find(">")
            return part[start:end]

    return None
