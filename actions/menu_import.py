from pathlib import Path
from core.config import check_config
from core.file_utils import first_value, parse_int, read_json, read_rows
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient

def get_menu_by_handle(client, handle):
    q='''query($first:Int!,$after:String){ menus(first:$first, after:$after){ edges{ node{ id handle title } } pageInfo{ hasNextPage endCursor } } }'''
    after=None
    while True:
        data=client.gql(q, {'first':250,'after':after})
        for e in data['menus']['edges']:
            if e['node']['handle']==handle: return e['node']
        pi=data['menus']['pageInfo']
        if not pi['hasNextPage']: break
        after=pi['endCursor']
    return None

def resolve_resource_id(job_id, client, typ, handle):
    typ=(typ or '').upper(); handle=(handle or '').strip()
    if not handle: return ''
    if typ=='COLLECTION':
        c=client.find_collection_by_handle(handle)
        if c: return c.get('admin_graphql_api_id') or f'gid://shopify/Collection/{c["id"]}'
    if typ=='PRODUCT':
        p=client.find_product_by_handle(handle)
        if p: return p.get('admin_graphql_api_id') or f'gid://shopify/Product/{p["id"]}'
    if typ=='PAGE':
        p=client.find_page_by_handle(handle)
        if p: return p.get('admin_graphql_api_id') or f'gid://shopify/Page/{p["id"]}'
    log(job_id, f'UYARI resource bulunamadı type={typ} handle={handle}')
    return ''

def item_from_row(job_id, client, row):
    title=first_value(row,'title','baslik'); typ=first_value(row,'type','tur', default='HTTP').upper(); url=first_value(row,'url','link'); rid=first_value(row,'resource_id','resourceid'); rh=first_value(row,'resource_handle','handle','kaynak_handle')
    if not title: raise Exception('title boş')
    item={'title':title,'type':typ,'items':[]}
    if typ=='HTTP': item['url']=url or '#'
    elif typ in ('COLLECTION','PRODUCT','PAGE'):
        rid = rid or resolve_resource_id(job_id, client, typ, rh)
        if not rid: raise Exception(f'resource_id yok title={title}')
        item['resourceId']=rid
    else:
        if url: item['url']=url
        if rid: item['resourceId']=rid
    return item

def build_csv(job_id, client, path):
    rows=read_rows(path); root=[]; stack={}
    if not rows: raise Exception('Menü import dosyasında satır yok')
    for row in rows:
        level=parse_int(first_value(row,'level','seviye'),1) or 1
        item=item_from_row(job_id, client, row)
        if level==1 or (level-1) not in stack: root.append(item)
        else: stack[level-1].setdefault('items',[]).append(item)
        stack[level]=item
        for k in list(stack.keys()):
            if k>level: del stack[k]
    return root

def clean_json(items):
    out=[]
    for s in items:
        typ=s.get('type','HTTP'); it={'title':s.get('title',''), 'type':typ, 'items':clean_json(s.get('items') or [])}
        if typ=='HTTP': it['url']=s.get('url') or '#'
        elif s.get('resourceId'): it['resourceId']=s.get('resourceId')
        elif s.get('url'): it['url']=s.get('url')
        out.append(it)
    return out

def count(items):
    return sum(1+count(i.get('items') or []) for i in items)

def menu_update(client, mid, title, handle, items):
    m='''mutation($id:ID!,$title:String,$handle:String,$items:[MenuItemUpdateInput!]!){ menuUpdate(id:$id,title:$title,handle:$handle,items:$items){ menu{id title handle} userErrors{field message} } }'''
    return client.gql(m, {'id':mid,'title':title,'handle':handle,'items':items})['menuUpdate']
def menu_create(client, title, handle, items):
    m='''mutation($title:String!,$handle:String!,$items:[MenuItemCreateInput!]!){ menuCreate(title:$title,handle:$handle,items:$items){ menu{id title handle} userErrors{field message} } }'''
    return client.gql(m, {'title':title,'handle':handle,'items':items})['menuCreate']
def run(job_id, upload_path, menu_handle, menu_title, dry_run):
    try:
        miss=check_config()
        if miss: raise Exception('Eksik ENV: '+', '.join(miss))
        client=ShopifyClient(job_id); menu_handle=menu_handle.strip(); path=Path(upload_path)
        if path.suffix.lower()=='.json':
            data=read_json(path); items=clean_json(data.get('items',[])); menu_title=menu_title or data.get('title') or menu_handle
        else:
            items=build_csv(job_id, client, path); menu_title=menu_title or menu_handle
        log(job_id, f'Menü import hazır handle={menu_handle} title={menu_title} item={count(items)} DRY_RUN={dry_run}')
        existing=get_menu_by_handle(client, menu_handle)
        if dry_run:
            log(job_id, 'TEST: menü güncellenecek/oluşturulacak'); finish_job(job_id,'done'); return
        res=menu_update(client, existing['id'], menu_title, menu_handle, items) if existing else menu_create(client, menu_title, menu_handle, items)
        if res.get('userErrors'): raise Exception(res.get('userErrors'))
        log(job_id, 'OK menü import tamamlandı')
        finish_job(job_id,'done')
    except Exception as exc:
        log(job_id, f'GENEL HATA: {exc}'); finish_job(job_id,'error')
