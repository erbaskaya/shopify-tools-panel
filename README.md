# Shopify Tools Panel

Bu repo, Render üzerinde çalıştırılabilecek basit bir Python/FastAPI admin panelidir.

Panelde iki işlem vardır:

1. Tüm ürün varyantlarının stok miktarını belirlenen değere çekme
2. Shopify menü hiyerarşisine göre alt koleksiyon ürünlerini üst koleksiyonlara ekleme

## Dosyalar

```text
main.py
requirements.txt
.env.example
.gitignore
render.yaml
```

## Render ayarları

Render üzerinde **New Web Service** seç.

Ayarlar:

```text
Language: Python 3
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
Instance Type: Free
```

## Environment Variables

Render > Environment Variables alanına şunları ekle:

```text
SHOP_DOMAIN=bzjwyw-jv.myshopify.com
SHOPIFY_ACCESS_TOKEN=buraya_yeni_shopify_token
API_VERSION=2026-04
PANEL_PASSWORD=panel_giris_sifren
SECRET_KEY=rastgele_uzun_bir_metin
```

Önemli: Shopify token kod içine yazılmamalıdır.

## Shopify Custom App izinleri

Shopify Admin API token'ında en az şu izinler gerekli olabilir:

```text
read_products
write_products
read_inventory
write_inventory
read_locations
read_online_store_navigation
```

Kategori işlemi için üst koleksiyonların manuel koleksiyon olması gerekir. Otomatik koleksiyonlara manuel ürün eklenemez.

## Kullanım

Deploy bittikten sonra Render sana bir URL verir:

```text
https://shopify-tools-panel.onrender.com
```

Bu adrese girip `PANEL_PASSWORD` ile giriş yap.

Önce her işlemi **test modunda** çalıştır. Log doğru görünüyorsa test kutucuğunu kaldırıp gerçek işlemi başlat.
