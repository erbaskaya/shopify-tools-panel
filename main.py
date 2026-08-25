from pathlib import Path
from typing import List

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, PlainTextResponse

from core.auth import clear_login_cookie, is_logged_in, set_login_cookie
from core.config import check_config, get_store, get_stores, settings
from core.file_utils import save_upload_file
from core.job_manager import create_job, get_job, list_jobs, run_thread
from core.shopify_client import ShopifyClient
from actions.stock_update import run as run_stock_update
from actions.category_sync import run as run_category_sync
from actions.product_import import run as run_product_import
from actions.category_import import run as run_category_import
from actions.menu_export import run as run_menu_export
from actions.menu_import import run as run_menu_import
from actions.blog_import import run as run_blog_import
from actions.vendor_import import run as run_vendor_import
from actions.sale_manager import run as run_sale_manager

app = FastAPI(title='Shopify Tools Panel V3')


def e(v):
    import html
    return html.escape(str(v or ''))


def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse('/', status_code=303)
    return None


def layout(title, body, request=None, refresh=None):
    meta = f'<meta http-equiv="refresh" content="{int(refresh)}">' if refresh else ''
    if request and is_logged_in(request):
        nav = '''<div class="nav"><a href="/dashboard">Panel</a><a href="/sale">Sale Yönetimi</a><a href="/logout">Çıkış</a></div>'''
    else:
        nav = ''
    return HTMLResponse(f'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{e(title)}</title>
<style>
:root{{--bg:#f4f6fb;--card:#fff;--text:#111827;--muted:#6b7280;--border:#e5e7eb;--primary:#111827;--hover:#374151;--danger:#b91c1c;--success:#166534}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text)}}.header{{background:#fff;border-bottom:1px solid var(--border);padding:15px 28px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:5}}.brand{{font-weight:800;font-size:18px}}.version{{font-size:12px;color:var(--muted);margin-left:8px}}.nav{{display:flex;gap:8px;align-items:center}}.nav a,.top-link{{color:var(--text);text-decoration:none;font-size:14px;border:1px solid var(--border);padding:8px 12px;border-radius:10px;background:#fff}}.nav a:hover{{background:#f8fafc}}.wrap{{width:min(1220px,calc(100% - 32px));margin:26px auto}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.grid3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}}@media(max-width:980px){{.grid3{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:760px){{.grid,.grid3{{grid-template-columns:1fr}}.wrap{{width:calc(100% - 24px)}}.header{{padding:12px;align-items:flex-start;gap:10px;flex-direction:column}}.nav{{flex-wrap:wrap}}}}.card{{background:#fff;border:1px solid var(--border);border-radius:18px;padding:22px;box-shadow:0 12px 30px rgba(15,23,42,.06)}}h1{{margin:0 0 18px;font-size:28px}}h2{{margin:0 0 12px;font-size:21px}}h3{{margin:24px 0 14px;font-size:20px}}p{{color:var(--muted);line-height:1.5}}label{{display:block;font-weight:700;margin:14px 0 7px}}input[type=text],input[type=number],input[type=password],select,textarea{{width:100%;border:1px solid var(--border);border-radius:12px;padding:12px 13px;font-size:15px;background:#fff}}textarea{{min-height:110px;resize:vertical}}input[type=file]{{width:100%;border:1px dashed #cbd5e1;border-radius:12px;padding:12px;background:#f8fafc}}.check-row{{display:flex;align-items:center;gap:9px;margin:12px 0;color:var(--muted);font-size:14px;font-weight:700}}.check-row input{{flex:0 0 auto}}button,.btn{{display:inline-flex;align-items:center;justify-content:center;width:100%;border:0;border-radius:12px;padding:13px 16px;background:var(--primary);color:#fff;font-weight:800;font-size:15px;cursor:pointer;text-decoration:none;margin-top:14px}}button:hover,.btn:hover{{background:var(--hover)}}.btn-light{{background:#fff;color:var(--text);border:1px solid var(--border)}}.btn-danger{{background:var(--danger)}}.alert{{padding:14px 16px;border-radius:14px;border:1px solid var(--border);background:#fff7ed;color:#9a3412;margin-bottom:18px}}.ok{{background:#ecfdf5;color:#166534;border-color:#bbf7d0}}.muted{{color:var(--muted)}}.small{{font-size:13px}}.pill{{display:inline-block;padding:6px 10px;border-radius:99px;font-size:13px;font-weight:800;background:#eef2ff;color:#3730a3;margin:4px 6px 4px 0}}.status-running{{background:#fff7ed;color:#9a3412}}.status-done{{background:#ecfdf5;color:#166534}}.status-error{{background:#fef2f2;color:#991b1b}}pre{{background:#0b1020;color:#e5e7eb;padding:18px;border-radius:16px;overflow:auto;white-space:pre-wrap;line-height:1.45;min-height:360px;font-size:13px}}.jobs-list a{{display:block;color:var(--text);text-decoration:none;border:1px solid var(--border);border-radius:14px;padding:14px;margin:10px 0;background:#fff}}.hint{{background:#f8fafc;border:1px dashed #cbd5e1;padding:12px;border-radius:12px;color:#475569;font-size:13px}}.store-box,.product-box{{border:1px solid var(--border);border-radius:14px;padding:12px;background:#fafafa}}.store-box{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 14px}}.product-list{{max-height:430px;overflow:auto;border:1px solid var(--border);border-radius:14px;background:#fff}}.product-row{{display:grid;grid-template-columns:28px 1fr auto;gap:10px;align-items:center;padding:12px;border-bottom:1px solid var(--border)}}.product-row:last-child{{border-bottom:0}}.product-title{{font-weight:800}}.filter-section{{display:none}}.filter-section.active{{display:block}}.sale-card{{border-top:4px solid #dc2626}}.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}@media(max-width:760px){{.two-col,.store-box{{grid-template-columns:1fr}}}}
</style></head><body><div class="header"><div class="brand">Shopify Tools Panel <span class="version">v3 + Sale</span></div>{nav}</div><main class="wrap">{body}</main></body></html>''')


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    if is_logged_in(request):
        return RedirectResponse('/dashboard', status_code=303)
    miss = check_config()
    warn = ''
    if miss:
        warn = f'<div class="alert">Eksik Environment Variables: <b>{e(", ".join(miss))}</b></div>'
    return layout('Giriş', f'''<div class="card" style="max-width:520px;margin:80px auto"><h1>Giriş</h1>{warn}<p>Panel şifresini gir.</p><form method="post" action="/login"><label>Panel Şifresi</label><input type="password" name="password" required><button>Giriş Yap</button></form></div>''', request)


@app.post('/login')
def login(password: str = Form(...)):
    import hmac
    if not settings.PANEL_PASSWORD:
        return PlainTextResponse('PANEL_PASSWORD env ayarı eksik.', status_code=500)
    if not hmac.compare_digest(password, settings.PANEL_PASSWORD):
        return HTMLResponse('<h2>Şifre yanlış</h2><p><a href="/">Tekrar dene</a></p>', status_code=401)
    response = RedirectResponse('/dashboard', status_code=303)
    set_login_cookie(response)
    return response


@app.get('/logout')
def logout():
    response = RedirectResponse('/', status_code=303)
    clear_login_cookie(response)
    return response


def file_form(action, label, accept='.csv,.xlsx,.xlsm'):
    return f'''<form method="post" action="{action}" enctype="multipart/form-data"><label>{label}</label><input type="file" name="file" accept="{accept}" required><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Test modu</label><button type="submit">Başlat</button></form>'''


@app.get('/dashboard', response_class=HTMLResponse)
def dashboard(request: Request):
    red = require_login(request)
    if red:
        return red
    miss = check_config()
    stores = get_stores()
    if miss:
        cfg = f'<div class="alert">Eksik ayarlar: <b>{e(", ".join(miss))}</b></div>'
    else:
        names = ', '.join(f'{s.name} ({s.domain})' for s in stores)
        cfg = f'<div class="alert ok">Ayarlar hazır. Mağaza sayısı: <b>{len(stores)}</b> | {e(names)}</div>'
    jobs = ''
    recent = list_jobs(10)
    if recent:
        items = []
        for job in recent:
            dl = '<span class="pill status-done">download</span>' if job.get('result_file_path') else ''
            items.append(f'<a href="/jobs/{e(job["id"])}"><b>{e(job["title"])}</b><br><span class="pill status-{e(job["status"])}">{e(job["status"])}</span>{dl}<span class="muted small">Başlangıç: {e(job["created_at"])}</span></a>')
        jobs = f'<div class="card" style="margin-top:18px"><h2>Son İşlemler</h2><div class="jobs-list">{"".join(items)}</div></div>'
    body = f'''
<h1>Shopify İşlem Paneli</h1>{cfg}
<div class="card sale-card" style="margin-bottom:18px"><h2>Sale / İndirim Yönetimi</h2><p>Kategori, satıcı/marka veya tek tek ürün seçerek indirim uygula; ürünleri <b>collections/sale</b> kategorisine ekle. İstersen aynı filtrelerle işlemi tersine çevir.</p><a class="btn" href="/sale">Sale Yönetimini Aç</a></div>
<div class="alert">Sunucu bilgisayarındaki <b>C:\\...</b> veya <b>D:\\...</b> dosya yolunu okuyamaz. Import için dosya seçme butonunu kullan.</div>
<h3>Hızlı Araçlar</h3><div class="grid">
<div class="card"><h2>Tüm Varyant Stoklarını Ayarla</h2><p>Tüm varyant stoklarını seçtiğin değere çeker.</p><form method="post" action="/actions/stocks"><label>Hedef stok miktarı</label><input type="number" name="stock_value" value="5" min="0" required><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Test modu</label><button>Stok İşlemini Başlat</button></form></div>
<div class="card"><h2>Alt Kategori Ürünlerini Üst Kategorilere Ekle</h2><p>Menü hiyerarşisine göre alt koleksiyon ürünlerini üst koleksiyonlara ekler.</p><form method="post" action="/actions/categories"><label>Shopify menü handle</label><input type="text" name="menu_handle" placeholder="main-menu" required><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Test modu</label><button>Kategori İşlemini Başlat</button></form></div>
</div>
<h3>Import / Export Tools</h3><div class="grid3">
<div class="card"><h2>1. Ürün Import</h2><p>Handle varsa günceller, yoksa yeni ürün açar.</p>{file_form('/actions/product-import','Ürün dosyası')}</div>
<div class="card"><h2>2. Kategori Import</h2><p>Manual ve smart kategori. Smart kuralı: ürün tag = rule_tag/kategori adı.</p>{file_form('/actions/category-import','Kategori dosyası')}</div>
<div class="card"><h2>3. Menü Export</h2><p>Menüyü CSV veya JSON indirilebilir dosya yapar.</p><form method="post" action="/actions/menu-export"><label>Menü handle</label><input type="text" name="menu_handle" placeholder="main-menu" required><label>Format</label><select name="export_format"><option value="csv">CSV</option><option value="json">JSON</option></select><button>Menü Export Başlat</button></form></div>
<div class="card"><h2>4. Menü Import</h2><p>Export edilmiş CSV/JSON menüyü içeri alır.</p><form method="post" action="/actions/menu-import" enctype="multipart/form-data"><label>Menü handle</label><input type="text" name="menu_handle" placeholder="main-menu" required><label>Menü başlığı</label><input type="text" name="menu_title" placeholder="Main menu"><label>Menü dosyası</label><input type="file" name="file" accept=".csv,.json" required><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Test modu</label><button>Menü Import Başlat</button></form></div>
<div class="card"><h2>5. Blog Import</h2><p>Blog ve blog yazısı oluşturur/günceller.</p>{file_form('/actions/blog-import','Blog dosyası')}</div>
<div class="card"><h2>6. Vendor Ekle / Güncelle</h2><p>handle, SKU veya product_id ile vendor günceller.</p>{file_form('/actions/vendor-import','Vendor dosyası')}</div>
</div>
<div class="card" style="margin-top:18px"><h2>Dosya Şablonları</h2><p>ZIP içinde <b>sample_templates/</b> klasöründe örnek CSV dosyaları var.</p></div>{jobs}'''
    return layout('Dashboard', body, request)


def _sale_reference_data(store_key, product_q):
    store = get_store(store_key)
    if not store:
        return [], [], [], 'Mağaza ayarı bulunamadı.'
    try:
        client = ShopifyClient(store=store)
        collections = client.list_collections()
        vendors = client.list_vendors()
        products = client.search_products(product_q, 50)
        return collections, vendors, products, ''
    except Exception as exc:
        return [], [], [], str(exc)


@app.get('/sale', response_class=HTMLResponse)
def sale_page(request: Request, source_store: str = '', q: str = ''):
    red = require_login(request)
    if red:
        return red

    stores = get_stores()
    if not source_store and stores:
        source_store = stores[0].key
    collections, vendors, products, load_error = _sale_reference_data(source_store, q) if stores else ([], [], [], '')

    store_options = ''.join(
        f'<option value="{e(s.key)}" {"selected" if s.key == source_store else ""}>{e(s.name)} — {e(s.domain)}</option>'
        for s in stores
    )
    target_checks = ''.join(
        f'<label class="check-row"><input type="checkbox" name="store_keys" value="{e(s.key)}" checked> {e(s.name)} <span class="muted small">{e(s.domain)}</span></label>'
        for s in stores
    ) or '<div class="alert">Mağaza tanımı yok.</div>'

    collection_options = ''.join(
        f'<option value="{e(c.get("handle"))}">{e(c.get("title"))} — /collections/{e(c.get("handle"))}</option>'
        for c in collections if c.get('handle') != 'sale'
    )
    vendor_options = ''.join(f'<option value="{e(v)}">{e(v)}</option>' for v in vendors)

    product_rows = []
    for product in products:
        preview = product.get('variants_preview') or []
        sku = ', '.join(str(v.get('sku') or '') for v in preview if v.get('sku'))
        product_rows.append(
            f'''<label class="product-row"><input type="checkbox" name="product_handles" value="{e(product.get('handle'))}"><span><span class="product-title">{e(product.get('title'))}</span><br><span class="muted small">/{e(product.get('handle'))} · {e(product.get('vendor'))}{(' · SKU: ' + e(sku)) if sku else ''}</span></span><span class="pill">{e(product.get('status'))}</span></label>'''
        )
    products_html = ''.join(product_rows) or '<div class="hint">Ürün bulunamadı. Arama alanından ürün adı, handle veya SKU ile arayın.</div>'
    load_alert = f'<div class="alert">Shopify verileri yüklenemedi: {e(load_error)}</div>' if load_error else ''

    body = f'''
<h1>Sale / İndirim Yönetimi</h1>
<div class="alert ok"><b>İşleyiş:</b> İndirim uygulamada mevcut satış fiyatı karşılaştırmalı fiyata taşınır. Örn. 100,00 € + %20 → <b>Price 80,00 €</b>, <b>Compare-at 100,00 €</b>. Geri almada Compare-at tekrar Price olur ve Compare-at temizlenir.</div>
{load_alert}
<div class="card" style="margin-bottom:18px"><h2>Filtre verilerini hangi mağazadan gösterelim?</h2><form method="get" action="/sale"><div class="two-col"><div><label>Referans mağaza</label><select name="source_store">{store_options}</select></div><div><label>Ürün ara</label><input type="text" name="q" value="{e(q)}" placeholder="Ürün adı, handle veya SKU"></div></div><button class="btn-light">Listeyi Yenile / Ara</button></form><p class="small">Seçtiğiniz kategori handle'ı, vendor adı veya ürün handle'ları hedef mağazalarda eşleştirilir.</p></div>
<form method="post" action="/actions/sale" id="saleForm">
<div class="grid">
<div class="card"><h2>1. Hedef Mağazalar</h2><div class="store-box">{target_checks}</div><p class="small">Birden fazla mağazaya aynı işlem tek seferde uygulanabilir.</p></div>
<div class="card"><h2>2. İşlem</h2><label>İşlem tipi</label><select name="operation" id="operation"><option value="apply">İndirim uygula + Sale kategorisine ekle</option><option value="restore">İndirimi kaldır + Sale kategorisinden çıkar</option></select><div id="discountBox"><label>İndirim yüzdesi</label><input type="number" name="discount_percent" value="20" min="0.01" max="99.99" step="0.01"></div><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Önce test modu (önerilir)</label></div>
</div>
<div class="card" style="margin-top:18px"><h2>3. Ürünleri Nasıl Seçeceğiz?</h2><label>Filtre tipi</label><select name="filter_mode" id="filterMode"><option value="collection">Kategoriye göre</option><option value="vendor">Satıcı / markaya göre</option><option value="products">Tek tek ürün seç</option></select>
<div id="filter-collection" class="filter-section active"><label>Kategori</label><select name="collection_handle"><option value="">Kategori seçin</option>{collection_options}</select></div>
<div id="filter-vendor" class="filter-section"><label>Satıcı / Marka</label><select name="vendor"><option value="">Satıcı / marka seçin</option>{vendor_options}</select></div>
<div id="filter-products" class="filter-section"><label>Ürünler</label><div class="product-list">{products_html}</div><p class="small">En fazla 50 arama sonucu gösterilir. Başka ürünler için yukarıdaki ürün aramasını kullanın.</p></div>
<button type="submit">İşlemi Başlat</button></div>
</form>
<script>
(function(){{
  const filterMode=document.getElementById('filterMode');
  const operation=document.getElementById('operation');
  function syncFilter(){{document.querySelectorAll('.filter-section').forEach(x=>x.classList.remove('active'));const el=document.getElementById('filter-'+filterMode.value);if(el)el.classList.add('active');}}
  function syncOperation(){{document.getElementById('discountBox').style.display=operation.value==='apply'?'block':'none';}}
  filterMode.addEventListener('change',syncFilter);operation.addEventListener('change',syncOperation);syncFilter();syncOperation();
}})();
</script>'''
    return layout('Sale Yönetimi', body, request)


def start_job(title, func, *args):
    job_id = create_job(title)
    run_thread(func, job_id, *args)
    return RedirectResponse(f'/jobs/{job_id}', status_code=303)


@app.post('/actions/sale')
def a_sale(
    request: Request,
    store_keys: List[str] = Form(...),
    operation: str = Form(...),
    discount_percent: float = Form(20),
    filter_mode: str = Form(...),
    collection_handle: str = Form(''),
    vendor: str = Form(''),
    product_handles: List[str] = Form([]),
    dry_run: str = Form(None),
):
    red = require_login(request)
    if red:
        return red
    dry = dry_run == '1'
    filter_value = collection_handle.strip() if filter_mode == 'collection' else vendor.strip() if filter_mode == 'vendor' else ''
    action_text = 'İndirim uygula' if operation == 'apply' else 'İndirimi kaldır'
    title = f'Sale: {action_text} | {filter_mode}' + (' - TEST' if dry else '')
    return start_job(
        title,
        run_sale_manager,
        list(store_keys),
        operation,
        discount_percent,
        filter_mode,
        filter_value,
        list(product_handles),
        dry,
    )


@app.post('/actions/stocks')
def a_stocks(request: Request, stock_value: int = Form(...), dry_run: str = Form(None)):
    red = require_login(request)
    if red:
        return red
    dry = dry_run == '1'
    return start_job(f'Stokları {stock_value} yap' + (' - TEST' if dry else ''), run_stock_update, stock_value, dry)


@app.post('/actions/categories')
def a_categories(request: Request, menu_handle: str = Form(...), dry_run: str = Form(None)):
    red = require_login(request)
    if red:
        return red
    dry = dry_run == '1'
    return start_job(f'Alt kategorileri üstlere ekle: {menu_handle}' + (' - TEST' if dry else ''), run_category_sync, menu_handle, dry)


@app.post('/actions/product-import')
def a_product(request: Request, file: UploadFile = File(...), dry_run: str = Form(None)):
    red = require_login(request)
    if red:
        return red
    path = save_upload_file(file, 'product_import')
    dry = dry_run == '1'
    return start_job('Ürün import' + (' - TEST' if dry else ''), run_product_import, str(path), dry)


@app.post('/actions/category-import')
def a_catimp(request: Request, file: UploadFile = File(...), dry_run: str = Form(None)):
    red = require_login(request)
    if red:
        return red
    path = save_upload_file(file, 'category_import')
    dry = dry_run == '1'
    return start_job('Kategori import' + (' - TEST' if dry else ''), run_category_import, str(path), dry)


@app.post('/actions/menu-export')
def a_menuexp(request: Request, menu_handle: str = Form(...), export_format: str = Form('csv')):
    red = require_login(request)
    if red:
        return red
    return start_job(f'Menü export: {menu_handle}', run_menu_export, menu_handle, export_format)


@app.post('/actions/menu-import')
def a_menuimp(request: Request, file: UploadFile = File(...), menu_handle: str = Form(...), menu_title: str = Form(''), dry_run: str = Form(None)):
    red = require_login(request)
    if red:
        return red
    path = save_upload_file(file, 'menu_import')
    dry = dry_run == '1'
    return start_job(f'Menü import: {menu_handle}' + (' - TEST' if dry else ''), run_menu_import, str(path), menu_handle, menu_title, dry)


@app.post('/actions/blog-import')
def a_blog(request: Request, file: UploadFile = File(...), dry_run: str = Form(None)):
    red = require_login(request)
    if red:
        return red
    path = save_upload_file(file, 'blog_import')
    dry = dry_run == '1'
    return start_job('Blog import' + (' - TEST' if dry else ''), run_blog_import, str(path), dry)


@app.post('/actions/vendor-import')
def a_vendor(request: Request, file: UploadFile = File(...), dry_run: str = Form(None)):
    red = require_login(request)
    if red:
        return red
    path = save_upload_file(file, 'vendor_import')
    dry = dry_run == '1'
    return start_job('Vendor import' + (' - TEST' if dry else ''), run_vendor_import, str(path), dry)


@app.get('/jobs/{job_id}', response_class=HTMLResponse)
def job_page(job_id: str, request: Request):
    red = require_login(request)
    if red:
        return red
    job = get_job(job_id)
    if not job:
        return layout('İş bulunamadı', '<div class="card"><h1>İş bulunamadı</h1><a class="btn btn-light" href="/dashboard">Panele dön</a></div>', request)
    refresh = 3 if job['status'] == 'running' else None
    dl = f'<a class="btn" href="/download/{e(job_id)}">Export Dosyasını İndir: {e(job.get("result_file_name"))}</a>' if job.get('result_file_path') and job['status'] == 'done' else ''
    logs = '\n'.join(job.get('logs', []))
    body = f'<div class="card"><h1>{e(job["title"])}</h1><p><span class="pill status-{e(job["status"])}">{e(job["status"])}</span><span class="muted small">Başlangıç: {e(job["created_at"])}</span></p>{dl}<pre>{e(logs)}</pre><a class="btn btn-light" href="/dashboard">Panele dön</a></div>'
    return layout('İş Detayı', body, request, refresh)


@app.get('/download/{job_id}')
def download(job_id: str, request: Request):
    red = require_login(request)
    if red:
        return red
    job = get_job(job_id)
    if not job or not job.get('result_file_path'):
        return PlainTextResponse('İndirilecek dosya bulunamadı.', status_code=404)
    path = Path(job['result_file_path'])
    if not path.exists():
        return PlainTextResponse('Dosya artık sunucuda yok.', status_code=404)
    return FileResponse(path, media_type=job.get('result_content_type') or 'application/octet-stream', filename=job.get('result_file_name') or path.name)


@app.get('/health')
def health():
    return {'status': 'ok', 'version': 'v3-sale'}
