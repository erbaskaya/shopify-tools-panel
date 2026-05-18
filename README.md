# Shopify Tools Panel V2

Bu sürüm modüler yapıya çevrilmiştir.

## Klasör yapısı

```text
shopify-tools-panel/
├── main.py
├── requirements.txt
├── render.yaml
├── core/
│   ├── __init__.py
│   ├── auth.py
│   ├── config.py
│   ├── job_manager.py
│   └── shopify_client.py
└── actions/
    ├── __init__.py
    ├── stock_update.py
    ├── category_sync.py
    └── example_new_action.py
```

## Render ayarları

Render'daki ayarların aynı kalabilir:

```text
Build Command:
pip install -r requirements.txt

Start Command:
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Environment Variables

Render > Environment Variables alanında bunlar olmalı:

```text
SHOP_DOMAIN=bzjwyw-jv.myshopify.com
SHOPIFY_ACCESS_TOKEN=yeni_shopify_token
API_VERSION=2026-04
PANEL_PASSWORD=panel_giris_sifren
SECRET_KEY=rastgele_uzun_bir_metin
```

Opsiyonel:

```text
COOKIE_SECURE=true
```

Render üzerinde `COOKIE_SECURE=true` kalsın. Lokal bilgisayarda HTTP ile test edeceksen `COOKIE_SECURE=false` yapabilirsin.

## Yeni işlem nasıl eklenir?

Örnek:

```text
actions/sale_add.py
```

dosyasını oluştur.

İçinde standart fonksiyon şöyle olmalı:

```python
def run(job_id, dry_run):
    ...
```

Sonra `main.py` içine import ekle:

```python
from actions.sale_add import run as run_sale_add
```

Dashboard'a yeni kart/form ekle.

Route ekle:

```python
@app.post("/actions/sale-add")
def start_sale_add(request: Request, dry_run: str = Form(None)):
    redirect = require_login(request)
    if redirect:
        return redirect

    dry = dry_run == "1"
    job_id = create_job("Sale ekleme - TEST" if dry else "Sale ekleme")
    run_thread(run_sale_add, job_id, dry)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)
```

## Mevcut işlemler

1. Tüm varyant stoklarını istenen değere çekme
2. Menü hiyerarşisine göre alt koleksiyon ürünlerini üst koleksiyonlara ekleme

Her iki işlemde de test modu vardır.
