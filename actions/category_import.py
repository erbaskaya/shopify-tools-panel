import time
from core.config import check_config
from core.file_utils import first_value, parse_bool, read_rows, split_values
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient

def ctype(row):
    v=first_value(row,'type','collection_type','kategori_tipi','tur', default='manual').lower()
    return 'smart' if v in ('smart','automatic','akilli','otomatik') else 'manual'
def payload(row, kind):
    title=first_value(row,'title','baslik','kategori_adi','name')
    p={'title':title,'sort_order':first_value(row,'sort_order','siralama', default='manual') or 'manual'}
    for key, aliases in {'handle':['handle','slug'], 'body_html':['body_html','description','aciklama']}.items():
        val=first_value(row,*aliases)
        if val: p[key]=val
    if first_value(row,'published','yayin','aktif'):
        p['published']=parse_bool(first_value(row,'published','yayin','aktif'), True)
    img=first_value(row,'image_src','image','resim','resim_linki')
    if img: p['image']={'src':img}
    if kind=='smart':
        tag=first_value(row,'rule_tag','tag','etiket','kural_tag', default=title)
        p['rules']=[{'column':'tag','relation':'equals','condition':tag}]
        p['disjunctive']=False
    return p
def get_custom(client, handle):
    arr=client.rest_request('GET', f'/custom_collections.json?handle={handle}&limit=1').json().get('custom_collections',[])
    return arr[0] if arr else None
def get_smart(client, handle):
    arr=client.rest_request('GET', f'/smart_collections.json?handle={handle}&limit=1').json().get('smart_collections',[])
    return arr[0] if arr else None
def product_ids(job_id, client, row):
    ids=[]
    for x in split_values(first_value(row,'product_ids','urun_idleri','product_id')):
        if str(x).isdigit(): ids.append(int(x))
    for h in split_values(first_value(row,'product_handles','handles','urun_handlelari','urunler')):
        p=client.find_product_by_handle(h)
        if p: ids.append(p['id'])
        else: log(job_id, f'UYARI ürün handle bulunamadı: {h}')
    return list(dict.fromkeys(ids))
def existing_collects(client, collection_id):
    s=set()
    for r in client.iter_rest_pages(f'/collects.json?collection_id={collection_id}&limit=250'):
        for c in r.json().get('collects',[]):
            if c.get('product_id'): s.add(int(c['product_id']))
    return s
def add_collects(job_id, client, collection_id, ids, dry_run):
    if not ids: return 0
    exists=existing_collects(client, collection_id)
    missing=[i for i in ids if int(i) not in exists]
    log(job_id, f'Manuel kategori ürün: zaten={len(ids)-len(missing)} eklenecek={len(missing)}')
    added=0
    for pid in missing:
        if dry_run: log(job_id, f'TEST ürün eklenecekti product_id={pid}'); added+=1
        else:
            try:
                client.rest_request('POST','/collects.json', json={'collect':{'collection_id':collection_id,'product_id':pid}}); added+=1; time.sleep(.12)
            except Exception as exc: log(job_id, f'UYARI collect eklenemedi {pid}: {exc}')
    return added
def run(job_id, upload_path, dry_run):
    try:
        miss=check_config()
        if miss: raise Exception('Eksik ENV: '+', '.join(miss))
        client=ShopifyClient(job_id); rows=read_rows(upload_path)
        if not rows: raise Exception('Dosyada satır yok.')
        log(job_id, f'Kategori import satır={len(rows)} DRY_RUN={dry_run}')
        created=updated=links=errors=0
        for row in rows:
            try:
                kind=ctype(row); title=first_value(row,'title','baslik','kategori_adi','name'); handle=first_value(row,'handle','slug')
                if not title: log(job_id,'ATLANDI başlık yok'); continue
                p=payload(row, kind)
                if kind=='smart':
                    ex=get_smart(client, handle) if handle else None
                    if ex:
                        if dry_run: log(job_id, f'TEST smart güncellenecekti {title}')
                        else: p['id']=ex['id']; client.rest_request('PUT', f'/smart_collections/{ex["id"]}.json', json={'smart_collection':p}); log(job_id, f'OK smart güncellendi {title}')
                        updated+=1
                    else:
                        if dry_run: log(job_id, f'TEST smart oluşturulacaktı {title}')
                        else: client.rest_request('POST','/smart_collections.json', json={'smart_collection':p}); log(job_id, f'OK smart oluşturuldu {title}')
                        created+=1
                else:
                    ex=get_custom(client, handle) if handle else None
                    cid=None
                    if ex:
                        cid=ex['id']
                        if dry_run: log(job_id, f'TEST manuel güncellenecekti {title}')
                        else: p['id']=cid; client.rest_request('PUT', f'/custom_collections/{cid}.json', json={'custom_collection':p}); log(job_id, f'OK manuel güncellendi {title}')
                        updated+=1
                    else:
                        if dry_run: log(job_id, f'TEST manuel oluşturulacaktı {title}')
                        else:
                            col=client.rest_request('POST','/custom_collections.json', json={'custom_collection':p}).json().get('custom_collection',{})
                            cid=col.get('id'); log(job_id, f'OK manuel oluşturuldu {title}')
                        created+=1
                    if cid: links += add_collects(job_id, client, cid, product_ids(job_id, client, row), dry_run)
                time.sleep(.15)
            except Exception as exc:
                errors+=1; log(job_id, f'HATA kategori: {exc}')
        log(job_id, f'BİTTİ created={created} updated={updated} product_links={links} errors={errors}')
        finish_job(job_id,'done' if errors==0 else 'error')
    except Exception as exc:
        log(job_id, f'GENEL HATA: {exc}'); finish_job(job_id,'error')
