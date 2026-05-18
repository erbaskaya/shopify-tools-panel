import time

from core.config import check_config, settings
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient, get_next_link


def get_first_active_location_id(job_id, client):
    response = client.rest_request("GET", "/locations.json")
    locations = response.json().get("locations", [])
    active_locations = [loc for loc in locations if loc.get("active")]

    if not active_locations:
        raise Exception("Aktif lokasyon bulunamadı.")

    location = active_locations[0]
    log(job_id, f"Kullanılan lokasyon: {location.get('name')} | ID: {location.get('id')}")
    return location["id"]


def fetch_products_for_stock(job_id, client):
    url = f"{settings.base_rest_url}/products.json?limit=250&fields=id,title,variants"
    product_count = 0

    while url:
        response = client.rest_request("GET", url)
        products = response.json().get("products", [])

        for product in products:
            product_count += 1
            yield product

        url = get_next_link(response)

    log(job_id, f"Toplam taranan ürün sayısı: {product_count}")


def set_inventory_level(client, location_id, inventory_item_id, available, dry_run):
    if dry_run:
        return True

    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(available),
        "disconnect_if_necessary": True,
    }

    client.rest_request("POST", "/inventory_levels/set.json", json=payload)
    return True


def run(job_id, stock_value, dry_run):
    try:
        missing = check_config()
        if missing:
            raise Exception(f"Eksik ENV ayarları: {', '.join(missing)}")

        client = ShopifyClient(job_id)

        stock_value = int(stock_value)
        log(job_id, f"Hedef stok: {stock_value}")
        log(job_id, f"DRY_RUN: {dry_run}")

        location_id = get_first_active_location_id(job_id, client)

        updated_count = 0
        skipped_count = 0
        error_count = 0

        for product in fetch_products_for_stock(job_id, client):
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
                    set_inventory_level(client, location_id, inventory_item_id, stock_value, dry_run)
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
