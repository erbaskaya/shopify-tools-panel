import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote

from core.config import check_config, get_store
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient

MONEY_STEP = Decimal('0.01')
SALE_HANDLE = 'sale'


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


def get_sale_collection(client):
    collection = client.find_collection_by_handle(SALE_HANDLE)
    if not collection:
        raise Exception('collections/sale kategorisi bulunamadı.')
    if collection.get('_collection_kind') != 'manual':
        raise Exception('collections/sale bir manuel (custom) kategori olmalı. Smart kategoriye elle ürün eklenemez/çıkarılamaz.')
    return collection


def collect_membership(client, collection_id, product_id):
    response = client.rest_request(
        'GET',
        f'/collects.json?collection_id={collection_id}&product_id={product_id}&limit=10',
    )
    return response.json().get('collects', [])


def add_to_sale(job_id, client, collection_id, product, dry_run):
    memberships = collect_membership(client, collection_id, product['id'])
    if memberships:
        log(job_id, f'KATEGORİ: zaten Sale içinde | {product.get("title")}')
        return False
    if dry_run:
        log(job_id, f'TEST KATEGORİ: Sale kategorisine eklenecekti | {product.get("title")}')
        return True
    client.rest_request(
        'POST',
        '/collects.json',
        json={'collect': {'product_id': product['id'], 'collection_id': collection_id}},
    )
    log(job_id, f'KATEGORİ OK: Sale kategorisine eklendi | {product.get("title")}')
    return True


def remove_from_sale(job_id, client, collection_id, product, dry_run):
    memberships = collect_membership(client, collection_id, product['id'])
    if not memberships:
        log(job_id, f'KATEGORİ: Sale içinde değil | {product.get("title")}')
        return False
    if dry_run:
        log(job_id, f'TEST KATEGORİ: Sale kategorisinden çıkarılacaktı | {product.get("title")}')
        return True
    for membership in memberships:
        client.rest_request('DELETE', f'/collects/{membership["id"]}.json')
    log(job_id, f'KATEGORİ OK: Sale kategorisinden çıkarıldı | {product.get("title")}')
    return True


def apply_variant_discount(job_id, client, product, variant, discount_percent, dry_run):
    variant_id = variant.get('id')
    current_price = money(variant.get('price'))
    compare_price = money(variant.get('compare_at_price')) if variant.get('compare_at_price') not in (None, '') else None
    sku = variant.get('sku') or '-'

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
        log(job_id, f'TEST FİYAT: {product.get("title")} | SKU={sku} | {current_price:.2f} -> {new_price:.2f} | compare={current_price:.2f}')
    else:
        client.rest_request('PUT', f'/variants/{variant_id}.json', json=payload)
        log(job_id, f'FİYAT OK: {product.get("title")} | SKU={sku} | {current_price:.2f} -> {new_price:.2f}')
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
    sale_collection = get_sale_collection(client)
    products = select_products(client, filter_mode, filter_value, product_handles)
    log(job_id, f'Seçilen ürün sayısı: {len(products)}')

    stats = {
        'products': len(products),
        'variant_updated': 0,
        'variant_skipped': 0,
        'collection_changed': 0,
        'errors': 0,
    }

    for product in products:
        try:
            for variant in product.get('variants', []):
                if operation == 'apply':
                    result = apply_variant_discount(job_id, client, product, variant, discount_percent, dry_run)
                else:
                    result = restore_variant_price(job_id, client, product, variant, dry_run)
                if result == 'updated':
                    stats['variant_updated'] += 1
                else:
                    stats['variant_skipped'] += 1
                time.sleep(0.08)

            if operation == 'apply':
                changed = add_to_sale(job_id, client, sale_collection['id'], product, dry_run)
            else:
                changed = remove_from_sale(job_id, client, sale_collection['id'], product, dry_run)
            if changed:
                stats['collection_changed'] += 1
        except Exception as exc:
            stats['errors'] += 1
            log(job_id, f'HATA ÜRÜN: {product.get("title")} | {exc}')

    log(
        job_id,
        'MAĞAZA ÖZET: '
        f'products={stats["products"]} '
        f'variant_updated={stats["variant_updated"]} '
        f'variant_skipped={stats["variant_skipped"]} '
        f'collection_changed={stats["collection_changed"]} '
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
