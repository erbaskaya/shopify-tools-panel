# Mağaza Yönetimi - Kurulum

## EXE / Local
Ek ayar gerekmez. Panelden eklenen mağazalar `data/stores.json` içinde şifreli token ile saklanır.

## Vercel
Vercel dosya sistemi kalıcı olmadığı için panelden mağaza eklemek için PostgreSQL gerekir.

1. Vercel projesine Neon/Postgres bağlayın.
2. `DATABASE_URL` Environment Variable oluştuğunu kontrol edin.
3. Redeploy yapın.
4. Panel > Mağaza Yönetimi sayfasını açın.
5. Mevcut `SHOPIFY_STORES_JSON` mağazaları varsa `ENV Mağazalarını İçe Aktar` butonuna basın.
6. Bağlantı testleri başarılı olduktan sonra `SHOPIFY_STORES_JSON` değişkenini kaldırabilirsiniz.

Tokenlar veritabanında `SECRET_KEY` türeviyle şifrelenir; arayüzde tam token geri gösterilmez.
