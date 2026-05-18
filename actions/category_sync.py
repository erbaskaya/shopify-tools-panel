import time
from collections import defaultdict

from core.config import check_config
from core.job_manager import finish_job, log
from core.shopify_client import ShopifyClient


def get_menu_id_by_handle(job_id, client, menu_handle):
    query = """
    query GetMenus($first: Int!, $after: String) {
      menus(first: $first, after: $after) {
        edges {
          cursor
          node {
            id
            handle
            title
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    after = None

    while True:
        data = client.gql(query, {"first": 250, "after": after})

        for edge in data["menus"]["edges"]:
            menu = edge["node"]
            if menu["handle"] == menu_handle:
                log(job_id, f"Menü bulundu: {menu['title']} | Handle: {menu['handle']}")
                return menu["id"]

        page_info = data["menus"]["pageInfo"]

        if not page_info["hasNextPage"]:
            break

        after = page_info["endCursor"]

    raise Exception(f"Menü bulunamadı: {menu_handle}")


def get_menu_tree(job_id, client, menu_id):
    query = """
    query GetMenu($id: ID!) {
      menu(id: $id) {
        id
        title
        handle
        items {
          id
          title
          type
          resourceId
          url
          items {
            id
            title
            type
            resourceId
            url
            items {
              id
              title
              type
              resourceId
              url
              items {
                id
                title
                type
                resourceId
                url
              }
            }
          }
        }
      }
    }
    """

    data = client.gql(query, {"id": menu_id})
    menu = data.get("menu")

    if not menu:
        raise Exception("Menü okunamadı.")

    log(job_id, f"Menü ağacı okundu: {menu.get('title')}")
    return menu


def is_collection_item(item):
    resource_id = item.get("resourceId")

    return (
        item.get("type") == "COLLECTION"
        and resource_id
        and resource_id.startswith("gid://shopify/Collection/")
    )


def build_child_to_parent_map(items, ancestor_collections=None, result=None):
    if ancestor_collections is None:
        ancestor_collections = []

    if result is None:
        result = defaultdict(set)

    for item in items:
        current_collection_id = item.get("resourceId") if is_collection_item(item) else None

        if current_collection_id and ancestor_collections:
            for parent_id in ancestor_collections:
                result[current_collection_id].add(parent_id)

        next_ancestors = list(ancestor_collections)

        if current_collection_id:
            next_ancestors.append(current_collection_id)

        children = item.get("items") or []

        if children:
            build_child_to_parent_map(children, next_ancestors, result)

    return result


def get_collection_info(client, collection_id):
    query = """
    query GetCollectionInfo($id: ID!) {
      node(id: $id) {
        ... on Collection {
          id
          title
          handle
          ruleSet {
            appliedDisjunctively
          }
        }
      }
    }
    """

    data = client.gql(query, {"id": collection_id})
    node = data.get("node")

    if not node:
        return {
            "id": collection_id,
            "title": collection_id,
            "handle": "",
            "is_smart": False,
        }

    return {
        "id": node["id"],
        "title": node.get("title", ""),
        "handle": node.get("handle", ""),
        "is_smart": node.get("ruleSet") is not None,
    }


def get_collection_product_ids(job_id, client, collection_id):
    query = """
    query GetCollectionProducts($id: ID!, $first: Int!, $after: String) {
      node(id: $id) {
        ... on Collection {
          id
          title
          products(first: $first, after: $after) {
            edges {
              cursor
              node {
                id
                title
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
    """

    product_ids = set()
    after = None

    while True:
        data = client.gql(query, {
            "id": collection_id,
            "first": 250,
            "after": after,
        })

        node = data.get("node")

        if not node:
            log(job_id, f"UYARI: Koleksiyon okunamadı: {collection_id}")
            return set()

        for edge in node["products"]["edges"]:
            product_ids.add(edge["node"]["id"])

        page_info = node["products"]["pageInfo"]

        if not page_info["hasNextPage"]:
            break

        after = page_info["endCursor"]

    return product_ids


def chunk_list(items, size):
    items = list(items)

    for i in range(0, len(items), size):
        yield items[i:i + size]


def add_missing_products_to_collection(job_id, client, parent_collection_id, missing_product_ids, dry_run):
    mutation = """
    mutation AddProductsToCollection($id: ID!, $productIds: [ID!]!) {
      collectionAddProducts(id: $id, productIds: $productIds) {
        collection {
          id
          title
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    if not missing_product_ids:
        return 0

    added_total = 0

    for batch in chunk_list(missing_product_ids, 200):
        if dry_run:
            log(job_id, f"TEST: {len(batch)} eksik ürün eklenecekti.")
            added_total += len(batch)
            continue

        data = client.gql(mutation, {
            "id": parent_collection_id,
            "productIds": batch,
        })

        result = data["collectionAddProducts"]
        errors = result.get("userErrors") or []

        if errors:
            log(job_id, f"HATA: Koleksiyona ekleme başarısız: {parent_collection_id}")

            for error in errors:
                log(job_id, f"  Field: {error.get('field')} | Message: {error.get('message')}")

            continue

        collection_title = result["collection"]["title"]
        log(job_id, f"OK: {len(batch)} eksik ürün eklendi -> {collection_title}")

        added_total += len(batch)
        time.sleep(0.25)

    return added_total


def run(job_id, menu_handle, dry_run):
    try:
        missing = check_config()
        if missing:
            raise Exception(f"Eksik ENV ayarları: {', '.join(missing)}")

        client = ShopifyClient(job_id)

        menu_handle = menu_handle.strip()

        if not menu_handle:
            raise Exception("Menü handle boş olamaz.")

        log(job_id, f"Menü handle: {menu_handle}")
        log(job_id, f"DRY_RUN: {dry_run}")

        menu_id = get_menu_id_by_handle(job_id, client, menu_handle)
        menu = get_menu_tree(job_id, client, menu_id)

        child_to_parents = build_child_to_parent_map(menu.get("items", []))

        if not child_to_parents:
            log(job_id, "Menüde alt/üst koleksiyon ilişkisi bulunamadı.")
            finish_job(job_id, "done")
            return

        log(job_id, f"Bulunan alt kategori sayısı: {len(child_to_parents)}")

        total_added = 0
        total_already_exists = 0
        total_skipped_smart = 0
        total_empty_child = 0

        parent_products_cache = {}

        for child_collection_id, parent_collection_ids in child_to_parents.items():
            child_info = get_collection_info(client, child_collection_id)
            child_product_ids = get_collection_product_ids(job_id, client, child_collection_id)

            log(job_id, "--------------------------------------------------")
            log(job_id, f"ALT KATEGORİ: {child_info['title']} ({child_info['handle']})")
            log(job_id, f"Alt kategorideki ürün sayısı: {len(child_product_ids)}")

            if not child_product_ids:
                total_empty_child += 1
                log(job_id, "ATLANDI: Alt kategoride ürün yok.")
                continue

            for parent_collection_id in parent_collection_ids:
                parent_info = get_collection_info(client, parent_collection_id)
                log(job_id, f"ÜST KATEGORİ: {parent_info['title']} ({parent_info['handle']})")

                if parent_info["is_smart"]:
                    total_skipped_smart += 1
                    log(job_id, "ATLANDI: Bu üst kategori otomatik koleksiyon. Manuel ürün eklenemez.")
                    continue

                if parent_collection_id not in parent_products_cache:
                    parent_products_cache[parent_collection_id] = get_collection_product_ids(
                        job_id,
                        client,
                        parent_collection_id,
                    )

                parent_existing_product_ids = parent_products_cache[parent_collection_id]

                already_existing_product_ids = child_product_ids.intersection(parent_existing_product_ids)
                missing_product_ids = child_product_ids.difference(parent_existing_product_ids)

                log(job_id, f"Zaten üst kategoride olan ürün: {len(already_existing_product_ids)}")
                log(job_id, f"Yeni eklenecek eksik ürün: {len(missing_product_ids)}")

                total_already_exists += len(already_existing_product_ids)

                if not missing_product_ids:
                    log(job_id, "OK: Eklenecek eksik ürün yok. Aynı ürün tekrar eklenmedi.")
                    continue

                added_count = add_missing_products_to_collection(
                    job_id,
                    client,
                    parent_collection_id,
                    missing_product_ids,
                    dry_run,
                )

                total_added += added_count
                parent_products_cache[parent_collection_id].update(missing_product_ids)

        log(job_id, "İŞLEM BİTTİ")
        log(job_id, f"Yeni eklenen / eklenecek ürün-kategori ilişkisi: {total_added}")
        log(job_id, f"Zaten mevcut olduğu için tekrar eklenmeyen ilişki: {total_already_exists}")
        log(job_id, f"Otomatik koleksiyon olduğu için atlanan üst kategori: {total_skipped_smart}")
        log(job_id, f"Ürünü olmadığı için atlanan alt kategori: {total_empty_child}")

        finish_job(job_id, "done")

    except Exception as exc:
        log(job_id, f"GENEL HATA: {exc}")
        finish_job(job_id, "error")
