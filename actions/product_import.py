import time
from collections import defaultdict
from core.config import check_config
from core.file_utils import first_value, parse_bool, parse_int, price_text, read_rows, split_values
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient

def product_key(row):
    return first_value(row,'handle','urun_handle','product_handle','slug') or first_value(row,'title','baslik','urun_adi','product_title')
def product_fields(row):
    pairs={
        'title': first_value(row,'title','baslik','urun_adi','product_title'),
        'handle': first_value(row,'handle','urun_handle','product_handle','slug'),
        'body_html': first_value(row,'body_html','description','aciklama','html_aciklama'),
        'vendor': first_value(row,'vendor','marka','satici'),
        'product_type': first_value(row,'product_type','type','urun_tipi','kategori'),
        'tags': first_value(row,'tags','tag','etiketler'),
        'status': first_value(row,'status','durum'),
    }
    return {k:v for k,v in pairs.items() if v}
def option_names(rows):
    out=[]
    for i in (1,2,3):
        name=''
        for r in rows:
            name=first_value(r,f'option{i}_name',f'option_{i}_name',f'secenek{i}_adi')
            if name: break
        if name: out.append({'name': name})
    return out
def variant_from_row(row):
    v={}
    for i in (1,2,3):
        val=first_value(row,f'option{i}_value',f'option_{i}_value',f'option{i}',f'secenek{i}')
        if val: v[f'option{i}']=val
    mapping={
        'sku': first_value(row,'sku','variant_sku','varyant_sku','variantnummer','varyant_numarasi'),
        'price': price_text(first_value(row,'price','fiyat','satis_fiyati')),
        'compare_at_price': price_text(first_value(row,'compare_at_price','compare_price','indirim_onceki_fiyat')),
        'barcode': first_value(row,'barcode','gtin','ean'),
        'inventory_policy': first_value(row,'inventory_policy','stok_politikasi'),
        'weight': price_text(first_value(row,'weight','agirlik')),
        'weight_unit': first_value(row,'weight_unit','agirlik_birimi'),
    }
    for k,val in mapping.items():
        if val: v[k]=val
    if first_value(row,'inventory_management','stok_takibi'):
        v['inventory_management']=first_value(row,'inventory_management','stok_takibi')
    elif first_value(row,'inventory_quantity','stok','stok_adedi'):
        v['inventory_management']='shopify'
    if first_value(row,'taxable','vergili'):
        v['taxable']=parse_bool(first_value(row,'taxable','vergili'), True)
    if first_value(row,'requires_shipping','kargo_gerekli'):
        v['requires_shipping']=parse_bool(first_value(row,'requires_shipping','kargo_gerekli'), True)
    return v
def image_list(rows):
    seen=set(); images=[]
    for r in rows:
        for alias in ('image_src','image','resim','resim_linki','image_url','gorsel'):
            for src in split_values(first_value(r, alias)):
                if src and src not in seen:
                    seen.add(src); images.append({'src': src})
    return images
def update_inventory_cost(job_id, client, variant, row, dry_run):
    inv=variant.get('inventory_item_id')
    if not inv: return
    cost=price_text(first_value(row,'cost','maliyet','alis_fiyati'))
    qty=parse_int(first_value(row,'inventory_quantity','stok','stok_adedi'), None)
    if cost:
        if dry_run: log(job_id, f'TEST: maliyet güncellenecekti inv={inv} cost={cost}')
        else: client.rest_request('PUT', f'/inventory_items/{inv}.json', json={'inventory_item':{'id':inv,'cost':cost}})
    if qty is not None:
        loc=client.first_active_location_id()
        if dry_run: log(job_id, f'TEST: stok {qty} yapılacaktı inv={inv}')
        else: client.rest_request('POST','/inventory_levels/set.json', json={'location_id':loc,'inventory_item_id':inv,'available':qty,'disconnect_if_necessary':True})
def create_product(job_id, client, rows, dry_run):
    payload=product_fields(rows[0]); opts=option_names(rows); vars=[variant_from_row(r) for r in rows if variant_from_row(r)]
    if opts: payload['options']=opts
    if vars: payload['variants']=vars
    imgs=image_list(rows)
    if imgs: payload['images']=imgs
    name=payload.get('title') or payload.get('handle')
    if dry_run:
        log(job_id, f'TEST: ürün oluşturulacaktı: {name} varyant={len(vars)} görsel={len(imgs)}'); return
    product=client.rest_request('POST','/products.json', json={'product':payload}).json().get('product',{})
    log(job_id, f'OK: ürün oluşturuldu: {product.get("title")} ID={product.get("id")}')
    for idx,var in enumerate(product.get('variants',[])):
        update_inventory_cost(job_id, client, var, rows[idx] if idx < len(rows) else rows[0], False)
def update_product(job_id, client, existing, rows, dry_run):
    pid=existing['id']; fields=product_fields(rows[0]); fields['id']=pid
    if dry_run: log(job_id, f'TEST: ürün güncellenecekti: {existing.get("title")} ID={pid}')
    else:
        client.rest_request('PUT', f'/products/{pid}.json', json={'product':fields}); log(job_id, f'OK: ürün güncellendi: {existing.get("title")}')
    by_sku={str(v.get('sku','')).strip():v for v in existing.get('variants',[]) if str(v.get('sku','')).strip()}
    for row in rows:
        incoming=variant_from_row(row); sku=incoming.get('sku','')
        if not incoming: continue
        if sku and sku in by_sku:
            var=by_sku[sku]; incoming['id']=var['id']
            if dry_run: log(job_id, f'TEST: varyant güncellenecekti SKU={sku}')
            else:
                nv=client.rest_request('PUT', f'/variants/{var["id"]}.json', json={'variant':incoming}).json().get('variant',var)
                update_inventory_cost(job_id, client, nv, row, False)
        else:
            if dry_run: log(job_id, f'TEST: yeni varyant oluşturulacaktı SKU={sku or "-"}')
            else:
                nv=client.rest_request('POST', f'/products/{pid}/variants.json', json={'variant':incoming}).json().get('variant',{})
                update_inventory_cost(job_id, client, nv, row, False)
        time.sleep(.15)
    for img in image_list(rows):
        if dry_run: log(job_id, f'TEST: görsel eklenecekti {img.get("src")}')
        else:
            try: client.rest_request('POST', f'/products/{pid}/images.json', json={'image':img})
            except Exception as exc: log(job_id, f'UYARI: görsel eklenemedi {exc}')
def run(job_id, upload_path, dry_run):
    try:
        miss=check_config()
        if miss: raise Exception('Eksik ENV: '+', '.join(miss))
        client=ShopifyClient(job_id); rows=read_rows(upload_path)
        if not rows: raise Exception('Dosyada satır yok.')
        log(job_id, f'Ürün import satır={len(rows)} DRY_RUN={dry_run}')
        groups=defaultdict(list)
        for i,r in enumerate(rows, start=2): groups[product_key(r) or f'row_{i}'].append(r)
        created=updated=errors=0
        for key,rs in groups.items():
            try:
                handle=first_value(rs[0],'handle','urun_handle','product_handle','slug')
                existing=client.find_product_by_handle(handle) if handle else None
                if existing: update_product(job_id, client, existing, rs, dry_run); updated+=1
                else: create_product(job_id, client, rs, dry_run); created+=1
            except Exception as exc:
                errors+=1; log(job_id, f'HATA ürün grubu {key}: {exc}')
        log(job_id, f'BİTTİ created={created} updated={updated} errors={errors}')
        finish_job(job_id, 'done' if errors==0 else 'error')
    except Exception as exc:
        log(job_id, f'GENEL HATA: {exc}'); finish_job(job_id,'error')
