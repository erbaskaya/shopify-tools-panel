"""
Yeni işlem eklemek için örnek şablon.

1. Bu dosyayı kopyala.
2. Dosya adını değiştir: actions/sale_add.py gibi.
3. run() fonksiyonunun içini kendi Shopify işleminle doldur.
4. main.py içine import, buton ve route ekle.
"""

from core.config import check_config
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient


def run(job_id, dry_run=True):
    try:
        missing = check_config()
        if missing:
            raise Exception(f"Eksik ENV ayarları: {', '.join(missing)}")

        client = ShopifyClient(job_id)

        log(job_id, "Yeni işlem başladı.")
        log(job_id, f"DRY_RUN: {dry_run}")

        # Örnek GraphQL sorgu:
        # data = client.gql("""
        # query {
        #   shop {
        #     name
        #   }
        # }
        # """)
        # log(job_id, f"Shop adı: {data['shop']['name']}")

        if dry_run:
            log(job_id, "TEST MODU: Gerçek değişiklik yapılmadı.")
        else:
            log(job_id, "Burada gerçek Shopify işlemi yapılacak.")

        log(job_id, "Yeni işlem tamamlandı.")
        finish_job(job_id, "done")

    except Exception as exc:
        log(job_id, f"GENEL HATA: {exc}")
        finish_job(job_id, "error")
