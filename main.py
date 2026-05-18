import os
import time
import uuid
import hmac
import hashlib
import html
import threading
from datetime import datetime
from collections import defaultdict

import requests
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse


# =========================
# ENV AYARLARI
# Render > Environment Variables alanına ekle:
# SHOP_DOMAIN=bzjwyw-jv.myshopify.com
# SHOPIFY_ACCESS_TOKEN=shpat_xxx
# API_VERSION=2026-04
# PANEL_PASSWORD=senin_sifren
# SECRET_KEY=rastgele_uzun_bir_metin
# =========================

SHOP_DOMAIN = os.getenv("SHOP_DOMAIN", "").strip()
ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
API_VERSION = os.getenv("API_VERSION", "2026-04").strip()
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key").encode("utf-8")

BASE_REST_URL = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}" if SHOP_DOMAIN else ""
GRAPHQL_URL = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json" if SHOP_DOMAIN else ""

HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

app = FastAPI(title="Shopify Tools Panel")

JOBS = {}
JOBS_LOCK = threading.Lock()


# =========================
# KÜÇÜK YARDIMCI FONKSİYONLAR
# =========================

def e(value):
    return html.escape(str(value or ""))


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_session_token():
    msg = b"shopify-tools-panel-auth"
    return hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()


def is_logged_in(request: Request):
    cookie_value = request.cookies.get("panel_session")
    expected = make_session_token()
    return bool(cookie_value and hmac.compare_digest(cookie_value, expected))


def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/", status_code=303)
    return None


def check_config():
    missing = []
    if not SHOP_DOMAIN:
        missing.append("SHOP_DOMAIN")
    if not ACCESS_TOKEN:
        missing.append("SHOPIFY_ACCESS_TOKEN")
    if not API_VERSION:
        missing.append("API_VERSION")
    if not PANEL_PASSWORD:
        missing.append("PANEL_PASSWORD")
    return missing


def create_job(title):
    job_id = str(uuid.uuid4())[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "title": title,
            "status": "running",
            "logs": [],
            "created_at": now_text(),
            "finished_at": "",
        }
    log(job_id, f"İş başlatıldı: {title}")
    return job_id


def log(job_id, message):
    line = f"[{now_text()}] {message}"
    print(line, flush=True)
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["logs"].append(line)
            if len(JOBS[job_id]["logs"]) > 3000:
                JOBS[job_id]["logs"] = JOBS[job_id]["logs"][-3000:]


def finish_job(job_id, status="done"):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["status"] = status
            JOBS[job_id]["finished_at"] = now_text()


def run_thread(target, *args):
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()


def render_layout(title, body, request=None, refresh_seconds=None):
    refresh_meta = ""
    if refresh_seconds:
        refresh_meta = f'<meta http-equiv="refresh" content="{int(refresh_seconds)}">'

    logout_link = ""
    if request and is_logged_in(request):
        logout_link = '<a class="top-link" href="/logout">Çıkış</a>'

    return HTMLResponse(f"""
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh_meta}
  <title>{e(title)}</title>
  <style>
    :root {{
      --bg: #f4f6fb;
      --card: #ffffff;
      --text: #111827;
      --muted: #6b7280;
      --border: #e5e7eb;
      --primary: #111827;
      --primary-hover: #374151;
      --danger: #dc2626;
      --green: #16a34a;
      --orange: #ea580c;
      --purple: #7c3aed;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .header {{
      background: #fff;
      border-bottom: 1px solid var(--border);
      padding: 18px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 5;
    }}
    .brand {{
      font-weight: 800;
      font-size: 18px;
    }}
    .top-link {{
      color: var(--text);
      text-decoration: none;
      font-size: 14px;
      border: 1px solid var(--border);
      padding: 8px 12px;
      border-radius: 10px;
      background: #fff;
    }}
    .wrap {{
      width: min(1120px, calc(100% - 32px));
      margin: 26px auto;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    @media (max-width: 760px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .header {{ padding: 16px; }}
      .wrap {{ width: calc(100% - 24px); }}
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: 28px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 21px;
    }}
    p {{
      color: var(--muted);
      line-height: 1.5;
    }}
    label {{
      display: block;
      font-weight: 700;
      margin: 14px 0 7px;
    }}
    input[type="text"], input[type="number"], input[type="password"] {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 13px;
      font-size: 15px;
      background: #fff;
    }}
    .check-row {{
      display: flex;
      align-items: center;
      gap: 9px;
      margin: 12px 0;
      color: var(--muted);
      font-size: 14px;
    }}
    button, .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      border: 0;
      border-radius: 12px;
      padding: 13px 16px;
      background: var(--primary);
      color: #fff;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
      text-decoration: none;
      margin-top: 14px;
    }}
    button:hover, .btn:hover {{ background: var(--primary-hover); }}
    .btn-light {{
      background: #fff;
      color: var(--text);
      border: 1px solid var(--border);
    }}
    .btn-light:hover {{ background: #f9fafb; }}
    .alert {{
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: #fff7ed;
      color: #9a3412;
      margin-bottom: 18px;
    }}
    .ok {{
      background: #ecfdf5;
      color: #166534;
      border-color: #bbf7d0;
    }}
    .muted {{ color: var(--muted); }}
    .small {{ font-size: 13px; }}
    .pill {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 99px;
      font-size: 13px;
      font-weight: 800;
      background: #eef2ff;
      color: #3730a3;
      margin: 4px 6px 4px 0;
    }}
    .status-running {{ background: #fff7ed; color: #9a3412; }}
    .status-done {{ background: #ecfdf5; color: #166534; }}
    .status-error {{ background: #fef2f2; color: #991b1b; }}
    pre {{
      background: #0b1020;
      color: #e5e7eb;
      padding: 18px;
      border-radius: 16px;
      overflow: auto;
      white-space: pre-wrap;
      line-height: 1.45;
      min-height: 360px;
      font-size: 13px;
    }}
    .jobs-list a {{
      display: block;
      color: var(--text);
      text-decoration: none;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      margin: 10px 0;
      background: #fff;
    }}
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">Shopify Tools Panel</div>
    <div>{logout_link}</div>
  </div>
  <main class="wrap">
    {body}
  </main>
</body>
</html>
""")


# =========================
# SHOPIFY REST
# =========================

def rest_request(method, path_or_url, job_id=None, **kwargs):
    if path_or_url.startswith("http"):
        url = path_or_url
    else:
        url = f"{BASE_REST_URL}{path_or_url}"

    for attempt in range(8):
        response = requests.request(method, url, headers=HEADERS, timeout=90, **kwargs)

        if response.status_code == 429:
            wait_time = float(response.headers.get("Retry-After", 2))
            if job_id:
                log(job_id, f"RATE LIMIT: {wait_time} saniye bekleniyor...")
            time.sleep(wait_time)
            continue

        if 500 <= response.status_code < 600:
            wait_time = 2 + attempt
            if job_id:
                log(job_id, f"SERVER HATASI {response.status_code}: {wait_time} saniye bekleniyor...")
            time.sleep(wait_time)
            continue

        if response.status_code >= 400:
            raise Exception(f"REST API hata: {response.status_code} | {response.text[:1000]}")

        return response

    raise Exception("REST API isteği tekrar denemelere rağmen başarısız oldu.")


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


# =========================
# SHOPIFY GRAPHQL
# =========================

def gql(query, variables=None, job_id=None, retries=8):
    payload = {
        "query": query,
        "variables": variables or {}
    }

    for attempt in range(retries):
        response = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=90)

        if response.status_code == 429:
            wait_time = float(response.headers.get("Retry-After", 2))
            if job_id:
                log(job_id, f"GRAPHQL RATE LIMIT: {wait_time} saniye bekleniyor...")
            time.sleep(wait_time)
            continue

        if 500 <= response.status_code < 600:
            wait_time = 2 + attempt
            if job_id:
                log(job_id, f"GRAPHQL SERVER HATASI {response.status_code}: {wait_time} saniye bekleniyor...")
            time.sleep(wait_time)
            continue

        if response.status_code >= 400:
            raise Exception(f"GraphQL HTTP hata: {response.status_code} | {response.text[:1000]}")

        data = response.json()

        if "errors" in data:
            errors_text = str(data["errors"])
            if "THROTTLED" in errors_text or "Throttled" in errors_text:
                wait_time = 2 + attempt
                if job_id:
                    log(job_id, f"GRAPHQL THROTTLED: {wait_time} saniye bekleniyor...")
                time.sleep(wait_time)
                continue

            raise Exception(f"GraphQL hata: {data['errors']}")

        return data["data"]

    raise Exception("GraphQL isteği tekrar denemelere rağmen başarısız oldu.")


# =========================
# İŞLEM 1: TÜM VARYANT STOKLARINI AYARLA
# =========================

def get_first_active_location_id(job_id):
    response = rest_request("GET", "/locations.json", job_id=job_id)
    locations = response.json().get("locations", [])
    active_locations = [loc for loc in locations if loc.get("active")]

    if not active_locations:
        raise Exception("Aktif lokasyon bulunamadı.")

    location = active_locations[0]
    log(job_id, f"Kullanılan lokasyon: {location.get('name')} | ID: {location.get('id')}")
    return location["id"]


def fetch_products_for_stock(job_id):
    url = f"{BASE_REST_URL}/products.json?limit=250&fields=id,title,variants"
    product_count = 0

    while url:
        response = rest_request("GET", url, job_id=job_id)
        products = response.json().get("products", [])

        for product in products:
            product_count += 1
            yield product

        url = get_next_link(response)

    log(job_id, f"Toplam taranan ürün sayısı: {product_count}")


def set_inventory_level(job_id, location_id, inventory_item_id, available, dry_run):
    if dry_run:
        return True

    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(available),
        "disconnect_if_necessary": True,
    }

    rest_request("POST", "/inventory_levels/set.json", job_id=job_id, json=payload)
    return True


def stock_update_job(job_id, stock_value, dry_run):
    try:
        missing = check_config()
        if missing:
            raise Exception(f"Eksik ENV ayarları: {', '.join(missing)}")

        stock_value = int(stock_value)
        log(job_id, f"Hedef stok: {stock_value}")
        log(job_id, f"DRY_RUN: {dry_run}")

        location_id = get_first_active_location_id(job_id)

        updated_count = 0
        skipped_count = 0
        error_count = 0

        for product in fetch_products_for_stock(job_id):
            product_title = product.get("title", "")
            variants = product.get("variants", [])

            for variant in variants:
                variant_id = variant.get("id")
                sku = variant.get("sku") or "-"
                inventory_item_id = variant.get("inventory_item_id")
                inventory_management = variant.get("inventory_management")

                if not inventory_item_id:
                    skipped_count += 1
                    log(job_id, f"ATLANDI: inventory_item_id yok | {product_title} | Variant ID: {variant_id}")
                    continue

                if inventory_management is None:
                    skipped_count += 1
                    log(job_id, f"ATLANDI: Stok takibi kapalı | {product_title} | SKU: {sku}")
                    continue

                try:
                    set_inventory_level(job_id, location_id, inventory_item_id, stock_value, dry_run)
                    updated_count += 1

                    if updated_count % 25 == 0:
                        log(job_id, f"İlerleme: {updated_count} varyant güncellendi / güncellenecek...")

                    time.sleep(0.15)

                except Exception as exc:
                    error_count += 1
                    log(job_id, f"HATA: {product_title} | SKU: {sku} | Variant ID: {variant_id} | {exc}")

        log(job_id, "İŞLEM BİTTİ")
        log(job_id, f"Güncellenen / güncellenecek varyant sayısı: {updated_count}")
        log(job_id, f"Atlanan varyant sayısı: {skipped_count}")
        log(job_id, f"Hatalı varyant sayısı: {error_count}")

        finish_job(job_id, "done")

    except Exception as exc:
        log(job_id, f"GENEL HATA: {exc}")
        finish_job(job_id, "error")


# =========================
# İŞLEM 2: ALT KATEGORİ ÜRÜNLERİNİ ÜST KATEGORİLERE EKLE
# =========================

def get_menu_id_by_handle(job_id, menu_handle):
    query = """
    query GetMenus($first: Int!, $after: String) {
      menus(first: $first, after: $after) {
        edges {
          cursor
          node {
            id
            handle
            title
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    after = None

    while True:
        data = gql(query, {"first": 250, "after": after}, job_id=job_id)

        for edge in data["menus"]["edges"]:
            menu = edge["node"]
            if menu["handle"] == menu_handle:
                log(job_id, f"Menü bulundu: {menu['title']} | Handle: {menu['handle']}")
                return menu["id"]

        page_info = data["menus"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break

        after = page_info["endCursor"]

    raise Exception(f"Menü bulunamadı: {menu_handle}")


def get_menu_tree(job_id, menu_id):
    query = """
    query GetMenu($id: ID!) {
      menu(id: $id) {
        id
        title
        handle
        items {
          id
          title
          type
          resourceId
          url
          items {
            id
            title
            type
            resourceId
            url
            items {
              id
              title
              type
              resourceId
              url
              items {
                id
                title
                type
                resourceId
                url
              }
            }
          }
        }
      }
    }
    """

    data = gql(query, {"id": menu_id}, job_id=job_id)
    menu = data.get("menu")

    if not menu:
        raise Exception("Menü okunamadı.")

    log(job_id, f"Menü ağacı okundu: {menu.get('title')}")
    return menu


def is_collection_item(item):
    resource_id = item.get("resourceId")
    return (
        item.get("type") == "COLLECTION"
        and resource_id
        and resource_id.startswith("gid://shopify/Collection/")
    )


def build_child_to_parent_map(items, ancestor_collections=None, result=None):
    if ancestor_collections is None:
        ancestor_collections = []

    if result is None:
        result = defaultdict(set)

    for item in items:
        current_collection_id = item.get("resourceId") if is_collection_item(item) else None

        if current_collection_id and ancestor_collections:
            for parent_id in ancestor_collections:
                result[current_collection_id].add(parent_id)

        next_ancestors = list(ancestor_collections)
        if current_collection_id:
            next_ancestors.append(current_collection_id)

        children = item.get("items") or []
        if children:
            build_child_to_parent_map(children, next_ancestors, result)

    return result


def get_collection_info(job_id, collection_id):
    query = """
    query GetCollectionInfo($id: ID!) {
      node(id: $id) {
        ... on Collection {
          id
          title
          handle
          ruleSet {
            appliedDisjunctively
          }
        }
      }
    }
    """

    data = gql(query, {"id": collection_id}, job_id=job_id)
    node = data.get("node")

    if not node:
        return {
            "id": collection_id,
            "title": collection_id,
            "handle": "",
            "is_smart": False,
        }

    return {
        "id": node["id"],
        "title": node.get("title", ""),
        "handle": node.get("handle", ""),
        "is_smart": node.get("ruleSet") is not None,
    }


def get_collection_product_ids(job_id, collection_id):
    query = """
    query GetCollectionProducts($id: ID!, $first: Int!, $after: String) {
      node(id: $id) {
        ... on Collection {
          id
          title
          products(first: $first, after: $after) {
            edges {
              cursor
              node {
                id
                title
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
    """

    product_ids = set()
    after = None

    while True:
        data = gql(query, {
            "id": collection_id,
            "first": 250,
            "after": after,
        }, job_id=job_id)

        node = data.get("node")
        if not node:
            log(job_id, f"UYARI: Koleksiyon okunamadı: {collection_id}")
            return set()

        for edge in node["products"]["edges"]:
            product_ids.add(edge["node"]["id"])

        page_info = node["products"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break

        after = page_info["endCursor"]

    return product_ids


def chunk_list(items, size):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def add_missing_products_to_collection(job_id, parent_collection_id, missing_product_ids, dry_run):
    mutation = """
    mutation AddProductsToCollection($id: ID!, $productIds: [ID!]!) {
      collectionAddProducts(id: $id, productIds: $productIds) {
        collection {
          id
          title
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    if not missing_product_ids:
        return 0

    added_total = 0

    for batch in chunk_list(missing_product_ids, 200):
        if dry_run:
            log(job_id, f"TEST: {len(batch)} eksik ürün eklenecekti.")
            added_total += len(batch)
            continue

        data = gql(mutation, {
            "id": parent_collection_id,
            "productIds": batch,
        }, job_id=job_id)

        result = data["collectionAddProducts"]
        errors = result.get("userErrors") or []

        if errors:
            log(job_id, f"HATA: Koleksiyona ekleme başarısız: {parent_collection_id}")
            for error in errors:
                log(job_id, f"  Field: {error.get('field')} | Message: {error.get('message')}")
            continue

        collection_title = result["collection"]["title"]
        log(job_id, f"OK: {len(batch)} eksik ürün eklendi -> {collection_title}")

        added_total += len(batch)
        time.sleep(0.25)

    return added_total


def category_sync_job(job_id, menu_handle, dry_run):
    try:
        missing = check_config()
        if missing:
            raise Exception(f"Eksik ENV ayarları: {', '.join(missing)}")

        menu_handle = menu_handle.strip()
        if not menu_handle:
            raise Exception("Menü handle boş olamaz.")

        log(job_id, f"Menü handle: {menu_handle}")
        log(job_id, f"DRY_RUN: {dry_run}")

        menu_id = get_menu_id_by_handle(job_id, menu_handle)
        menu = get_menu_tree(job_id, menu_id)

        child_to_parents = build_child_to_parent_map(menu.get("items", []))

        if not child_to_parents:
            log(job_id, "Menüde alt/üst koleksiyon ilişkisi bulunamadı.")
            finish_job(job_id, "done")
            return

        log(job_id, f"Bulunan alt kategori sayısı: {len(child_to_parents)}")

        total_added = 0
        total_already_exists = 0
        total_skipped_smart = 0
        total_empty_child = 0

        parent_products_cache = {}

        for child_collection_id, parent_collection_ids in child_to_parents.items():
            child_info = get_collection_info(job_id, child_collection_id)
            child_product_ids = get_collection_product_ids(job_id, child_collection_id)

            log(job_id, "--------------------------------------------------")
            log(job_id, f"ALT KATEGORİ: {child_info['title']} ({child_info['handle']})")
            log(job_id, f"Alt kategorideki ürün sayısı: {len(child_product_ids)}")

            if not child_product_ids:
                total_empty_child += 1
                log(job_id, "ATLANDI: Alt kategoride ürün yok.")
                continue

            for parent_collection_id in parent_collection_ids:
                parent_info = get_collection_info(job_id, parent_collection_id)
                log(job_id, f"ÜST KATEGORİ: {parent_info['title']} ({parent_info['handle']})")

                if parent_info["is_smart"]:
                    total_skipped_smart += 1
                    log(job_id, "ATLANDI: Bu üst kategori otomatik koleksiyon. Manuel ürün eklenemez.")
                    continue

                if parent_collection_id not in parent_products_cache:
                    parent_products_cache[parent_collection_id] = get_collection_product_ids(job_id, parent_collection_id)

                parent_existing_product_ids = parent_products_cache[parent_collection_id]

                already_existing_product_ids = child_product_ids.intersection(parent_existing_product_ids)
                missing_product_ids = child_product_ids.difference(parent_existing_product_ids)

                log(job_id, f"Zaten üst kategoride olan ürün: {len(already_existing_product_ids)}")
                log(job_id, f"Yeni eklenecek eksik ürün: {len(missing_product_ids)}")

                total_already_exists += len(already_existing_product_ids)

                if not missing_product_ids:
                    log(job_id, "OK: Eklenecek eksik ürün yok. Aynı ürün tekrar eklenmedi.")
                    continue

                added_count = add_missing_products_to_collection(
                    job_id,
                    parent_collection_id,
                    missing_product_ids,
                    dry_run,
                )

                total_added += added_count
                parent_products_cache[parent_collection_id].update(missing_product_ids)

        log(job_id, "İŞLEM BİTTİ")
        log(job_id, f"Yeni eklenen / eklenecek ürün-kategori ilişkisi: {total_added}")
        log(job_id, f"Zaten mevcut olduğu için tekrar eklenmeyen ilişki: {total_already_exists}")
        log(job_id, f"Otomatik koleksiyon olduğu için atlanan üst kategori: {total_skipped_smart}")
        log(job_id, f"Ürünü olmadığı için atlanan alt kategori: {total_empty_child}")

        finish_job(job_id, "done")

    except Exception as exc:
        log(job_id, f"GENEL HATA: {exc}")
        finish_job(job_id, "error")


# =========================
# WEB SAYFALARI
# =========================

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if is_logged_in(request):
        return RedirectResponse("/dashboard", status_code=303)

    missing = check_config()
    warning = ""
    if missing:
        warning = f"""
        <div class="alert">
          Eksik Render Environment Variables: <b>{e(", ".join(missing))}</b>
          <br>Render panelinden bunları eklemeden işlemler çalışmaz.
        </div>
        """

    body = f"""
    <div class="card" style="max-width:520px;margin:80px auto;">
      <h1>Giriş</h1>
      {warning}
      <p>Shopify işlem paneline devam etmek için panel şifresini gir.</p>
      <form method="post" action="/login">
        <label>Panel Şifresi</label>
        <input type="password" name="password" placeholder="PANEL_PASSWORD" required>
        <button type="submit">Giriş Yap</button>
      </form>
    </div>
    """
    return render_layout("Giriş", body, request)


@app.post("/login")
def login(password: str = Form(...)):
    if not PANEL_PASSWORD:
        return PlainTextResponse("PANEL_PASSWORD env ayarı eksik.", status_code=500)

    if not hmac.compare_digest(password, PANEL_PASSWORD):
        return HTMLResponse("""
        <html><body style="font-family:Arial;padding:40px;">
          <h2>Şifre yanlış</h2>
          <p><a href="/">Tekrar dene</a></p>
        </body></html>
        """, status_code=401)

    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        "panel_session",
        make_session_token(),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("panel_session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    missing = check_config()
    config_alert = ""
    if missing:
        config_alert = f"""
        <div class="alert">
          Eksik ayarlar var: <b>{e(", ".join(missing))}</b>
          <br>Render > Environment Variables alanından tamamlaman gerekiyor.
        </div>
        """
    else:
        config_alert = f"""
        <div class="alert ok">
          Ayarlar hazır görünüyor. Shop: <b>{e(SHOP_DOMAIN)}</b> | API: <b>{e(API_VERSION)}</b>
        </div>
        """

    with JOBS_LOCK:
        recent_jobs = list(JOBS.values())[-8:][::-1]

    jobs_html = ""
    if recent_jobs:
        items = []
        for job in recent_jobs:
            status = job["status"]
            items.append(f"""
            <a href="/jobs/{e(job['id'])}">
              <b>{e(job['title'])}</b><br>
              <span class="pill status-{e(status)}">{e(status)}</span>
              <span class="muted small">Başlangıç: {e(job['created_at'])}</span>
            </a>
            """)
        jobs_html = f"""
        <div class="card" style="margin-top:18px;">
          <h2>Son İşlemler</h2>
          <div class="jobs-list">{''.join(items)}</div>
        </div>
        """

    body = f"""
    <h1>Shopify İşlem Paneli</h1>
    {config_alert}

    <div class="grid">
      <div class="card">
        <h2>Tüm Varyant Stoklarını Ayarla</h2>
        <p>Mağazadaki tüm ürün varyantlarının stok miktarını seçtiğin değere çeker. Stok takibi kapalı varyantlar atlanır.</p>
        <form method="post" action="/actions/stocks">
          <label>Hedef stok miktarı</label>
          <input type="number" name="stock_value" value="5" min="0" required>
          <label class="check-row">
            <input type="checkbox" name="dry_run" value="1" checked>
            Önce test modunda çalıştır, gerçek değişiklik yapma
          </label>
          <button type="submit">Stok İşlemini Başlat</button>
        </form>
      </div>

      <div class="card">
        <h2>Alt Kategori Ürünlerini Üst Kategorilere Ekle</h2>
        <p>Menü hiyerarşisine göre alt koleksiyonlardaki ürünleri üst koleksiyonlara ekler. Ürün zaten varsa tekrar eklemez.</p>
        <form method="post" action="/actions/categories">
          <label>Shopify menü handle</label>
          <input type="text" name="menu_handle" placeholder="main-menu veya standort-feste-kategorie" required>
          <label class="check-row">
            <input type="checkbox" name="dry_run" value="1" checked>
            Önce test modunda çalıştır, gerçek değişiklik yapma
          </label>
          <button type="submit">Kategori İşlemini Başlat</button>
        </form>
      </div>
    </div>

    {jobs_html}
    """
    return render_layout("Dashboard", body, request)


@app.post("/actions/stocks")
def start_stock_action(request: Request, stock_value: int = Form(...), dry_run: str = Form(None)):
    redirect = require_login(request)
    if redirect:
        return redirect

    dry = dry_run == "1"
    title = f"Stokları {stock_value} yap"
    if dry:
        title += " - TEST"

    job_id = create_job(title)
    run_thread(stock_update_job, job_id, stock_value, dry)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/actions/categories")
def start_category_action(request: Request, menu_handle: str = Form(...), dry_run: str = Form(None)):
    redirect = require_login(request)
    if redirect:
        return redirect

    dry = dry_run == "1"
    title = f"Kategori senkronizasyonu: {menu_handle}"
    if dry:
        title += " - TEST"

    job_id = create_job(title)
    run_thread(category_sync_job, job_id, menu_handle, dry)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str, request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    with JOBS_LOCK:
        job = JOBS.get(job_id)

    if not job:
        return render_layout("İş bulunamadı", """
        <div class="card">
          <h1>İş bulunamadı</h1>
          <a class="btn btn-light" href="/dashboard">Panele dön</a>
        </div>
        """, request)

    status = job["status"]
    refresh = 3 if status == "running" else None
    logs = "\n".join(job.get("logs", []))

    body = f"""
    <div class="card">
      <h1>{e(job['title'])}</h1>
      <p>
        <span class="pill status-{e(status)}">{e(status)}</span>
        <span class="muted small">Başlangıç: {e(job['created_at'])}</span>
        {'<span class="muted small"> | Bitiş: ' + e(job.get('finished_at')) + '</span>' if job.get('finished_at') else ''}
      </p>
      <pre>{e(logs)}</pre>
      <a class="btn btn-light" href="/dashboard">Panele dön</a>
    </div>
    """
    return render_layout("İş Detayı", body, request, refresh_seconds=refresh)


@app.get("/health")
def health():
    return {"status": "ok"}
