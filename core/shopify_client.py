import time, requests
from core.config import settings
from core.job_manager import log

def legacy_id_from_gid(gid):
    if not gid: return ''
    return str(gid).rsplit('/',1)[-1]

def get_next_link(response):
    header = response.headers.get('Link','')
    for part in header.split(','):
        if 'rel="next"' in part:
            return part[part.find('<')+1:part.find('>')]
    return None

class ShopifyClient:
    def __init__(self, job_id=None):
        self.job_id = job_id
        self._first_location_id = None
    def _log(self, msg):
        if self.job_id: log(self.job_id, msg)
    def rest_request(self, method, path_or_url, **kwargs):
        url = path_or_url if path_or_url.startswith('http') else f'{settings.base_rest_url}{path_or_url}'
        for attempt in range(8):
            r = requests.request(method, url, headers=settings.headers, timeout=120, **kwargs)
            if r.status_code == 429:
                wait = float(r.headers.get('Retry-After', 2)); self._log(f'REST RATE LIMIT: {wait} sn'); time.sleep(wait); continue
            if 500 <= r.status_code < 600:
                wait = 2 + attempt; self._log(f'REST SERVER {r.status_code}: {wait} sn'); time.sleep(wait); continue
            if r.status_code >= 400:
                raise Exception(f'REST API hata: {r.status_code} | {r.text[:1500]}')
            return r
        raise Exception('REST API isteği başarısız oldu.')
    def gql(self, query, variables=None):
        payload = {'query': query, 'variables': variables or {}}
        for attempt in range(8):
            r = requests.post(settings.graphql_url, headers=settings.headers, json=payload, timeout=120)
            if r.status_code == 429:
                wait = float(r.headers.get('Retry-After', 2)); self._log(f'GRAPHQL RATE LIMIT: {wait} sn'); time.sleep(wait); continue
            if 500 <= r.status_code < 600:
                wait = 2 + attempt; self._log(f'GRAPHQL SERVER {r.status_code}: {wait} sn'); time.sleep(wait); continue
            if r.status_code >= 400:
                raise Exception(f'GraphQL HTTP hata: {r.status_code} | {r.text[:1500]}')
            data = r.json()
            if 'errors' in data:
                txt = str(data['errors'])
                if 'THROTTLED' in txt or 'Throttled' in txt:
                    wait = 2 + attempt; self._log(f'GRAPHQL THROTTLED: {wait} sn'); time.sleep(wait); continue
                raise Exception(f'GraphQL hata: {data["errors"]}')
            return data['data']
        raise Exception('GraphQL isteği başarısız oldu.')
    def iter_rest_pages(self, path):
        url = f'{settings.base_rest_url}{path}'
        while url:
            r = self.rest_request('GET', url)
            yield r
            url = get_next_link(r)
    def find_product_by_handle(self, handle):
        if not handle: return None
        r = self.rest_request('GET', f'/products.json?handle={handle}&limit=1')
        arr = r.json().get('products', [])
        return arr[0] if arr else None
    def find_products_by_sku(self, sku):
        if not sku: return []
        q = '''query($query:String!){ productVariants(first:20, query:$query){ edges{ node{ sku product{ id legacyResourceId title handle } } } } }'''
        data = self.gql(q, {'query': f'sku:{sku}'})
        out=[]
        for e in data.get('productVariants',{}).get('edges',[]):
            n=e['node']
            if str(n.get('sku','')).strip()==str(sku).strip(): out.append(n.get('product'))
        return out
    def find_collection_by_handle(self, handle):
        if not handle: return None
        for path,key,kind in [(f'/custom_collections.json?handle={handle}&limit=1','custom_collections','manual'),(f'/smart_collections.json?handle={handle}&limit=1','smart_collections','smart')]:
            r=self.rest_request('GET', path); arr=r.json().get(key, [])
            if arr:
                arr[0]['_collection_kind']=kind
                return arr[0]
        return None
    def find_page_by_handle(self, handle):
        if not handle: return None
        r=self.rest_request('GET', f'/pages.json?handle={handle}&limit=1')
        arr=r.json().get('pages', [])
        return arr[0] if arr else None
    def first_active_location_id(self):
        if self._first_location_id: return self._first_location_id
        r=self.rest_request('GET','/locations.json')
        locs=[x for x in r.json().get('locations',[]) if x.get('active')]
        if not locs: raise Exception('Aktif lokasyon bulunamadı.')
        self._first_location_id=locs[0]['id']
        self._log(f'Kullanılan lokasyon: {locs[0].get("name")} | ID: {self._first_location_id}')
        return self._first_location_id
