import time
from core.config import check_config
from core.file_utils import first_value, read_rows
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient, legacy_id_from_gid

def find_product_id(job_id, client, row):
    pid=first_value(row,'product_id','urun_id','id')
    if pid: return legacy_id_from_gid(pid)
    handle=first_value(row,'handle','product_handle','urun_handle')
    if handle:
        p=client.find_product_by_handle(handle)
        if p: return p['id']
        log(job_id, f'UYARI handle bulunamadı {handle}'); return None
    sku=first_value(row,'sku','variant_sku','varyant_sku','variantnummer','varyant_numarasi')
    if sku:
        ps=client.find_products_by_sku(sku)
        if ps: return ps[0].get('legacyResourceId') or legacy_id_from_gid(ps[0].get('id'))
        log(job_id, f'UYARI SKU bulunamadı {sku}')
    return None

def run(job_id, upload_path, dry_run):
    try:
        miss=check_config()
        if miss: raise Exception('Eksik ENV: '+', '.join(miss))
        client=ShopifyClient(job_id); rows=read_rows(upload_path)
        log(job_id, f'Vendor import satır={len(rows)} DRY_RUN={dry_run}')
        updated=skipped=errors=0
        for row in rows:
            try:
                vendor=first_value(row,'vendor','marka','satici','tedarikci')
                if not vendor: skipped+=1; log(job_id,'ATLANDI vendor boş'); continue
                pid=find_product_id(job_id, client, row)
                if not pid: skipped+=1; continue
                if dry_run: log(job_id, f'TEST vendor güncellenecekti product_id={pid} vendor={vendor}')
                else: client.rest_request('PUT', f'/products/{pid}.json', json={'product':{'id':pid,'vendor':vendor}}); log(job_id, f'OK vendor güncellendi product_id={pid}')
                updated+=1; time.sleep(.12)
            except Exception as exc: errors+=1; log(job_id, f'HATA vendor: {exc}')
        log(job_id, f'BİTTİ updated={updated} skipped={skipped} errors={errors}')
        finish_job(job_id,'done' if errors==0 else 'error')
    except Exception as exc:
        log(job_id, f'GENEL HATA: {exc}'); finish_job(job_id,'error')
