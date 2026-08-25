import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote

from core.config import check_config, get_store
from core.job_manager import finish_job, log, set_progress
from core.shopify_client import ShopifyClient

MONEY_STEP = Decimal('0.01')
MIN_SALE_STOCK = 10



def variant_stock(variant):
    try:
        return int(variant.get('inventory_quantity') or 0)
    except (TypeError, ValueError):
        return 0


def money(value):
    try:
        return Decimal(str(value)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


def discounted_price(original, percent):
    original = money(original)
    pct = Decimal(str(percent))
    if original is None:
        return None
    value = original * (Decimal('100') - pct) / Decimal('100')
    return value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def money_text(value):
    return f'{money(value):.2f}'


def fetch_products_by_collection(client, collection_handle):
    collection = client.find_collection_by_handle(collection_handle)
    if not collection:
        raise Exception(f'Kategori bulunamadı: {collection_handle}')
    out = []
    path = f'/collections/{collection["id"]}/products.json?limit=250&fields=id,title,handle,vendor,variants'
    for response in client.iter_rest_pages(path):
        out.extend(response.json().get('products', []))
    return out


def fetch_products_by_vendor(client, vendor):
    out = []
    path = f'/products.json?vendor={quote(vendor)}&limit=250&fields=id,title,handle,vendor,variants'
    for response in client.iter_rest_pages(path):
        out.extend(response.json().get('products', []))
    return out


def fetch_products_by_handles(client, handles):
    out = []
    seen = set()
    for handle in handles:
        handle = str(handle or '').strip()
        if not handle or handle in seen:
            continue
        seen.add(handle)
        product = client.find_product_by_handle(handle)
        if product:
            out.append(product)
    return out


def select_products(client, filter_mode, filter_value, product_handles):
    if filter_mode == 'collection':
        if not filter_value:
            raise Exception('Kategori seçilmedi.')
        return fetch_products_by_collection(client, filter_value)
    if filter_mode == 'vendor':
        if not filter_value:
            raise Exception('Satıcı/marka seçilmedi.')
        return fetch_products_by_vendor(client, filter_value)
    if filter_mode == 'products':
        if not product_handles:
            raise Exception('En az bir ürün seçilmedi.')
        return fetch_products_by_handles(client, product_handles)
    raise Exception(f'Geçersiz filtre tipi: {filter_mode}')



def apply_variant_discount(job_id, client, product, variant, discount_percent, dry_run):
    variant_id = variant.get('id')
    current_price = money(variant.get('price'))
    compare_price = money(variant.get('compare_at_price')) if variant.get('compare_at_price') not in (None, '') else None
    sku = variant.get('sku') or '-'
    stock = variant_stock(variant)

    # Sale indirimi yalnızca stoğu 10'dan büyük varyantlara uygulanır.
    if stock <= MIN_SALE_STOCK:
        log(job_id, f'ATLANDI: stok yetersiz ({stock}) | {product.get("title")} | SKU={sku} | gerekli > {MIN_SALE_STOCK}')
        return 'stock_skipped'

    if current_price is None:
        log(job_id, f'ATLANDI: geçersiz fiyat | {product.get("title")} | SKU={sku}')
        return 'skipped'

    # Tekrar tekrar indirim bindirmeyi ve mevcut kampanyayı ezmeyi önler.
    if compare_price is not None:
        log(job_id, f'ATLANDI: compare_at_price zaten dolu ({compare_price:.2f}) | {product.get("title")} | SKU={sku}')
        return 'skipped'

    new_price = discounted_price(current_price, discount_percent)
    if new_price is None or new_price >= current_price:
        log(job_id, f'ATLANDI: indirim sonrası fiyat değişmiyor | {product.get("title")} | SKU={sku}')
        return 'skipped'

    payload = {
        'variant': {
            'id': variant_id,
            'price': money_text(new_price),
            'compare_at_price': money_text(current_price),
        }
    }
    if dry_run:
        log(job_id, f'TEST FİYAT: {product.get("title")} | SKU={sku} | {current_price:.2f} -> {new_price:.2f} | stok={stock} | compare={current_price:.2f}')
    else:
        client.rest_request('PUT', f'/variants/{variant_id}.json', json=payload)
        log(job_id, f'FİYAT OK: {product.get("title")} | SKU={sku} | {current_price:.2f} -> {new_price:.2f} | stok={stock}')
    return 'updated'


def restore_variant_price(job_id, client, product, variant, dry_run):
    variant_id = variant.get('id')
    current_price = money(variant.get('price'))
    compare_price = money(variant.get('compare_at_price')) if variant.get('compare_at_price') not in (None, '') else None
    sku = variant.get('sku') or '-'

    if compare_price is None:
        log(job_id, f'ATLANDI: compare_at_price boş | {product.get("title")} | SKU={sku}')
        return 'skipped'

    payload = {
        'variant': {
            'id': variant_id,
            'price': money_text(compare_price),
            'compare_at_price': None,
        }
    }
    if dry_run:
        log(job_id, f'TEST GERİ AL: {product.get("title")} | SKU={sku} | {current_price} -> {compare_price:.2f} | compare temizlenecek')
    else:
        client.rest_request('PUT', f'/variants/{variant_id}.json', json=payload)
        log(job_id, f'GERİ AL OK: {product.get("title")} | SKU={sku} | fiyat={compare_price:.2f}')
    return 'updated'


def process_store(job_id, store_key, operation, discount_percent, filter_mode, filter_value, product_handles, dry_run):
    store = get_store(store_key)
    if not store:
        raise Exception(f'Mağaza bulunamadı: {store_key}')

    client = ShopifyClient(job_id, store=store)
    log(job_id, f'===== MAĞAZA: {store.name} | {store.domain} =====')
    products = select_products(client, filter_mode, filter_value, product_handles)
    log(job_id, f'Seçilen ürün sayısı: {len(products)}')

    stats = {
        'products': len(products),
        'variant_updated': 0,
        'variant_skipped': 0,
        'stock_skipped': 0,
        'errors': 0,
    }

    total_products = len(products)
    set_progress(job_id, 0, total_products, store.name)
    for product_index, product in enumerate(products, start=1):
        log(job_id, f'ÜRÜN {product_index}/{total_products}: {product.get("title")}')
        try:
            for variant in product.get('variants', []):
                if operation == 'apply':
                    result = apply_variant_discount(job_id, client, product, variant, discount_percent, dry_run)
                else:
                    result = restore_variant_price(job_id, client, product, variant, dry_run)
                if result == 'updated':
                    stats['variant_updated'] += 1
                elif result == 'stock_skipped':
                    stats['stock_skipped'] += 1
                    stats['variant_skipped'] += 1
                else:
                    stats['variant_skipped'] += 1
                time.sleep(0.08)

        except Exception as exc:
            stats['errors'] += 1
            log(job_id, f'HATA ÜRÜN {product_index}/{total_products}: {product.get("title")} | {exc}')
        finally:
            set_progress(job_id, product_index, total_products, store.name)

    log(
        job_id,
        'MAĞAZA ÖZET: '
        f'products={stats["products"]} '
        f'variant_updated={stats["variant_updated"]} '
        f'variant_skipped={stats["variant_skipped"]} '
        f'stock_skipped={stats["stock_skipped"]} '
        f'errors={stats["errors"]}',
    )
    return stats


def run(job_id, store_keys, operation, discount_percent, filter_mode, filter_value, product_handles, dry_run):
    try:
        missing = check_config()
        if missing:
            raise Exception('Eksik ENV: ' + ', '.join(missing))
        if operation not in ('apply', 'restore'):
            raise Exception('Geçersiz işlem.')
        discount_percent = Decimal(str(discount_percent))
        if operation == 'apply' and (discount_percent <= 0 or discount_percent >= 100):
            raise Exception('İndirim yüzdesi 0 ile 100 arasında olmalı.')
        if not store_keys:
            raise Exception('En az bir mağaza seçilmeli.')

        log(job_id, f'İŞLEM: {operation} | indirim={discount_percent}% | filtre={filter_mode} | TEST={dry_run}')
        total_errors = 0
        for store_key in store_keys:
            try:
                stats = process_store(
                    job_id,
                    store_key,
                    operation,
                    discount_percent,
                    filter_mode,
                    filter_value,
                    product_handles,
                    dry_run,
                )
                total_errors += stats['errors']
            except Exception as exc:
                total_errors += 1
                log(job_id, f'MAĞAZA HATASI [{store_key}]: {exc}')

        log(job_id, f'İŞLEM TAMAMLANDI | toplam hata={total_errors}')
        finish_job(job_id, 'done' if total_errors == 0 else 'error')
    except Exception as exc:
        log(job_id, f'GENEL HATA: {exc}')
        finish_job(job_id, 'error')
