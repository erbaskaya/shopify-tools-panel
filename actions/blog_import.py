import time
from core.config import check_config
from core.file_utils import first_value, parse_bool, read_rows
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient

def all_blogs(client):
    out=[]
    for r in client.iter_rest_pages('/blogs.json?limit=250'):
        out.extend(r.json().get('blogs',[]))
    return out

def find_blog(client, handle):
    for b in all_blogs(client):
        if str(b.get('handle','')).strip()==str(handle).strip(): return b
    return None

def blog_get_create(job_id, client, row, dry_run):
    handle=first_value(row,'blog_handle','blog','blog_slug', default='news')
    title=first_value(row,'blog_title','blog_baslik', default=handle)
    ex=find_blog(client, handle)
    payload={'title':title,'handle':handle}
    if ex:
        if dry_run: log(job_id, f'TEST blog güncellenecekti {title}'); return ex
        payload['id']=ex['id']; b=client.rest_request('PUT', f'/blogs/{ex["id"]}.json', json={'blog':payload}).json().get('blog',ex); log(job_id, f'OK blog güncellendi {title}'); return b
    if dry_run: log(job_id, f'TEST blog oluşturulacaktı {title}'); return {'id':None,'title':title,'handle':handle}
    b=client.rest_request('POST','/blogs.json', json={'blog':payload}).json().get('blog',{})
    log(job_id, f'OK blog oluşturuldu {title}'); return b

def article_map(client, blog_id):
    mp={}
    if not blog_id: return mp
    for r in client.iter_rest_pages(f'/blogs/{blog_id}/articles.json?limit=250'):
        for a in r.json().get('articles',[]):
            if a.get('handle'): mp['h:'+a['handle']]=a
            if a.get('title'): mp['t:'+a['title']]=a
    return mp

def article_payload(row):
    p={}
    aliases={'title':['title','baslik','article_title'],'handle':['handle','slug','article_handle'],'author':['author','yazar'],'tags':['tags','etiketler','tag'],'body_html':['body_html','content','icerik','html'],'summary_html':['summary_html','summary','ozet']}
    for k,als in aliases.items():
        v=first_value(row,*als)
        if v: p[k]=v
    if first_value(row,'published','yayin','aktif'):
        p['published']=parse_bool(first_value(row,'published','yayin','aktif'), True)
    img=first_value(row,'image_src','image','resim','resim_linki')
    if img: p['image']={'src':img}
    return p

def run(job_id, upload_path, dry_run):
    try:
        miss=check_config()
        if miss: raise Exception('Eksik ENV: '+', '.join(miss))
        client=ShopifyClient(job_id); rows=read_rows(upload_path)
        log(job_id, f'Blog import satır={len(rows)} DRY_RUN={dry_run}')
        blog_cache={}; article_cache={}; created=updated=errors=0
        for row in rows:
            try:
                bh=first_value(row,'blog_handle','blog','blog_slug', default='news')
                if bh not in blog_cache: blog_cache[bh]=blog_get_create(job_id, client, row, dry_run)
                blog=blog_cache[bh]; bid=blog.get('id')
                if bh not in article_cache: article_cache[bh]=article_map(client,bid)
                p=article_payload(row); title=p.get('title'); handle=p.get('handle')
                if not title: log(job_id,'ATLANDI title boş'); continue
                ex=article_cache[bh].get('h:'+handle) if handle else None
                ex=ex or article_cache[bh].get('t:'+title)
                if ex:
                    if dry_run: log(job_id, f'TEST yazı güncellenecekti {title}')
                    else: p['id']=ex['id']; client.rest_request('PUT', f'/blogs/{bid}/articles/{ex["id"]}.json', json={'article':p}); log(job_id, f'OK yazı güncellendi {title}')
                    updated+=1
                else:
                    if dry_run: log(job_id, f'TEST yazı oluşturulacaktı {title}')
                    else:
                        a=client.rest_request('POST', f'/blogs/{bid}/articles.json', json={'article':p}).json().get('article',{})
                        if a.get('handle'): article_cache[bh]['h:'+a['handle']]=a
                        if a.get('title'): article_cache[bh]['t:'+a['title']]=a
                        log(job_id, f'OK yazı oluşturuldu {title}')
                    created+=1
                time.sleep(.15)
            except Exception as exc: errors+=1; log(job_id, f'HATA blog: {exc}')
        log(job_id, f'BİTTİ created={created} updated={updated} errors={errors}')
        finish_job(job_id,'done' if errors==0 else 'error')
    except Exception as exc:
        log(job_id, f'GENEL HATA: {exc}'); finish_job(job_id,'error')
