import csv, json
from datetime import datetime
from core.config import check_config
from core.file_utils import make_export_path
from core.job_manager import finish_job, log, set_job_result_file
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

def get_tree(client, mid):
    q='''query($id:ID!){ menu(id:$id){ id title handle items{ id title type resourceId url items{ id title type resourceId url items{ id title type resourceId url items{ id title type resourceId url } } } } } }'''
    return client.gql(q, {'id':mid}).get('menu')

def resource_info(client, rid, cache):
    if not rid: return {'resource_handle':'','resource_title':''}
    if rid in cache: return cache[rid]
    q='''query($id:ID!){ node(id:$id){ ... on Collection{title handle} ... on Product{title handle} ... on Page{title handle} } }'''
    try:
        n=(client.gql(q, {'id':rid}).get('node') or {})
        info={'resource_handle':n.get('handle',''), 'resource_title':n.get('title','')}
    except Exception:
        info={'resource_handle':'','resource_title':''}
    cache[rid]=info; return info

def flatten(client, items, level=1, parent='', rows=None, cache=None):
    rows = rows if rows is not None else []
    cache = cache if cache is not None else {}
    for pos,item in enumerate(items, start=1):
        title=item.get('title',''); rid=item.get('resourceId',''); info=resource_info(client,rid,cache)
        rows.append({'level':level,'position':pos,'parent_path':parent,'title':title,'type':item.get('type',''),'url':item.get('url',''),'resource_id':rid,'resource_handle':info['resource_handle'],'resource_title':info['resource_title']})
        children=item.get('items') or []
        if children: flatten(client, children, level+1, f'{parent} > {title}' if parent else title, rows, cache)
    return rows

def run(job_id, menu_handle, export_format):
    try:
        miss=check_config()
        if miss: raise Exception('Eksik ENV: '+', '.join(miss))
        client=ShopifyClient(job_id); menu_handle=menu_handle.strip(); fmt=(export_format or 'csv').lower()
        menu=get_menu_by_handle(client, menu_handle)
        if not menu: raise Exception(f'Menü bulunamadı: {menu_handle}')
        tree=get_tree(client, menu['id']); rows=flatten(client, tree.get('items',[])); ts=datetime.now().strftime('%Y%m%d_%H%M%S')
        if fmt=='json':
            fn=f'menu_export_{menu_handle}_{ts}.json'; path=make_export_path(fn); path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding='utf-8'); ctype='application/json'
        else:
            fn=f'menu_export_{menu_handle}_{ts}.csv'; path=make_export_path(fn)
            fields=['level','position','parent_path','title','type','url','resource_id','resource_handle','resource_title']
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f, fieldnames=fields, delimiter=';'); w.writeheader(); w.writerows(rows)
            ctype='text/csv'
        set_job_result_file(job_id, path, fn, ctype)
        log(job_id, f'Menü export hazır. Satır={len(rows)} Dosya={fn}')
        finish_job(job_id,'done')
    except Exception as exc:
        log(job_id, f'GENEL HATA: {exc}'); finish_job(job_id,'error')
