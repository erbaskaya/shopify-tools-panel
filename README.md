# Shopify Tools Panel V3

Bu sürümde panelde import/export araçları eklendi.

## Araçlar

1. Ürün import
2. Manuel ve smart kategori import
3. Menü export
4. Menü import
5. Blog import
6. Vendor import

Ayrıca önceki araçlar korunur:

- Tüm varyant stoklarını ayarla
- Alt kategori ürünlerini üst kategorilere ekle

## Önemli

Render sunucusu senin bilgisayarındaki `C:\...` veya `D:\...` dosya yolunu okuyamaz. Bu yüzden import için panelde **dosya seçme butonu** kullanılır.

Export işleminde dosya Render üzerinde oluşturulur ve işlem sayfasında **indir** butonu çıkar. Ona basınca dosya PC'ye iner.

## Render ayarları

Ayarların aynı kalabilir:

```text
Build Command:
pip install -r requirements.txt

Start Command:
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Environment Variables

```text
SHOP_DOMAIN=bzjwyw-jv.myshopify.com
SHOPIFY_ACCESS_TOKEN=yeni_shopify_token
API_VERSION=2026-04
PANEL_PASSWORD=panel_giris_sifren
SECRET_KEY=rastgele_uzun_bir_metin
COOKIE_SECURE=true
```

## Gerekli Shopify izinleri

Custom app token içinde ihtiyaca göre şu izinler olmalı:

```text
read_products
write_products
read_inventory
write_inventory
read_locations
read_online_store_navigation
write_online_store_navigation
read_content
write_content
```

## CSV şablonları

`sample_templates/` klasörü içinde örnek CSV dosyaları vardır.

CSV dosyaları Türkçe Excel için `;` ayırıcıyla hazırlandı. Sistem `;`, `,`, `|` ve tab ayırıcıları okumaya çalışır.

## Ürün import kolonları

```text
handle;title;body_html;vendor;product_type;tags;status;option1_name;option1_value;option2_name;option2_value;sku;price;compare_at_price;barcode;inventory_quantity;cost;image_src
```

Aynı `handle` birden fazla satırda varsa bu satırlar ürünün varyantları olarak işlenir.

## Kategori import kolonları

```text
type;title;handle;body_html;rule_tag;product_handles;image_src;published
```

`type` değeri:

```text
manual
smart
```

Smart kategoride otomatik kural şu şekilde kurulur:

```text
Product tag equals rule_tag
```

`rule_tag` boşsa kategori başlığı kullanılır.

## Menü export/import

En güvenli kullanım:

1. Menü export al
2. Dosyayı düzenle
3. Menü import ile tekrar yükle

Menü import CSV kolonları:

```text
level;position;parent_path;title;type;url;resource_id;resource_handle;resource_title
```

## Blog import kolonları

```text
blog_handle;blog_title;title;handle;author;tags;body_html;summary_html;published;image_src
```

## Vendor import kolonları

Ürünü bulmak için şu alanlardan biri yeterlidir:

```text
product_id
handle
sku
```

Vendor alanı:

```text
vendor
```

## Yeni işlem ekleme

Yeni işlem kodunu `actions/` klasörüne ayrı dosya olarak ekle. Sonra `main.py` içine yeni form ve route ekle.
