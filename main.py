from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse

from core.auth import clear_login_cookie, is_logged_in, set_login_cookie
from core.config import check_config, settings
from core.job_manager import create_job, get_job, list_jobs, run_thread

from actions.stock_update import run as run_stock_update
from actions.category_sync import run as run_category_sync


app = FastAPI(title="Shopify Tools Panel V2")


def e(value):
    import html
    return html.escape(str(value or ""))


def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/", status_code=303)
    return None


def render_layout(title, body, request=None, refresh_seconds=None):
    refresh_meta = ""
    if refresh_seconds:
        refresh_meta = f'<meta http-equiv="refresh" content="{int(refresh_seconds)}">'

    logout_link = ""
    if request and is_logged_in(request):
        logout_link = '<a class="top-link" href="/logout">Çıkış</a>'

    return HTMLResponse(f"""
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh_meta}
  <title>{e(title)}</title>
  <style>
    :root {{
      --bg: #f4f6fb;
      --card: #ffffff;
      --text: #111827;
      --muted: #6b7280;
      --border: #e5e7eb;
      --primary: #111827;
      --primary-hover: #374151;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .header {{
      background: #fff;
      border-bottom: 1px solid var(--border);
      padding: 18px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 5;
    }}
    .brand {{
      font-weight: 800;
      font-size: 18px;
    }}
    .version {{
      font-size: 12px;
      color: var(--muted);
      margin-left: 8px;
      font-weight: 700;
    }}
    .top-link {{
      color: var(--text);
      text-decoration: none;
      font-size: 14px;
      border: 1px solid var(--border);
      padding: 8px 12px;
      border-radius: 10px;
      background: #fff;
    }}
    .wrap {{
      width: min(1120px, calc(100% - 32px));
      margin: 26px auto;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    @media (max-width: 760px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .header {{ padding: 16px; }}
      .wrap {{ width: calc(100% - 24px); }}
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: 28px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 21px;
    }}
    p {{
      color: var(--muted);
      line-height: 1.5;
    }}
    label {{
      display: block;
      font-weight: 700;
      margin: 14px 0 7px;
    }}
    input[type="text"], input[type="number"], input[type="password"] {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 13px;
      font-size: 15px;
      background: #fff;
    }}
    .check-row {{
      display: flex;
      align-items: center;
      gap: 9px;
      margin: 12px 0;
      color: var(--muted);
      font-size: 14px;
      font-weight: 700;
    }}
    button, .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      border: 0;
      border-radius: 12px;
      padding: 13px 16px;
      background: var(--primary);
      color: #fff;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
      text-decoration: none;
      margin-top: 14px;
    }}
    button:hover, .btn:hover {{ background: var(--primary-hover); }}
    .btn-light {{
      background: #fff;
      color: var(--text);
      border: 1px solid var(--border);
    }}
    .btn-light:hover {{ background: #f9fafb; }}
    .alert {{
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: #fff7ed;
      color: #9a3412;
      margin-bottom: 18px;
    }}
    .ok {{
      background: #ecfdf5;
      color: #166534;
      border-color: #bbf7d0;
    }}
    .muted {{ color: var(--muted); }}
    .small {{ font-size: 13px; }}
    .pill {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 99px;
      font-size: 13px;
      font-weight: 800;
      background: #eef2ff;
      color: #3730a3;
      margin: 4px 6px 4px 0;
    }}
    .status-running {{ background: #fff7ed; color: #9a3412; }}
    .status-done {{ background: #ecfdf5; color: #166534; }}
    .status-error {{ background: #fef2f2; color: #991b1b; }}
    pre {{
      background: #0b1020;
      color: #e5e7eb;
      padding: 18px;
      border-radius: 16px;
      overflow: auto;
      white-space: pre-wrap;
      line-height: 1.45;
      min-height: 360px;
      font-size: 13px;
    }}
    .jobs-list a {{
      display: block;
      color: var(--text);
      text-decoration: none;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      margin: 10px 0;
      background: #fff;
    }}
    .hint {{
      background: #f8fafc;
      border: 1px dashed #cbd5e1;
      padding: 12px;
      border-radius: 12px;
      color: #475569;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">Shopify Tools Panel <span class="version">v2 modüler</span></div>
    <div>{logout_link}</div>
  </div>
  <main class="wrap">
    {body}
  </main>
</body>
</html>
""")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if is_logged_in(request):
        return RedirectResponse("/dashboard", status_code=303)

    missing = check_config()
    warning = ""
    if missing:
        warning = f"""
        <div class="alert">
          Eksik Render Environment Variables: <b>{e(", ".join(missing))}</b>
          <br>Render panelinden bunları eklemeden işlemler çalışmaz.
        </div>
        """

    body = f"""
    <div class="card" style="max-width:520px;margin:80px auto;">
      <h1>Giriş</h1>
      {warning}
      <p>Shopify işlem paneline devam etmek için panel şifresini gir.</p>
      <form method="post" action="/login">
        <label>Panel Şifresi</label>
        <input type="password" name="password" placeholder="PANEL_PASSWORD" required>
        <button type="submit">Giriş Yap</button>
      </form>
    </div>
    """
    return render_layout("Giriş", body, request)


@app.post("/login")
def login(password: str = Form(...)):
    if not settings.PANEL_PASSWORD:
        return PlainTextResponse("PANEL_PASSWORD env ayarı eksik.", status_code=500)

    import hmac
    if not hmac.compare_digest(password, settings.PANEL_PASSWORD):
        return HTMLResponse("""
        <html><body style="font-family:Arial;padding:40px;">
          <h2>Şifre yanlış</h2>
          <p><a href="/">Tekrar dene</a></p>
        </body></html>
        """, status_code=401)

    response = RedirectResponse("/dashboard", status_code=303)
    set_login_cookie(response)
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    clear_login_cookie(response)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    missing = check_config()
    if missing:
        config_alert = f"""
        <div class="alert">
          Eksik ayarlar var: <b>{e(", ".join(missing))}</b>
          <br>Render > Environment Variables alanından tamamlaman gerekiyor.
        </div>
        """
    else:
        config_alert = f"""
        <div class="alert ok">
          Ayarlar hazır görünüyor. Shop: <b>{e(settings.SHOP_DOMAIN)}</b> | API: <b>{e(settings.API_VERSION)}</b>
        </div>
        """

    recent_jobs = list_jobs(limit=8)

    jobs_html = ""
    if recent_jobs:
        items = []
        for job in recent_jobs:
            status = job["status"]
            items.append(f"""
            <a href="/jobs/{e(job['id'])}">
              <b>{e(job['title'])}</b><br>
              <span class="pill status-{e(status)}">{e(status)}</span>
              <span class="muted small">Başlangıç: {e(job['created_at'])}</span>
            </a>
            """)
        jobs_html = f"""
        <div class="card" style="margin-top:18px;">
          <h2>Son İşlemler</h2>
          <div class="jobs-list">{''.join(items)}</div>
        </div>
        """

    body = f"""
    <h1>Shopify İşlem Paneli</h1>
    {config_alert}

    <div class="grid">
      <div class="card">
        <h2>Tüm Varyant Stoklarını Ayarla</h2>
        <p>Mağazadaki tüm ürün varyantlarının stok miktarını seçtiğin değere çeker. Stok takibi kapalı varyantlar atlanır.</p>
        <form method="post" action="/actions/stocks">
          <label>Hedef stok miktarı</label>
          <input type="number" name="stock_value" value="5" min="0" required>
          <label class="check-row">
            <input type="checkbox" name="dry_run" value="1" checked>
            Önce test modunda çalıştır, gerçek değişiklik yapma
          </label>
          <button type="submit">Stok İşlemini Başlat</button>
        </form>
      </div>

      <div class="card">
        <h2>Alt Kategori Ürünlerini Üst Kategorilere Ekle</h2>
        <p>Menü hiyerarşisine göre alt koleksiyonlardaki ürünleri üst koleksiyonlara ekler. Ürün zaten varsa tekrar eklemez.</p>
        <form method="post" action="/actions/categories">
          <label>Shopify menü handle</label>
          <input type="text" name="menu_handle" placeholder="main-menu veya standort-feste-kategorie" required>
          <label class="check-row">
            <input type="checkbox" name="dry_run" value="1" checked>
            Önce test modunda çalıştır, gerçek değişiklik yapma
          </label>
          <button type="submit">Kategori İşlemini Başlat</button>
        </form>
      </div>
    </div>

    <div class="card" style="margin-top:18px;">
      <h2>v2 Yapısı</h2>
      <p>Bu sürümde işlem kodları tek dosyada değil, <b>actions/</b> klasöründe ayrı ayrı durur.</p>
      <div class="hint">
        Yeni işlem eklerken: <b>actions/yeni_islem.py</b> oluştur, sonra <b>main.py</b> içine yeni buton ve route ekle.
      </div>
    </div>

    {jobs_html}
    """
    return render_layout("Dashboard", body, request)


@app.post("/actions/stocks")
def start_stock_action(request: Request, stock_value: int = Form(...), dry_run: str = Form(None)):
    redirect = require_login(request)
    if redirect:
        return redirect

    dry = dry_run == "1"
    title = f"Stokları {stock_value} yap"
    if dry:
        title += " - TEST"

    job_id = create_job(title)
    run_thread(run_stock_update, job_id, stock_value, dry)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/actions/categories")
def start_category_action(request: Request, menu_handle: str = Form(...), dry_run: str = Form(None)):
    redirect = require_login(request)
    if redirect:
        return redirect

    dry = dry_run == "1"
    title = f"Kategori senkronizasyonu: {menu_handle}"
    if dry:
        title += " - TEST"

    job_id = create_job(title)
    run_thread(run_category_sync, job_id, menu_handle, dry)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str, request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    job = get_job(job_id)

    if not job:
        return render_layout("İş bulunamadı", """
        <div class="card">
          <h1>İş bulunamadı</h1>
          <a class="btn btn-light" href="/dashboard">Panele dön</a>
        </div>
        """, request)

    status = job["status"]
    refresh = 3 if status == "running" else None
    logs = "\n".join(job.get("logs", []))

    body = f"""
    <div class="card">
      <h1>{e(job['title'])}</h1>
      <p>
        <span class="pill status-{e(status)}">{e(status)}</span>
        <span class="muted small">Başlangıç: {e(job['created_at'])}</span>
        {'<span class="muted small"> | Bitiş: ' + e(job.get('finished_at')) + '</span>' if job.get('finished_at') else ''}
      </p>
      <pre>{e(logs)}</pre>
      <a class="btn btn-light" href="/dashboard">Panele dön</a>
    </div>
    """
    return render_layout("İş Detayı", body, request, refresh_seconds=refresh)


@app.get("/health")
def health():
    return {"status": "ok", "version": "v2"}
