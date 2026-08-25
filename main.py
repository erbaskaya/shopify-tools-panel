from pathlib import Path
from typing import List
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, PlainTextResponse

from core.auth import clear_login_cookie, is_logged_in, set_login_cookie
from core.config import check_config, get_store, get_stores, get_env_stores, settings
from core.file_utils import save_upload_file
from core.job_manager import create_job, get_job, list_jobs, run_thread
from core.shopify_client import ShopifyClient
from core.store_repository import backend_name, writes_are_persistent, get_managed_store, upsert_managed_store, delete_managed_store
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
    logged_in = bool(request and is_logged_in(request))
    path = request.url.path if request else ''

    def nav_link(href, label, icon, active=False):
        active_class = ' active' if active else ''
        return f'''<a class="side-link{active_class}" href="{href}"><span class="side-icon">{icon}</span><span>{label}</span></a>'''

    dashboard_icon = '''<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h6v6H4V4Zm10 0h6v6h-6V4ZM4 14h6v6H4v-6Zm10 0h6v6h-6v-6Z"/></svg>'''
    sale_icon = '''<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.6 13.1 11 3.5A2 2 0 0 0 9.6 3H5a2 2 0 0 0-2 2v4.6A2 2 0 0 0 3.6 11l9.5 9.5a2 2 0 0 0 2.8 0l4.7-4.6a2 2 0 0 0 0-2.8ZM7 8.5A1.5 1.5 0 1 1 7 5a1.5 1.5 0 0 1 0 3.5Z"/></svg>'''
    stores_icon = '''<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16l-1-3H5L4 7Zm1 2v10h14V9M8 19v-6h8v6" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>'''
    tools_icon = '''<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.7 6.3a5 5 0 0 0-6.3 6.3L3 18l3 3 5.4-5.4a5 5 0 0 0 6.3-6.3l-3 3-3-3 3-3Z"/></svg>'''
    import_icon = '''<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v11m0 0 4-4m-4 4-4-4M5 16v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'''
    history_icon = '''<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 7v5l3 2M4 4v5h5M5.5 16a8 8 0 1 0 .3-8.4L4 9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'''
    logout_icon = '''<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 5H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h5m5-4 4-3-4-3m4 3H9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'''

    if logged_in:
        dashboard_active = path == '/dashboard' or path.startswith('/jobs/')
        sale_active = path == '/sale'
        stores_active = path.startswith('/stores')
        sidebar = f'''<aside class="sidebar">
            <div class="side-brand">
                <div class="brand-mark">S</div>
                <div><strong>Shopify Tools</strong><span>Management Panel</span></div>
            </div>
            <nav class="side-nav">
                <div class="nav-label">GENEL</div>
                {nav_link('/dashboard', 'Dashboard', dashboard_icon, dashboard_active)}
                <div class="nav-label">TİCARET</div>
                {nav_link('/sale', 'Sale Yönetimi', sale_icon, sale_active)}
                {nav_link('/stores', 'Mağaza Yönetimi', stores_icon, stores_active)}
                <div class="nav-label">ARAÇLAR</div>
                {nav_link('/dashboard#quick-tools', 'Hızlı Araçlar', tools_icon)}
                {nav_link('/dashboard#import-export', 'Import / Export', import_icon)}
                {nav_link('/dashboard#recent-jobs', 'İşlem Geçmişi', history_icon)}
            </nav>
            <div class="sidebar-footer">
                <div class="system-status"><span class="status-dot"></span><div><b>Sistem hazır</b><small>v3 + Sale Smart</small></div></div>
                {nav_link('/logout', 'Çıkış Yap', logout_icon)}
            </div>
        </aside>'''
        shell = f'''<div class="app-shell">{sidebar}<section class="main-shell">
            <header class="topbar"><div><span class="topbar-kicker">SHOPIFY OPERATIONS</span><strong>{e(title)}</strong></div><div class="topbar-right"><span class="env-badge">Production</span><span class="avatar">ST</span></div></header>
            <main class="content">{body}</main>
        </section></div>'''
    else:
        shell = f'''<main class="login-shell"><div class="login-brand"><div class="brand-mark large">S</div><div><strong>Shopify Tools Panel</strong><span>Store operations workspace</span></div></div>{body}</main>'''

    return HTMLResponse(f'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{e(title)} · Shopify Tools</title>
<style>
:root{{--bg:#f5f7fb;--surface:#fff;--surface-soft:#f8fafc;--text:#182230;--muted:#667085;--border:#e4e7ec;--primary:#2563eb;--primary-dark:#1d4ed8;--nav:#101828;--nav-soft:#1d2939;--nav-text:#d0d5dd;--success:#067647;--success-bg:#ecfdf3;--warning:#b54708;--warning-bg:#fffaeb;--danger:#b42318;--danger-bg:#fef3f2;--shadow:0 1px 2px rgba(16,24,40,.04),0 8px 24px rgba(16,24,40,.06)}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--text);font-size:14px}}a{{color:inherit}}svg{{width:18px;height:18px;display:block;fill:currentColor}}
.app-shell{{display:grid;grid-template-columns:264px minmax(0,1fr);min-height:100vh}}.sidebar{{position:sticky;top:0;height:100vh;background:linear-gradient(180deg,#101828 0%,#111827 100%);padding:24px 16px 18px;color:#fff;display:flex;flex-direction:column;z-index:20}}.side-brand{{display:flex;align-items:center;gap:12px;padding:0 8px 25px;border-bottom:1px solid rgba(255,255,255,.08)}}.side-brand strong,.login-brand strong{{display:block;font-size:16px;letter-spacing:-.2px}}.side-brand span,.login-brand span{{display:block;color:#98a2b3;font-size:11px;margin-top:3px}}.brand-mark{{width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,#2563eb,#7c3aed);display:grid;place-items:center;color:#fff;font-weight:900;font-size:18px;box-shadow:0 8px 20px rgba(37,99,235,.28)}}.brand-mark.large{{width:48px;height:48px;border-radius:14px;font-size:21px}}.side-nav{{padding-top:18px;display:flex;flex-direction:column;gap:4px}}.nav-label{{font-size:10px;font-weight:800;letter-spacing:1.15px;color:#667085;padding:18px 12px 7px}}.side-link{{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:9px;text-decoration:none;color:var(--nav-text);font-weight:650;transition:.18s ease}}.side-link:hover{{background:rgba(255,255,255,.06);color:#fff}}.side-link.active{{background:#fff;color:#101828;box-shadow:0 4px 12px rgba(0,0,0,.12)}}.side-icon{{width:20px;display:grid;place-items:center}}.sidebar-footer{{margin-top:auto;border-top:1px solid rgba(255,255,255,.08);padding-top:16px}}.system-status{{display:flex;align-items:center;gap:10px;padding:8px 12px 15px;color:#d0d5dd}}.system-status b{{display:block;font-size:12px}}.system-status small{{color:#667085;font-size:10px}}.status-dot{{width:8px;height:8px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 4px rgba(18,183,106,.12)}}
.main-shell{{min-width:0}}.topbar{{height:72px;background:rgba(255,255,255,.94);backdrop-filter:blur(10px);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 32px;position:sticky;top:0;z-index:10}}.topbar strong{{display:block;font-size:16px}}.topbar-kicker{{display:block;color:#98a2b3;font-size:9px;letter-spacing:1.4px;font-weight:800;margin-bottom:3px}}.topbar-right{{display:flex;align-items:center;gap:12px}}.env-badge{{background:var(--success-bg);color:var(--success);border:1px solid #abefc6;border-radius:999px;padding:6px 10px;font-size:11px;font-weight:800}}.avatar{{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#eef2ff;color:#3538cd;font-size:11px;font-weight:900;border:1px solid #e0e7ff}}.content{{padding:24px 28px 32px;max-width:1600px;margin:0 auto;width:100%}}
.page-heading{{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:18px}}.page-heading h1{{font-size:26px;line-height:1.15;margin:4px 0 6px;letter-spacing:-.65px}}.page-heading p{{margin:0;color:var(--muted);max-width:720px;font-size:13px}}.eyebrow{{font-size:10px;letter-spacing:1px;font-weight:850;color:var(--primary)}}h1{{margin:0 0 14px;font-size:26px}}h2{{margin:0 0 5px;font-size:15px;letter-spacing:-.15px}}h3{{margin:22px 0 10px;font-size:12px;letter-spacing:.65px;text-transform:uppercase;color:#475467}}p{{color:var(--muted);line-height:1.45}}.section-title{{display:flex;align-items:center;justify-content:space-between;margin:22px 0 10px}}.section-title h3{{margin:0}}.section-title span{{font-size:11px;color:#98a2b3}}
.metric-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-bottom:14px}}.metric{{position:relative;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px;min-height:82px}}.metric-label{{color:var(--muted);font-size:9px;font-weight:800;letter-spacing:.35px}}.metric-value{{font-size:20px;font-weight:850;letter-spacing:-.45px;margin:4px 0 1px}}.metric-note{{font-size:10px;color:#98a2b3}}.metric-icon{{position:absolute;right:12px;top:12px;width:28px;height:28px;border-radius:8px;background:#f2f4f7;color:#475467;display:grid;place-items:center;font-size:11px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.grid3{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}.card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;box-shadow:none}}.card-header{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px}}.card-icon{{width:30px;height:30px;border-radius:8px;background:#f2f4f7;color:#475467;display:grid;place-items:center;flex:0 0 auto;font-size:10px;font-weight:800}}.card p{{margin:0 0 8px;font-size:12px}}.feature-card{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:14px;border-left:3px solid var(--primary);background:#fff}}.feature-card p{{color:var(--muted);max-width:900px;margin:2px 0 0}}.feature-card .btn{{margin:0}}.feature-top{{display:flex;align-items:center;gap:9px;margin-bottom:2px}}.feature-icon{{width:30px;height:30px;border-radius:8px;background:#eff4ff;color:#3538cd;display:grid;place-items:center;font-weight:900}}
.module-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}.module-card{{background:#fff;border:1px solid var(--border);border-radius:10px;overflow:hidden;min-width:0}}.module-card[open]{{border-color:#b2ccff}}.module-summary{{list-style:none;display:grid;grid-template-columns:32px minmax(0,1fr) 20px;gap:10px;align-items:center;padding:12px;cursor:pointer;user-select:none}}.module-summary::-webkit-details-marker{{display:none}}.module-summary:hover{{background:#f9fafb}}.module-summary .card-icon{{margin:0}}.module-summary h2{{font-size:13px;margin:0 0 2px}}.module-summary p{{font-size:10.5px;line-height:1.35;margin:0;color:#98a2b3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.module-chevron{{color:#98a2b3;font-size:13px;text-align:center;transition:.15s}}.module-card[open] .module-chevron{{transform:rotate(180deg)}}.module-body{{border-top:1px solid #f0f1f3;padding:2px 12px 12px;background:#fcfcfd}}
label{{display:block;font-weight:700;margin:9px 0 5px;color:#344054;font-size:11px}}input[type=text],input[type=number],input[type=password],select,textarea{{width:100%;height:38px;border:1px solid #d0d5dd;border-radius:8px;padding:8px 10px;font:inherit;background:#fff;color:#101828;outline:none;transition:.15s;font-size:12px}}textarea{{height:auto;min-height:96px;resize:vertical}}input:focus,select:focus,textarea:focus{{border-color:#84adff;box-shadow:0 0 0 3px #eff4ff}}input[type=file]{{width:100%;border:1px dashed #cfd4dc;border-radius:8px;padding:9px;background:#fff;font-size:11px}}.check-row{{display:flex;align-items:center;gap:8px;margin:9px 0;color:#475467;font-size:11px;font-weight:650}}.check-row input{{width:15px;height:15px;accent-color:var(--primary);flex:0 0 auto}}button,.btn{{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:0;border-radius:8px;padding:8px 12px;background:var(--primary);color:#fff;font-weight:800;font-size:11px;cursor:pointer;text-decoration:none;margin-top:9px;transition:.15s;min-height:36px}}button:hover,.btn:hover{{background:var(--primary-dark)}}form>button,.card form>.btn,.module-body form>button{{width:100%}}.btn-light{{background:#fff;color:#344054;border:1px solid #d0d5dd}}.btn-light:hover{{background:#f9fafb;color:#182230}}.btn-danger{{background:#d92d20}}.btn-secondary{{background:#344054}}.btn-inline{{width:auto!important}}
.alert{{padding:12px 14px;border-radius:10px;border:1px solid #fedf89;background:var(--warning-bg);color:var(--warning);margin-bottom:16px;font-size:12px;line-height:1.5}}.alert.ok,.ok{{background:var(--success-bg);color:var(--success);border-color:#abefc6}}.muted{{color:var(--muted)}}.small{{font-size:11px}}.pill{{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:800;background:#f2f4f7;color:#475467;margin:3px 5px 3px 0;border:1px solid #eaecf0}}.status-running{{background:var(--warning-bg);color:var(--warning);border-color:#fedf89}}.status-done{{background:var(--success-bg);color:var(--success);border-color:#abefc6}}.status-error{{background:var(--danger-bg);color:var(--danger);border-color:#fecdca}}pre{{background:#0c111d;color:#d0d5dd;padding:18px;border-radius:10px;overflow:auto;white-space:pre-wrap;line-height:1.55;min-height:360px;font-size:12px}}.jobs-list{{display:grid;gap:9px}}.jobs-list a{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;color:var(--text);text-decoration:none;border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:#fff;transition:.15s}}.jobs-list a:hover{{border-color:#b2ccff;background:#f9fbff;transform:translateY(-1px)}}.hint{{background:#f8fafc;border:1px dashed #d0d5dd;padding:11px;border-radius:9px;color:#475467;font-size:11px}}.store-box,.product-box{{border:1px solid var(--border);border-radius:10px;padding:12px;background:#f9fafb}}.store-box{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 12px}}.product-list{{max-height:430px;overflow:auto;border:1px solid var(--border);border-radius:10px;background:#fff}}.product-row{{display:grid;grid-template-columns:24px 1fr auto;gap:10px;align-items:center;padding:11px 12px;border-bottom:1px solid #f0f1f3;cursor:pointer}}.product-row:hover{{background:#f9fbff}}.product-row:last-child{{border-bottom:0}}.product-title{{font-weight:800;font-size:12px}}.filter-section{{display:none;margin-top:10px}}.filter-section.active{{display:block}}.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.workflow-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.step-card{{position:relative;padding-left:54px}}.step-number{{position:absolute;left:18px;top:18px;width:24px;height:24px;border-radius:7px;background:#eef4ff;color:#3538cd;display:grid;place-items:center;font-size:10px;font-weight:900}}
.login-shell{{min-height:100vh;display:grid;place-items:center;padding:28px;background:radial-gradient(circle at 15% 20%,#e0e7ff 0,transparent 28%),radial-gradient(circle at 85% 80%,#dbeafe 0,transparent 24%),#f8fafc}}.login-shell>.card{{width:min(440px,100%);padding:28px;border-radius:16px}}.login-brand{{position:fixed;top:28px;left:32px;display:flex;align-items:center;gap:12px}}.login-brand strong{{color:#101828}}.login-shell h1{{font-size:25px;margin-bottom:7px}}.login-shell p{{margin-top:0}}.login-shell button{{width:100%}}
@media(max-width:1280px){{.grid3{{grid-template-columns:repeat(3,1fr)}}.module-grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:1120px){{.grid3{{grid-template-columns:repeat(2,1fr)}}.metric-grid{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:820px){{.app-shell{{display:block}}.sidebar{{position:relative;height:auto;padding:12px;display:block}}.side-brand{{padding:4px 4px 12px}}.side-nav{{display:flex;flex-direction:row;overflow-x:auto;padding-top:10px;gap:6px}}.nav-label,.sidebar-footer{{display:none}}.side-link{{white-space:nowrap;background:rgba(255,255,255,.04)}}.topbar{{height:62px;padding:0 18px}}.content{{padding:18px 14px}}.page-heading{{flex-direction:column}}.grid,.grid3,.module-grid,.workflow-grid,.two-col,.store-box{{grid-template-columns:1fr}}.metric-grid{{grid-template-columns:1fr 1fr}}.feature-card{{grid-template-columns:1fr}}}}
@media(max-width:520px){{.metric-grid{{grid-template-columns:1fr}}.topbar-right .env-badge{{display:none}}.login-brand{{position:static;margin-bottom:22px;justify-self:start}}.login-shell{{display:flex;flex-direction:column;justify-content:center}}}}
</style></head><body>{shell}</body></html>''')


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
<div class="page-heading">
  <div><span class="eyebrow">OPERASYON MERKEZİ</span><h1>Shopify İşlem Paneli</h1><p>Günlük mağaza operasyonları için sade, büyümeye hazır yönetim alanı.</p></div>
  <a class="btn btn-inline" href="/sale">Sale Yönetimi →</a>
</div>
{cfg}
<div class="metric-grid">
  <div class="metric"><span class="metric-icon">◆</span><div class="metric-label">MAĞAZA</div><div class="metric-value">{len(stores)}</div><div class="metric-note">Bağlı hesap</div></div>
  <div class="metric"><span class="metric-icon">↻</span><div class="metric-label">İŞLEM</div><div class="metric-value">{len(recent)}</div><div class="metric-note">Son görevler</div></div>
  <div class="metric"><span class="metric-icon">%</span><div class="metric-label">SALE</div><div class="metric-value">Smart</div><div class="metric-note">Fiyat bazlı</div></div>
  <div class="metric"><span class="metric-icon">✓</span><div class="metric-label">DURUM</div><div class="metric-value">Online</div><div class="metric-note">API hazır</div></div>
</div>
<div class="card feature-card">
  <div><div class="feature-top"><span class="feature-icon">%</span><div><h2>Sale / İndirim Yönetimi</h2><span class="small">Smart Collection uyumlu</span></div></div><p>Toplu fiyat indirimi uygula veya geri al. Kategori üyeliğini Shopify otomatik yönetir.</p></div>
  <a class="btn btn-inline" href="/sale">Modülü Aç</a>
</div>
<div class="section-title" id="quick-tools"><h3>Hızlı Araçlar</h3><span>Karta tıklayın, işlem alanı açılsın</span></div>
<div class="module-grid">
  <details class="module-card"><summary class="module-summary"><span class="card-icon">↕</span><div><h2>Stok Ayarla</h2><p>Tüm varyant stoklarını tek değere eşitle.</p></div><span class="module-chevron">⌄</span></summary><div class="module-body"><form method="post" action="/actions/stocks"><label>Hedef stok miktarı</label><input type="number" name="stock_value" value="5" min="0" required><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Önce test modunda çalıştır</label><button>İşlemi Başlat</button></form></div></details>
  <details class="module-card"><summary class="module-summary"><span class="card-icon">⌘</span><div><h2>Kategori Senkronizasyonu</h2><p>Alt kategori ürünlerini üst kategorilere aktar.</p></div><span class="module-chevron">⌄</span></summary><div class="module-body"><form method="post" action="/actions/categories"><label>Shopify menü handle</label><input type="text" name="menu_handle" placeholder="main-menu" required><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Önce test modunda çalıştır</label><button>İşlemi Başlat</button></form></div></details>
  <details class="module-card"><summary class="module-summary"><span class="card-icon">%</span><div><h2>Sale Yönetimi</h2><p>Kategori, marka veya ürün bazında indirim yönet.</p></div><span class="module-chevron">→</span></summary><div class="module-body"><p class="small">Gelişmiş filtre ve fiyat geri alma araçları ayrı sayfadadır.</p><a class="btn" href="/sale">Sale Sayfasına Git</a></div></details>
</div>
<div class="section-title" id="import-export"><h3>Import / Export</h3><span>Yeni modüller aynı yapıya kolayca eklenebilir</span></div>
<div class="module-grid">
  <details class="module-card"><summary class="module-summary"><span class="card-icon">01</span><div><h2>Ürün Import</h2><p>Ürün oluştur veya mevcut ürünü güncelle.</p></div><span class="module-chevron">⌄</span></summary><div class="module-body">{file_form('/actions/product-import','Ürün dosyası')}</div></details>
  <details class="module-card"><summary class="module-summary"><span class="card-icon">02</span><div><h2>Kategori Import</h2><p>Manual ve smart koleksiyonları içeri aktar.</p></div><span class="module-chevron">⌄</span></summary><div class="module-body">{file_form('/actions/category-import','Kategori dosyası')}</div></details>
  <details class="module-card"><summary class="module-summary"><span class="card-icon">03</span><div><h2>Menü Export</h2><p>Menü yapısını CSV veya JSON olarak dışa aktar.</p></div><span class="module-chevron">⌄</span></summary><div class="module-body"><form method="post" action="/actions/menu-export"><label>Menü handle</label><input type="text" name="menu_handle" placeholder="main-menu" required><label>Format</label><select name="export_format"><option value="csv">CSV</option><option value="json">JSON</option></select><button>Export Başlat</button></form></div></details>
  <details class="module-card"><summary class="module-summary"><span class="card-icon">04</span><div><h2>Menü Import</h2><p>CSV/JSON menü dosyasını içeri aktar.</p></div><span class="module-chevron">⌄</span></summary><div class="module-body"><form method="post" action="/actions/menu-import" enctype="multipart/form-data"><label>Menü handle</label><input type="text" name="menu_handle" placeholder="main-menu" required><label>Menü başlığı</label><input type="text" name="menu_title" placeholder="Main menu"><label>Menü dosyası</label><input type="file" name="file" accept=".csv,.json" required><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Test modu</label><button>Import Başlat</button></form></div></details>
  <details class="module-card"><summary class="module-summary"><span class="card-icon">05</span><div><h2>Blog Import</h2><p>Blog ve yazıları toplu oluştur veya güncelle.</p></div><span class="module-chevron">⌄</span></summary><div class="module-body">{file_form('/actions/blog-import','Blog dosyası')}</div></details>
  <details class="module-card"><summary class="module-summary"><span class="card-icon">06</span><div><h2>Vendor Güncelle</h2><p>SKU, handle veya product_id ile satıcı güncelle.</p></div><span class="module-chevron">⌄</span></summary><div class="module-body">{file_form('/actions/vendor-import','Vendor dosyası')}</div></details>
</div>
<div class="section-title" id="recent-jobs"><h3>İşlem Merkezi</h3><span>Son görevler</span></div>
{jobs if jobs else '<div class="card"><div class="hint">Henüz işlem geçmişi yok. İlk işleminiz burada görünecek.</div></div>'}
<div class="card" style="margin-top:10px"><div class="card-header"><div><h2>Dosya Şablonları</h2><p>Örnek CSV dosyaları <b>sample_templates/</b> klasöründe bulunur.</p></div><span class="card-icon">CSV</span></div></div>'''

    return layout('Dashboard', body, request)


def _store_mask(token):
    token = str(token or '')
    if len(token) <= 8:
        return '••••••••'
    return token[:4] + '••••••••••••' + token[-4:]


@app.get('/stores', response_class=HTMLResponse)
def stores_page(request: Request, edit: str = '', msg: str = '', error: str = ''):
    red = require_login(request)
    if red:
        return red

    stores = get_stores()
    managed = get_managed_store(edit) if edit else None
    env_stores = get_env_stores()
    persistent = writes_are_persistent()
    storage = backend_name()

    rows = []
    for store in stores:
        source = getattr(store, 'source', 'env')
        source_badge = '<span class="pill status-done">Panel</span>' if source == 'panel' else '<span class="pill">ENV</span>'
        if source == 'panel':
            actions = f'''<div style="display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap">
                <a class="btn btn-light btn-inline" href="/stores?edit={e(store.key)}">Düzenle</a>
                <form method="post" action="/stores/{e(store.key)}/test"><button class="btn btn-light btn-inline" type="submit">Bağlantı Testi</button></form>
                <form method="post" action="/stores/{e(store.key)}/delete" onsubmit="return confirm('Bu mağaza panelden silinsin mi?')"><button class="btn btn-danger btn-inline" type="submit">Sil</button></form>
            </div>'''
        else:
            actions = '<span class="muted small">Environment Variable üzerinden tanımlı</span>'
        rows.append(f'''<div class="store-manage-row">
            <div><div class="product-title">{e(store.name)}</div><div class="muted small">{e(store.domain)}</div></div>
            <div><code>{e(store.key)}</code></div>
            <div>{source_badge}</div>
            <div class="muted small">{e(store.api_version)}</div>
            <div>{actions}</div>
        </div>''')
    store_rows = ''.join(rows) or '<div class="hint">Henüz mağaza tanımlı değil.</div>'

    if managed:
        form_title = 'Mağazayı Düzenle'
        key_value = managed.get('key', '')
        name_value = managed.get('name', '')
        domain_value = managed.get('domain', '')
        api_value = managed.get('api_version', '2026-04')
        token_hint = f'Mevcut token: {_store_mask(managed.get("token"))}. Değiştirmeyecekseniz boş bırakın.'
        token_required = ''
    else:
        form_title = 'Yeni Mağaza Ekle'
        key_value = name_value = domain_value = ''
        api_value = '2026-04'
        token_hint = 'Shopify Admin API access token (shpat_...)'
        token_required = 'required'

    write_warning = ''
    form_disabled = ''
    if not persistent:
        form_disabled = 'disabled'
        write_warning = '''<div class="alert"><b>Kalıcı depolama gerekli:</b> Vercel dosya sistemi geçicidir. Panelden mağaza ekleme/düzenleme için Vercel projesine bir PostgreSQL veritabanı bağlayıp <b>DATABASE_URL</b> Environment Variable oluşturmalıyız. Mevcut ENV mağazaları çalışmaya devam eder.</div>'''

    import_env = ''
    if env_stores:
        disabled = 'disabled' if not persistent else ''
        import_env = f'''<div class="card" style="margin-top:12px"><div class="card-header"><div><h2>ENV Mağazalarını Panele Taşı</h2><p>Mevcut SHOPIFY_STORES_JSON içindeki {len(env_stores)} mağazayı yönetilebilir mağaza kayıtlarına kopyalar.</p></div><span class="card-icon">⇢</span></div>
        <form method="post" action="/stores/import-env"><button {disabled}>ENV Mağazalarını İçe Aktar</button></form>
        <p class="small muted">Aktarım başarılı olduktan sonra Vercel'deki SHOPIFY_STORES_JSON değişkenini kaldırabilirsiniz.</p></div>'''

    status_msg = f'<div class="alert ok">{e(msg)}</div>' if msg else ''
    error_msg = f'<div class="alert">{e(error)}</div>' if error else ''
    cancel = '<a class="btn btn-light btn-inline" href="/stores">Vazgeç</a>' if managed else ''

    body = f'''
<style>
.store-manage-grid{{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr);gap:14px;align-items:start}}
.store-manage-row{{display:grid;grid-template-columns:minmax(180px,1.4fr) minmax(100px,.7fr) 70px 90px minmax(210px,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--border)}}
.store-manage-row:last-child{{border-bottom:0}}code{{font-size:12px;background:#f4f4f5;padding:4px 7px;border-radius:7px}}.token-note{{font-size:12px;color:var(--muted);margin-top:6px}}
@media(max-width:1050px){{.store-manage-grid{{grid-template-columns:1fr}}.store-manage-row{{grid-template-columns:1fr 1fr;align-items:start}}}}
</style>
<div class="page-heading"><div><span class="eyebrow">AYARLAR</span><h1>Mağaza Yönetimi</h1><p>Shopify mağazalarını panelden ekleyin, düzenleyin, test edin ve silin.</p></div><span class="pill status-done">Depolama: {e(storage)}</span></div>
{status_msg}{error_msg}{write_warning}
<div class="store-manage-grid">
  <div>
    <div class="card"><div class="card-header"><div><h2>Bağlı Mağazalar</h2><p>Sale ve diğer çoklu mağaza işlemlerinde bu liste kullanılır.</p></div><span class="card-icon">{len(stores)}</span></div>{store_rows}</div>
    {import_env}
  </div>
  <div class="card"><div class="card-header"><div><h2>{form_title}</h2><p>Token tarayıcıya geri gösterilmez ve panel kayıtlarında şifreli saklanır.</p></div><span class="card-icon">＋</span></div>
    <form method="post" action="/stores/save">
      <label>Mağaza adı</label><input type="text" name="name" value="{e(name_value)}" placeholder="HAUSONE" required {form_disabled}>
      <label>Mağaza anahtarı</label><input type="text" name="store_key" value="{e(key_value)}" placeholder="hausone" {'readonly' if managed else ''} required {form_disabled}><div class="token-note">Kısa ve benzersiz olmalı. Örn: hausone, frank-eiselt.</div>
      <label>Shopify domain</label><input type="text" name="domain" value="{e(domain_value)}" placeholder="xxxxx.myshopify.com" required {form_disabled}>
      <label>Admin API Access Token</label><input type="password" name="token" placeholder="{e(token_hint)}" {token_required} {form_disabled}><div class="token-note">{e(token_hint)}</div>
      <label>API version</label><input type="text" name="api_version" value="{e(api_value)}" placeholder="2026-04" required {form_disabled}>
      <button type="submit" {form_disabled}>Kaydet</button>{cancel}
    </form>
  </div>
</div>'''
    return layout('Mağaza Yönetimi', body, request)


@app.post('/stores/save')
def stores_save(request: Request, name: str = Form(...), store_key: str = Form(...), domain: str = Form(...), token: str = Form(''), api_version: str = Form('2026-04')):
    red = require_login(request)
    if red:
        return red
    try:
        upsert_managed_store(store_key, name, domain, token, api_version, True)
        return RedirectResponse('/stores?msg=Mağaza kaydedildi.', status_code=303)
    except Exception as exc:
        return RedirectResponse('/stores?error=' + quote(str(exc)), status_code=303)


@app.post('/stores/{store_key}/delete')
def stores_delete(store_key: str, request: Request):
    red = require_login(request)
    if red:
        return red
    try:
        delete_managed_store(store_key)
        return RedirectResponse('/stores?msg=Mağaza silindi.', status_code=303)
    except Exception as exc:
        return RedirectResponse('/stores?error=' + quote(str(exc)), status_code=303)


@app.post('/stores/{store_key}/test')
def stores_test(store_key: str, request: Request):
    red = require_login(request)
    if red:
        return red
    try:
        store = get_store(store_key)
        if not store:
            raise Exception('Mağaza bulunamadı.')
        client = ShopifyClient(store=store)
        data = client.gql('query { shop { name myshopifyDomain } }')
        shop = data.get('shop') or {}
        msg = f'Bağlantı başarılı: {shop.get("name") or store.name} ({shop.get("myshopifyDomain") or store.domain})'
        return RedirectResponse('/stores?msg=' + quote(msg), status_code=303)
    except Exception as exc:
        return RedirectResponse('/stores?error=' + quote('Bağlantı başarısız: ' + str(exc)), status_code=303)


@app.post('/stores/import-env')
def stores_import_env(request: Request):
    red = require_login(request)
    if red:
        return red
    try:
        items = get_env_stores()
        for store in items:
            upsert_managed_store(store.key, store.name, store.domain, store.token, store.api_version, True)
        return RedirectResponse('/stores?msg=' + quote(f'{len(items)} mağaza panele aktarıldı.'), status_code=303)
    except Exception as exc:
        return RedirectResponse('/stores?error=' + quote(str(exc)), status_code=303)

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
<div class="page-heading">
  <div><span class="eyebrow">FİYAT OTOMASYONU</span><h1>Sale Yönetimi</h1><p>Kategori, marka veya ürün bazında indirim uygulayın; gerektiğinde fiyatları tek işlemle geri alın.</p></div>
  <a class="btn btn-light btn-inline" href="/dashboard">← Dashboard</a>
</div>
<div class="alert ok"><b>Smart Collection modu:</b> Panel kategori üyeliğine müdahale etmez. İndirimde mevcut satış fiyatı Compare-at Price alanına taşınır; geri almada Compare-at tekrar satış fiyatı olur ve alan temizlenir.</div>
{load_alert}
<div class="card" style="margin-bottom:16px">
  <div class="card-header"><div><h2>Referans Mağaza ve Ürün Arama</h2><p>Filtre seçeneklerini hangi mağazadan okuyacağınızı belirleyin.</p></div><span class="card-icon">⌕</span></div>
  <form method="get" action="/sale"><div class="two-col"><div><label>Referans mağaza</label><select name="source_store">{store_options}</select></div><div><label>Ürün ara</label><input type="text" name="q" value="{e(q)}" placeholder="Ürün adı, handle veya SKU"></div></div><button class="btn-light">Listeyi Yenile / Ara</button></form>
</div>
<form method="post" action="/actions/sale" id="saleForm">
  <div class="workflow-grid">
    <div class="card step-card"><span class="step-number">1</span><h2>Hedef Mağazalar</h2><p>İşlemin uygulanacağı mağazaları seçin.</p><div class="store-box">{target_checks}</div></div>
    <div class="card step-card"><span class="step-number">2</span><h2>İşlem ve Oran</h2><p>İndirim uygulayın veya mevcut indirimi geri alın.</p><label>İşlem tipi</label><select name="operation" id="operation"><option value="apply">İndirim uygula</option><option value="restore">İndirimi kaldır</option></select><div id="discountBox"><label>İndirim yüzdesi</label><input type="number" name="discount_percent" value="20" min="0.01" max="99.99" step="0.01"></div><label class="check-row"><input type="checkbox" name="dry_run" value="1" checked> Önce test modu (önerilir)</label></div>
  </div>
  <div class="card step-card" style="margin-top:16px"><span class="step-number">3</span><h2>Ürün Seçim Yöntemi</h2><p>İşlemin kapsamını kategori, marka veya ürün seçimiyle belirleyin.</p><label>Filtre tipi</label><select name="filter_mode" id="filterMode"><option value="collection">Kategoriye göre</option><option value="vendor">Satıcı / markaya göre</option><option value="products">Tek tek ürün seç</option></select>
    <div id="filter-collection" class="filter-section active"><label>Kategori</label><select name="collection_handle"><option value="">Kategori seçin</option>{collection_options}</select></div>
    <div id="filter-vendor" class="filter-section"><label>Satıcı / Marka</label><select name="vendor"><option value="">Satıcı / marka seçin</option>{vendor_options}</select></div>
    <div id="filter-products" class="filter-section"><label>Ürünler</label><div class="product-list">{products_html}</div><p class="small">En fazla 50 arama sonucu gösterilir. Başka ürünler için üstteki ürün aramasını kullanın.</p></div>
    <button type="submit">İşlemi Başlat</button>
  </div>
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
