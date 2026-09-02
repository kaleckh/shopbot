import asyncio
import importlib.util
import json
from types import SimpleNamespace
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("scout-browser.py")
SPEC = importlib.util.spec_from_file_location("scout_browser", MODULE_PATH)
BROWSER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BROWSER)


def product(title="RELAXED FIT JEANS", url="https://www.zara.com/us/en/relaxed-fit-jeans-p00840442.html"):
    return {
        "title": title,
        "brand": "ZARA",
        "category": "Clothing > Pants > Jeans",
        "url": url,
        "description": "Relaxed straight-leg cotton denim.",
        "variants": [
            {
                "id": "sku-30",
                "sku": "sku-30",
                "price": {"amount": 79.9, "currency": "USD"},
                "availability": {"inStock": True, "text": "In stock"},
                "images": [{"url": "https://static.zara.net/product.jpg"}],
            },
            {
                "id": "sku-32",
                "sku": "sku-32",
                "price": {"amount": 89.9, "currency": "USD"},
                "originalPrice": {"amount": 99.9, "currency": "USD"},
                "availability": {"inStock": False, "text": "Out of stock"},
                "images": [],
            },
        ],
    }


def main():
    source = {
        "id": "zara-us",
        "name": "Zara",
        "tasteFit": "relaxed denim",
        "fetch": {
            "urls": ["https://www.zara.com/us/en/man-jeans-l659.html"],
            "allowedHosts": ["www.zara.com"],
            "productPathPattern": r"^/us/en/.+-p\d+\.html$",
            "audienceCategoryPathPattern": r"^/us/en/man-.*-l\d+\.html$",
        },
        "catalogPolicy": {
            "initialTarget": 4,
            "maxUnreviewed": 4,
            "newPerRefresh": 2,
            "activeCeiling": 6,
            "bootstrapPerCategory": 2,
            "refreshLikedLimit": 2,
        },
        "categories": ["outerwear", "pants"],
    }
    category_html = """
      <html><head><title>Men's Jeans | ZARA United States</title></head><body>
      <a href="/us/en/relaxed-fit-jeans-p00840442.html?color=blue">RELAXED FIT JEANS</a>
      <a href="https://evil.example/us/en/relaxed-fit-jeans-p00840442.html">wrong host</a>
      </body></html>
    """
    category = {
        "url": "https://www.zara.com/us/en/man-jeans-l659.html",
        "html": category_html,
        "links": [],
    }
    assert BROWSER.source_contract_errors(source) == []
    invalid_source = dict(source, fetch=dict(source["fetch"], productPathPattern="["))
    assert any("invalid productPathPattern" in error for error in BROWSER.source_contract_errors(invalid_source))
    assert BROWSER.canonical_url("https://example.com:bad/item") == ""
    refs = BROWSER.product_refs_from_pages([category], source)
    assert len(refs) == 1
    assert refs[0]["url"].endswith("p00840442.html")
    assert BROWSER.canonical_url(refs[0]["url"] + "?color=blue#size") == refs[0]["url"]
    assert refs[0]["discoveryTitle"] == "RELAXED FIT JEANS"
    assert refs[0]["audienceEvidence"]["categoryUrl"] == category["url"]

    direct_pdp = {"url": refs[0]["url"], "html": category_html, "links": []}
    assert BROWSER.product_refs_from_pages([direct_pdp], source) == []
    women_category = dict(category, url="https://www.zara.com/us/en/woman-jeans-l1119.html")
    assert BROWSER.product_refs_from_pages([women_category], source) == []

    record = BROWSER.product_to_record(product(), source, refs[0], "2026-09-01T00:00:00Z", cache_images=False)
    assert record["id"] == "zara-us-relaxed-fit-jeans-p00840442"
    assert record["category"] == "pants"
    assert record["priceUSD"] == 79.9
    assert record["listPriceUSD"] == 99.9
    assert record["verification"]["status"] == "verified"
    assert record["verification"]["stock"] == "in-stock"
    assert record["provenance"]["audienceEvidence"]["categoryUrl"] == category["url"]
    assert record["imageUrl"] == "https://static.zara.net/product.jpg"

    protocol_relative = product()
    protocol_relative["variants"][0]["images"] = [{"url": "//static.zara.net/protocol-relative.jpg"}]
    protocol_record = BROWSER.product_to_record(protocol_relative, source, refs[0], "now", cache_images=False)
    assert protocol_record["imageUrl"] == "https://static.zara.net/protocol-relative.jpg"

    unknown_stock = product()
    unknown_stock["variants"][0].pop("availability")
    unknown_stock["variants"][1].pop("availability")
    assert BROWSER.product_to_record(unknown_stock, source, refs[0], "now", cache_images=False)["verification"]["stock"] == "unknown"

    rules = {"skipProductContains": ["women", "womens", "skinny", "slim"]}
    assert BROWSER.product_to_record(product("SKINNY FIT JEANS"), source, refs[0], "now", rules, cache_images=False) is None
    assert BROWSER.product_to_record(product(url="https://evil.example/item-p00840442.html"), source, refs[0], "now", rules, cache_images=False) is None

    existing = {"schemaVersion": 2, "suggestions": [{"id": record["id"], "title": "old", "provenance": {"checkedBy": BROWSER.LEGACY_CHECKED_BY}}, {"id": "curated", "title": "keep", "provenance": {"checkedBy": "human"}}]}
    merged, counts = BROWSER.merge_records(existing, [record])
    assert counts == {"added": 0, "updated": 1}
    assert len(merged["suggestions"]) == 2
    assert next(item for item in merged["suggestions"] if item["id"] == record["id"])["title"] == record["title"]
    merged_again, counts_again = BROWSER.merge_records(merged, [record])
    assert counts_again == {"added": 0, "updated": 1}
    assert len(merged_again["suggestions"]) == 2

    outerwear_ref = {
        "url": "https://www.zara.com/us/en/relaxed-denim-jacket-p00000001.html",
        "discoveryTitle": "RELAXED DENIM JACKET",
        "audienceEvidence": refs[0]["audienceEvidence"],
    }
    pants_ref_2 = {
        "url": "https://www.zara.com/us/en/wide-utility-pants-p00000002.html",
        "discoveryTitle": "WIDE UTILITY PANTS",
        "audienceEvidence": refs[0]["audienceEvidence"],
    }
    skinny_ref = {
        "url": "https://www.zara.com/us/en/skinny-jeans-p00000003.html",
        "discoveryTitle": "SKINNY JEANS",
        "audienceEvidence": refs[0]["audienceEvidence"],
    }
    plan = BROWSER.plan_source(
        {"suggestions": []},
        {},
        [refs[0], outerwear_ref, pants_ref_2, skinny_ref],
        source,
        rules,
    )
    assert plan["newBudget"] == 4
    assert [item["category"] for item in plan["newRefs"][:2]] == ["outerwear", "pants"]
    assert len(plan["newRefs"]) == 3
    assert plan["rejectedBeforeScrape"] == {"excluded-product-signal": 1}

    owned = dict(record)
    owned["provenance"] = dict(record["provenance"], sourceId="zara-us")
    owned["category"] = "pants"
    owned_outerwear = dict(record, id="zara-us-old-jacket", url=outerwear_ref["url"], category="outerwear")
    owned_outerwear["provenance"] = dict(record["provenance"], sourceId="zara-us")
    full_existing = {"suggestions": [owned, owned_outerwear]}
    misclassified = dict(owned_outerwear, title="RELAXED DENIM HOODIE JACKET", category="knit")
    normalization_fixture = {"suggestions": [misclassified]}
    assert BROWSER.normalize_owned_categories(normalization_fixture, source) == 1
    assert misclassified["category"] == "outerwear"
    legacy_owned = dict(record)
    legacy_owned["provenance"] = {"checkedBy": BROWSER.LEGACY_CHECKED_BY}
    legacy_fixture = {"suggestions": [legacy_owned]}
    assert BROWSER.normalize_owned_categories(legacy_fixture, source) == 1
    assert legacy_owned["provenance"]["sourceId"] == "zara-us"
    blocked_plan = BROWSER.plan_source(full_existing, {}, [refs[0], outerwear_ref, pants_ref_2], source, rules)
    assert blocked_plan["newBudget"] == 2
    assert len(blocked_plan["newRefs"]) == 1
    reviewed_plan = BROWSER.plan_source(full_existing, {owned["id"]: {"vote": 2}, owned_outerwear["id"]: {"vote": -2}}, [refs[0], outerwear_ref, pants_ref_2], source, rules)
    assert reviewed_plan["refreshRecords"][0]["id"] == owned["id"]
    assert reviewed_plan["activeBefore"] == 1

    at_backpressure = {"suggestions": [dict(owned, id=f"zara-us-{index}") for index in range(4)]}
    backpressure_plan = BROWSER.plan_source(at_backpressure, {}, [pants_ref_2], source, rules)
    assert backpressure_plan["newBudget"] == 0
    assert backpressure_plan["backpressure"] is True

    product_json = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "RELAXED FIT JEANS",
        "brand": {"@type": "Brand", "name": "ZARA"},
        "description": "Relaxed straight-leg cotton denim.",
        "category": "Jeans",
        "image": ["https://static.zara.net/product.jpg"],
        "offers": [
            {
                "@type": "Offer",
                "sku": "sku-30",
                "price": "79.90",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock",
            }
        ],
    }
    page = {
        "url": refs[0]["url"],
        "status": 200,
        "html": f'<html><head><script type="application/ld+json">{json.dumps(product_json)}</script></head></html>',
    }
    extracted = BROWSER.product_from_page(page, refs[0]["url"])
    assert extracted["title"] == "RELAXED FIT JEANS"
    assert extracted["variants"][0]["price"] == {"amount": 79.9, "currency": "USD"}
    assert extracted["variants"][0]["availability"]["inStock"] is True
    assert extracted["variants"][0]["images"][0]["url"] == "https://static.zara.net/product.jpg"
    assert extracted["extractionMethod"] == "json-ld-product"
    aggregate = BROWSER.normalize_offer({"lowPrice": 50, "highPrice": 80, "priceCurrency": "USD"}, [])
    assert "originalPrice" not in aggregate
    sale = BROWSER.normalize_offer({"price": 80, "priceCurrency": "USD", "priceSpecification": [{"price": 100, "priceCurrency": "USD"}]}, [])
    assert sale["originalPrice"]["amount"] == 100

    group_json = dict(product_json, **{
        "@type": "ProductGroup",
        "offers": None,
        "hasVariant": [{
            "@type": "Product",
            "sku": "sku-group-m",
            "image": ["https://static.zara.net/group.jpg"],
            "offers": product_json["offers"][0],
        }],
    })
    group_page = dict(page, html=f'<script type="application/ld+json">{json.dumps(group_json)}</script>')
    group_product = BROWSER.product_from_page(group_page, refs[0]["url"])
    assert group_product["variants"][0]["sku"] == "sku-group-m"
    assert group_product["variants"][0]["images"][0]["url"] == "https://static.zara.net/group.jpg"
    assert group_product["extractionMethod"] == "json-ld-product-group"

    embedded_page = dict(
        page,
        html=f'<script id="__NEXT_DATA__" type="application/json">{json.dumps({"props": {"product": product_json}})}</script>',
    )
    assert BROWSER.product_from_page(embedded_page, refs[0]["url"])["extractionMethod"] == "embedded-json-product"

    meta_page = {
        "url": refs[0]["url"],
        "status": 200,
        "html": '<meta property="og:title" content="RELAXED JEANS"><meta property="og:image" content="https://static.zara.net/meta.jpg"><meta property="product:price:amount" content="69.90"><meta property="product:price:currency" content="USD">',
    }
    assert BROWSER.product_from_page(meta_page, refs[0]["url"])["variants"][0]["price"]["amount"] == 69.9
    itemprop_page = {
        "url": refs[0]["url"],
        "status": 200,
        "html": '<meta property="og:title" content="RELAXED JEANS"><meta property="og:image" content="https://static.zara.net/itemprop.jpg"><meta itemprop="priceCurrency" content="USD"><data itemprop="price" data-currency="USD" value="64.90"></data>',
    }
    itemprop_product = BROWSER.product_from_page(itemprop_page, refs[0]["url"])
    assert itemprop_product["variants"][0]["price"] == {"amount": 64.9, "currency": "USD"}
    assert itemprop_product["extractionMethod"] == "rendered-product-metadata"
    assert BROWSER.is_challenge_html('<meta http-equiv="refresh" content="5; URL=?bm-verify=abc">') is True
    try:
        BROWSER.product_from_page({"url": refs[0]["url"], "status": 403, "html": "<h1>Access Denied</h1> Akamai"}, refs[0]["url"])
        raise AssertionError("challenge should fail")
    except BROWSER.CrawlError as error:
        assert error.blocked is True

    class FakeCrawler:
        def __init__(self, results):
            self.results = list(results)

        async def arun(self, **_kwargs):
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    retry_client = BROWSER.Crawl4AIClient(config_factory=lambda kind, attempt: (kind, attempt), sleeper=fake_sleep)
    retry_client.crawler = FakeCrawler([
        SimpleNamespace(success=False, status_code=500, html="", error_message="temporary"),
        SimpleNamespace(success=True, status_code=200, html="<html>" + ("ok" * 300) + "</html>", url=refs[0]["url"], links={}, cache_status="miss"),
    ])
    retried = asyncio.run(retry_client.fetch(refs[0]["url"], "product"))
    assert retried["status"] == 200
    assert retry_client.network_attempts == {"product": 2}
    assert sleeps == [0.75]

    blocked_client = BROWSER.Crawl4AIClient(config_factory=lambda kind, attempt: (kind, attempt), sleeper=fake_sleep)
    blocked_client.crawler = FakeCrawler([
        SimpleNamespace(success=False, status_code=403, html="<h1>Access Denied</h1>", error_message="forbidden"),
    ])
    try:
        asyncio.run(blocked_client.fetch(refs[0]["url"], "product"))
        raise AssertionError("blocked response should fail without retry")
    except BROWSER.CrawlError as error:
        assert error.blocked is True
    assert blocked_client.network_attempts == {"product": 1}

    tiny_client = BROWSER.Crawl4AIClient(config_factory=lambda kind, attempt: (kind, attempt), sleeper=fake_sleep)
    tiny_client.crawler = FakeCrawler([
        SimpleNamespace(success=True, status_code=200, html="<html></html>", url=refs[0]["url"], links={}, cache_status="hit"),
        SimpleNamespace(success=True, status_code=200, html="<html>" + ("x" * 600) + "</html>", url=refs[0]["url"], links={}, cache_status="miss"),
    ])
    assert asyncio.run(tiny_client.fetch(refs[0]["url"], "category"))["status"] == 200
    assert tiny_client.network_attempts == {"category": 2}
    assert BROWSER.is_block_message("Blocked by anti-bot protection: DataDome captcha") is True

    transport_client = BROWSER.Crawl4AIClient(config_factory=lambda kind, attempt: (kind, attempt), sleeper=fake_sleep)
    transport_client.crawler = FakeCrawler([
        RuntimeError("browser closed"),
        SimpleNamespace(success=True, status_code=200, html="<html>" + ("ok" * 300) + "</html>", url=refs[0]["url"], links={}, cache_status="miss"),
    ])
    assert asyncio.run(transport_client.fetch(refs[0]["url"], "product"))["status"] == 200
    assert transport_client.network_attempts == {"product": 2}
    print("browser scout tests: 68 assertions passed, 0 failed")


if __name__ == "__main__":
    main()
