import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("source-ingest.py")
SPEC = importlib.util.spec_from_file_location("source_ingest", MODULE_PATH)
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


def source(method, **fetch_overrides):
    fetch = {
        "method": method,
        "urls": ["https://catalog.example/feed"],
        "allowedHosts": ["catalog.example", "shop.example"],
        "productPathPattern": r"^/men/.+",
        **fetch_overrides,
    }
    return {"id": "example", "name": "Example", "fetch": fetch}


def main():
    assert INGEST.canonical_url("https://SHOP.example/men/jeans?x=1#blue") == "https://shop.example/men/jeans"
    assert INGEST.canonical_url("http://shop.example/men/jeans") == ""
    assert INGEST.canonical_url("https://shop.example:bad/men/jeans") == ""
    assert INGEST.allowed_fetch_url("https://catalog.example/feed", source("json-feed", mapping={"url": "url"})["fetch"]) is True
    assert INGEST.allowed_fetch_url("https://evil.example/feed", source("json-feed", mapping={"url": "url"})["fetch"]) is False

    sitemap_source = source(
        "sitemap-xml",
        urls=["https://catalog.example/sitemap.xml"],
        sitemapPathPattern=r"^/.*\.xml$",
        maxSitemaps=5,
    )
    index = b'''<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://catalog.example/products.xml</loc></sitemap><sitemap><loc>https://evil.example/products.xml</loc></sitemap></sitemapindex>'''
    products = b'''<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"><url><loc>https://shop.example/men/relaxed-jeans/p/123</loc><lastmod>2026-09-01</lastmod><image:image><image:loc>https://shop.example/men/123.jpg</image:loc></image:image></url><url><loc>https://shop.example/women/jeans/p/999</loc></url></urlset>'''
    calls = []

    def sitemap_fetcher(url, _fetch):
        calls.append(url)
        return index if url.endswith("sitemap.xml") else products

    candidates, stats = INGEST.ingest_source(sitemap_source, "2026-09-01T00:00:00Z", sitemap_fetcher)
    assert calls == ["https://catalog.example/sitemap.xml", "https://catalog.example/products.xml"]
    assert stats == {"sitemapsRead": 2, "queuedSitemapsRemaining": 0, "rawCandidates": 2, "acceptedCandidates": 1}
    assert candidates[0]["title"] == "Relaxed Jeans"
    assert candidates[0]["imageUrl"] == "https://shop.example/men/123.jpg"
    assert candidates[0]["sku"] == "123"
    assert candidates[0]["evidence"]["status"] == "lead"
    assert candidates[0]["lastModified"] == "2026-09-01"

    json_source = source(
        "json-feed",
        itemsPath="data.products",
        mapping={"url": "link", "title": "name", "price": "offers.0.price", "currency": "offers.0.currency", "sku": "id"},
    )
    json_payload = {"data": {"products": [{"id": "sku1", "link": "https://shop.example/men/chore-coat", "name": "Chore Coat", "offers": [{"price": "$129.50", "currency": "usd"}]}]}}
    candidates, stats = INGEST.ingest_source(json_source, "now", lambda _url, _fetch: json.dumps(json_payload).encode())
    assert stats == {"feedRequests": 1, "rawCandidates": 1, "acceptedCandidates": 1}
    assert candidates[0]["price"] == {"amount": 129.5, "currency": "USD"}
    assert candidates[0]["sku"] == "sku1"

    csv_source = source("csv-feed", mapping={"url": "product_url", "title": "product_name", "price": "sale_price", "currency": "currency"})
    csv_payload = b"product_url,product_name,sale_price,currency\nhttps://shop.example/men/wide-pants,Wide Pants,89.00,USD\n"
    candidates, _ = INGEST.ingest_source(csv_source, "now", lambda _url, _fetch: csv_payload)
    assert candidates[0]["title"] == "Wide Pants"
    assert candidates[0]["price"]["amount"] == 89.0

    xml_source = source("xml-feed", itemPath="channel/item", mapping={"url": "link", "title": "title", "price": "price", "currency": "currency"})
    xml_payload = b"<rss><channel><item><link>https://shop.example/men/knit-polo</link><title>Knit Polo</title><price>59.90 USD</price><currency>USD</currency></item></channel></rss>"
    candidates, _ = INGEST.ingest_source(xml_source, "now", lambda _url, _fetch: xml_payload)
    assert candidates[0]["title"] == "Knit Polo"
    assert candidates[0]["price"]["amount"] == 59.9

    paged = INGEST.feed_urls({"urlTemplate": "https://catalog.example/products?page={page}", "pagination": {"start": 2, "maxPages": 3}})
    assert paged == ["https://catalog.example/products?page=2", "https://catalog.example/products?page=3", "https://catalog.example/products?page=4"]

    bad = source("json-feed", mapping={"url": "url"})
    bad["fetch"]["productPathPattern"] = "["
    assert any("invalid productPathPattern" in error for error in INGEST.source_contract_errors(bad))
    missing_secret = source("json-feed", mapping={"url": "url"}, headersEnv={"Authorization": "SHOPBOT_MISSING_TEST_TOKEN"})
    try:
        INGEST.request_headers(missing_secret["fetch"])
        raise AssertionError("missing header secret should fail")
    except INGEST.IngestError as error:
        assert "SHOPBOT_MISSING_TEST_TOKEN" in str(error)

    print("source ingestion tests: 23 checks passed, 0 failed")


if __name__ == "__main__":
    main()
