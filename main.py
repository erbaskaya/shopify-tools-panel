from pathlib import Path
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, PlainTextResponse
from core.auth import clear_login_cookie, is_logged_in, set_login_cookie
from core.config import check_config, settings
from core.file_utils import save_upload_file
from core.job_manager import create_job, get_job, list_jobs, run_thread
from actions.stock_update import run as run_stock_update
from actions.category_sync import run as run_category_sync
from actions.product_import import run as run_product_import
from actions.category_import import run as run_category_import
from actions.menu_export import run as run_menu_export
from actions.menu_import import run as run_menu_import
from actions.blog_import import run as run_blog_import
from actions.vendor_import import run as run_vendor_import

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
    logout = '<a class="top-link" href="/logout">Çıkış</a>' if request and is_logged_in(request) else ''
    return HTMLResponse(f'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{e(title)}</title>
<style>
:root{{--bg:#f4f6fb;--card:#fff;--text:#111827;--muted:#6b7280;--border:#e5e7eb;--primary:#111827;--hover:#374151}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text)}}.header{{background:#fff;border-bottom:1px solid var(--border);padding:18px 28px;display:flex;justify-content:space-between;position:sticky;top:0;z-index:5}}.brand{{font-weight:800;font-size:18px}}.version{{font-size:12px;color:var(--muted);margin-left:8px}}.top-link{{color:var(--text);text-decoration:none;font-size:14px;border:1px solid var(--border);padding:8px 12px;border-radius:10px}}.wrap{{width:min(1220px,calc(100% - 32px));margin:26px auto}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.grid3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}}@media(max-width:980px){{.grid3{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:760px){{.grid,.grid3{{grid-template-columns:1fr}}.wrap{{width:calc(100% - 24px)}}}}.card{{background:#fff;border:1px solid var(--border);border-radius:18px;padding:22px;box-shadow:0 12px 30px rgba(15,23,42,.06)}}h1{{margin:0 0 18px;font-size:28px}}h2{{margin:0 0 12px;font-size:21px}}h3{{margin:24px 0 14px;font-size:20px}}p{{color:var(--muted);line-height:1.5}}label{{display:block;font-weight:700;margin:14px 0 7px}}input[type=text],input[type=number],input[type=password],select{{width:100%;border:1px solid var(--border);border-radius:12px;padding:12px 13px;font-size:15px;background:#fff}}input[type=file]{{width:100%;border:1px dashed #cbd5e1;border-radius:12px;padding:12px;background:#f8fafc}}.check-row{{display:flex;align-items:center;gap:9px;margin:12px 0;color:var(--muted);font-size:14px;font-weight:700}}button,.btn{{display:inline-flex;align-items:center;justify-content:center;width:100%;border:0;border-radius:12px;padding:13px 16px;background:var(--primary);color:#fff;font-weight:800;font-size:15px;cursor:pointer;text-decoration:none;margin-top:14px}}button:hover,.btn:hover{{background:var(--hover)}}.btn-light{{background:#fff;color:var(--text);border:1px solid var(--border)}}.alert{{padding:14px 16px;border-radius:14px;border:1px solid var(--border);background:#fff7ed;color:#9a3412;margin-bottom:18px}}.ok{{background:#ecfdf5;color:#166534;border-color:#bbf7d0}}.muted{{color:var(--muted)}}.small{{font-size:13px}}.pill{{display:inline-block;padding:6px 10px;border-radius:99px;font-size:13px;font-weight:800;background:#eef2ff;color:#3730a3;margin:4px 6px 4px 0}}.status-running{{background:#fff7ed;color:#9a3412}}.status-done{{background:#ecfdf5;color:#166534}}.status-error{{background:#fef2f2;color:#991b1b}}pre{{background:#0b1020;color:#e5e7eb;padding:18px;border-radius:16px;overflow:auto;white-space:pre-wrap;line-height:1.45;min-height:360px;font-size:13px}}.jobs-list a{{display:block;color:var(--text);text-decoration:none;border:1px solid var(--border);border-radius:14px;padding:14px;margin:10px 0;background:#fff}}.hint{{background:#f8fafc;border:1px dashed #cbd5e1;padding:12px;border-radius:12px;color:#475569;font-size:13px}}
</style></head><body><div class="header"><div class="brand">Shopify Tools Panel <span class="version">v3 import/export</span></div><div>{logout}</div></div><main class="wrap">{body}</main></body></html>''')

@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    if is_logged_in(request): return RedirectResponse('/dashboard', status_code=303)
    miss=check_config(); warn=''
    if miss: warn=f'<div class="alert">Eksik Render Environment Variables: <b>{e(", ".join(miss))}</b></div>'
    return layout('Giriş', f'''<div class="card" style="max-width:520px;margin:80px auto"><h1>Giriş</h1>{warn}<p>Panel şifresini gir.</p><form method="post" action="/login"><label>Panel Şifresi</label><input type="password" name="password" required><button>Giriş Yap</button></form></div>''', request)

@app.post('/login')
def login(password: str = Form(...)):
    import hmac
    if not settings.PANEL_PASSWORD: return PlainTextResponse('PANEL_PASSWORD env ayarı eksik.', status_code=500)
    if not hmac.compare_digest(password, settings.PANEL_PASSWORD): return HTMLResponse('<h2>Şifre yanlış</h2><p><a href="/">Tekrar dene</a></p>', status_code=401)
    r=RedirectResponse('/dashboard', status_code=303); set_login_cookie(r); return r

@app.get('/logout')
def logout():
    r=RedirectResponse('/', status_code=303); clear_login_cookie(r); return r

def file_form(action, label, accept='.csv,.xlsx,.xlsm'):
    return f'''<form method="post" action="{action}" enctype="multipart/form-data"><label>{label}</label><input type="file" name="file" accept="{accept}" required><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Test modu</label><button type="submit">Başlat</button></form>'''

@app.get('/dashboard', response_class=HTMLResponse)
def dashboard(request: Request):
    red=require_login(request)
    if red: return red
    miss=check_config()
    cfg=f'<div class="alert">Eksik ayarlar: <b>{e(", ".join(miss))}</b></div>' if miss else f'<div class="alert ok">Ayarlar hazır görünüyor. Shop: <b>{e(settings.SHOP_DOMAIN)}</b> | API: <b>{e(settings.API_VERSION)}</b></div>'
    jobs=''
    recent=list_jobs(10)
    if recent:
        items=[]
        for j in recent:
            dl='<span class="pill status-done">download</span>' if j.get('result_file_path') else ''
            items.append(f'<a href="/jobs/{e(j["id"])}"><b>{e(j["title"])}</b><br><span class="pill status-{e(j["status"])}">{e(j["status"])}</span>{dl}<span class="muted small">Başlangıç: {e(j["created_at"])}</span></a>')
        jobs=f'<div class="card" style="margin-top:18px"><h2>Son İşlemler</h2><div class="jobs-list">{"".join(items)}</div></div>'
    body=f'''
<h1>Shopify İşlem Paneli</h1>{cfg}
<div class="alert">Render sunucusu bilgisayarındaki <b>C:\\...</b> veya <b>D:\\...</b> dosya yolunu okuyamaz. Import için <b>dosya seçme butonu</b> daha doğru. Export sonrası indirme butonu çıkar.</div>
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
<div class="card" style="margin-top:18px"><h2>Dosya Şablonları</h2><p>ZIP içinde <b>sample_templates/</b> klasöründe örnek CSV dosyaları var.</p><div class="hint">CSV dosyaları Türkçe Excel için <b>;</b> ayırıcıyla hazırlandı.</div></div>{jobs}'''
    return layout('Dashboard', body, request)

def start_job(title, func, *args):
    job_id=create_job(title); run_thread(func, job_id, *args); return RedirectResponse(f'/jobs/{job_id}', status_code=303)

@app.post('/actions/stocks')
def a_stocks(request: Request, stock_value:int=Form(...), dry_run:str=Form(None)):
    red=require_login(request); 
    if red: return red
    dry=dry_run=='1'; return start_job(f'Stokları {stock_value} yap' + (' - TEST' if dry else ''), run_stock_update, stock_value, dry)
@app.post('/actions/categories')
def a_categories(request: Request, menu_handle:str=Form(...), dry_run:str=Form(None)):
    red=require_login(request); 
    if red: return red
    dry=dry_run=='1'; return start_job(f'Alt kategorileri üstlere ekle: {menu_handle}' + (' - TEST' if dry else ''), run_category_sync, menu_handle, dry)
@app.post('/actions/product-import')
def a_product(request: Request, file: UploadFile=File(...), dry_run:str=Form(None)):
    red=require_login(request); 
    if red: return red
    p=save_upload_file(file,'product_import'); dry=dry_run=='1'; return start_job('Ürün import' + (' - TEST' if dry else ''), run_product_import, str(p), dry)
@app.post('/actions/category-import')
def a_catimp(request: Request, file: UploadFile=File(...), dry_run:str=Form(None)):
    red=require_login(request); 
    if red: return red
    p=save_upload_file(file,'category_import'); dry=dry_run=='1'; return start_job('Kategori import' + (' - TEST' if dry else ''), run_category_import, str(p), dry)
@app.post('/actions/menu-export')
def a_menuexp(request: Request, menu_handle:str=Form(...), export_format:str=Form('csv')):
    red=require_login(request); 
    if red: return red
    return start_job(f'Menü export: {menu_handle}', run_menu_export, menu_handle, export_format)
@app.post('/actions/menu-import')
def a_menuimp(request: Request, file: UploadFile=File(...), menu_handle:str=Form(...), menu_title:str=Form(''), dry_run:str=Form(None)):
    red=require_login(request); 
    if red: return red
    p=save_upload_file(file,'menu_import'); dry=dry_run=='1'; return start_job(f'Menü import: {menu_handle}' + (' - TEST' if dry else ''), run_menu_import, str(p), menu_handle, menu_title, dry)
@app.post('/actions/blog-import')
def a_blog(request: Request, file: UploadFile=File(...), dry_run:str=Form(None)):
    red=require_login(request); 
    if red: return red
    p=save_upload_file(file,'blog_import'); dry=dry_run=='1'; return start_job('Blog import' + (' - TEST' if dry else ''), run_blog_import, str(p), dry)
@app.post('/actions/vendor-import')
def a_vendor(request: Request, file: UploadFile=File(...), dry_run:str=Form(None)):
    red=require_login(request); 
    if red: return red
    p=save_upload_file(file,'vendor_import'); dry=dry_run=='1'; return start_job('Vendor import' + (' - TEST' if dry else ''), run_vendor_import, str(p), dry)

@app.get('/jobs/{job_id}', response_class=HTMLResponse)
def job_page(job_id: str, request: Request):
    red=require_login(request)
    if red: return red
    j=get_job(job_id)
    if not j: return layout('İş bulunamadı','<div class="card"><h1>İş bulunamadı</h1><a class="btn btn-light" href="/dashboard">Panele dön</a></div>',request)
    refresh=3 if j['status']=='running' else None
    dl=f'<a class="btn" href="/download/{e(job_id)}">Export Dosyasını İndir: {e(j.get("result_file_name"))}</a>' if j.get('result_file_path') and j['status']=='done' else ''
    logs='\n'.join(j.get('logs',[]))
    body=f'<div class="card"><h1>{e(j["title"])}</h1><p><span class="pill status-{e(j["status"])}">{e(j["status"])}</span><span class="muted small">Başlangıç: {e(j["created_at"])}</span></p>{dl}<pre>{e(logs)}</pre><a class="btn btn-light" href="/dashboard">Panele dön</a></div>'
    return layout('İş Detayı', body, request, refresh)

@app.get('/download/{job_id}')
def download(job_id: str, request: Request):
    red=require_login(request)
    if red: return red
    j=get_job(job_id)
    if not j or not j.get('result_file_path'): return PlainTextResponse('İndirilecek dosya bulunamadı.', status_code=404)
    p=Path(j['result_file_path'])
    if not p.exists(): return PlainTextResponse('Dosya artık sunucuda yok.', status_code=404)
    return FileResponse(p, media_type=j.get('result_content_type') or 'application/octet-stream', filename=j.get('result_file_name') or p.name)

@app.get('/health')
def health(): return {'status':'ok','version':'v3'}
