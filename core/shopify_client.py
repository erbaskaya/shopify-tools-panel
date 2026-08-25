import time
import requests
from core.config import settings
from core.job_manager import log


def legacy_id_from_gid(gid):
    if not gid:
        return ''
    return str(gid).rsplit('/', 1)[-1]


def get_next_link(response):
    header = response.headers.get('Link', '')
    for part in header.split(','):
        if 'rel="next"' in part:
            return part[part.find('<') + 1:part.find('>')]
    return None


class ShopifyClient:
    def __init__(self, job_id=None, store=None):
        self.job_id = job_id
        self.store = store or settings.get_store()
        self._first_location_id = None
        if not self.store:
            raise Exception('Shopify mağaza ayarı bulunamadı.')

    @property
    def base_rest_url(self):
        return self.store.base_rest_url

    @property
    def graphql_url(self):
        return self.store.graphql_url

    @property
    def headers(self):
        return self.store.headers

    def _log(self, msg):
        if self.job_id:
            log(self.job_id, msg)

    def rest_request(self, method, path_or_url, **kwargs):
        url = path_or_url if path_or_url.startswith('http') else f'{self.base_rest_url}{path_or_url}'
        for attempt in range(8):
            r = requests.request(method, url, headers=self.headers, timeout=120, **kwargs)
            if r.status_code == 429:
                wait = float(r.headers.get('Retry-After', 2))
                self._log(f'REST RATE LIMIT: {wait} sn')
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                wait = 2 + attempt
                self._log(f'REST SERVER {r.status_code}: {wait} sn')
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise Exception(f'REST API hata: {r.status_code} | {r.text[:1500]}')
            return r
        raise Exception('REST API isteği başarısız oldu.')

    def gql(self, query, variables=None):
        payload = {'query': query, 'variables': variables or {}}
        for attempt in range(8):
            r = requests.post(self.graphql_url, headers=self.headers, json=payload, timeout=120)
            if r.status_code == 429:
                wait = float(r.headers.get('Retry-After', 2))
                self._log(f'GRAPHQL RATE LIMIT: {wait} sn')
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                wait = 2 + attempt
                self._log(f'GRAPHQL SERVER {r.status_code}: {wait} sn')
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise Exception(f'GraphQL HTTP hata: {r.status_code} | {r.text[:1500]}')
            data = r.json()
            if 'errors' in data:
                txt = str(data['errors'])
                if 'THROTTLED' in txt or 'Throttled' in txt:
                    wait = 2 + attempt
                    self._log(f'GRAPHQL THROTTLED: {wait} sn')
                    time.sleep(wait)
                    continue
                raise Exception(f'GraphQL hata: {data["errors"]}')
            return data['data']
        raise Exception('GraphQL isteği başarısız oldu.')

    def iter_rest_pages(self, path):
        url = path if str(path).startswith('http') else f'{self.base_rest_url}{path}'
        while url:
            r = self.rest_request('GET', url)
            yield r
            url = get_next_link(r)

    def find_product_by_handle(self, handle):
        if not handle:
            return None
        r = self.rest_request('GET', f'/products.json?handle={handle}&limit=1')
        arr = r.json().get('products', [])
        return arr[0] if arr else None

    def find_products_by_sku(self, sku):
        if not sku:
            return []
        query = '''query($query:String!){ productVariants(first:20, query:$query){ edges{ node{ sku product{ id legacyResourceId title handle } } } } }'''
        data = self.gql(query, {'query': f'sku:{sku}'})
        out = []
        for edge in data.get('productVariants', {}).get('edges', []):
            node = edge['node']
            if str(node.get('sku', '')).strip() == str(sku).strip():
                out.append(node.get('product'))
        return out

    def find_collection_by_handle(self, handle):
        if not handle:
            return None
        paths = [
            (f'/custom_collections.json?handle={handle}&limit=1', 'custom_collections', 'manual'),
            (f'/smart_collections.json?handle={handle}&limit=1', 'smart_collections', 'smart'),
        ]
        for path, key, kind in paths:
            r = self.rest_request('GET', path)
            arr = r.json().get(key, [])
            if arr:
                arr[0]['_collection_kind'] = kind
                return arr[0]
        return None

    def list_collections(self):
        out = []
        paths = [
            ('/custom_collections.json?limit=250&fields=id,title,handle', 'custom_collections', 'manual'),
            ('/smart_collections.json?limit=250&fields=id,title,handle', 'smart_collections', 'smart'),
        ]
        for path, key, kind in paths:
            for response in self.iter_rest_pages(path):
                for item in response.json().get(key, []):
                    item['_collection_kind'] = kind
                    out.append(item)
        return sorted(out, key=lambda x: str(x.get('title', '')).lower())

    def list_vendors(self):
        vendors = set()
        for response in self.iter_rest_pages('/products.json?limit=250&fields=vendor'):
            for product in response.json().get('products', []):
                vendor = str(product.get('vendor') or '').strip()
                if vendor:
                    vendors.add(vendor)
        return sorted(vendors, key=str.lower)

    def search_products(self, text='', limit=50):
        text = str(text or '').strip()
        query_text = None
        if text:
            safe = text.replace('\\', ' ').replace('"', ' ').strip()
            query_text = f'title:{safe}* OR handle:{safe}* OR sku:{safe}*'
        query = '''query($first:Int!,$query:String){
          products(first:$first, query:$query, sortKey:TITLE){
            edges{ node{ id legacyResourceId title handle vendor status
              variants(first:5){edges{node{sku price compareAtPrice}}}
            }}
          }
        }'''
        data = self.gql(query, {'first': int(limit), 'query': query_text})
        out = []
        for edge in data.get('products', {}).get('edges', []):
            node = edge.get('node', {})
            variants = []
            for variant_edge in node.get('variants', {}).get('edges', []):
                variants.append(variant_edge.get('node', {}))
            node['variants_preview'] = variants
            out.append(node)
        return out

    def first_active_location_id(self):
        if self._first_location_id:
            return self._first_location_id
        r = self.rest_request('GET', '/locations.json')
        locs = [x for x in r.json().get('locations', []) if x.get('active')]
        if not locs:
            raise Exception('Aktif lokasyon bulunamadı.')
        self._first_location_id = locs[0]['id']
        self._log(f'Kullanılan lokasyon: {locs[0].get("name")} | ID: {self._first_location_id}')
        return self._first_location_id
