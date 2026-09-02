# Source adapters

`engine/source-ingest.py` is Shopbot's discovery boundary for retailer catalogs that do not fit the live browser-category crawler. It normalizes public sitemaps and merchant/affiliate feeds into `data/ingestion-candidates.json`.

Candidates are always leads. A sitemap or feed may discover a product, image, price, or availability, but only a current PDP verification may become purchase-ready evidence.

## Supported adapters

| Method | Use it for | Required configuration |
| --- | --- | --- |
| `sitemap-xml` | XML sitemap indexes, URL sets, image sitemaps, and `.gz` sitemap shards | `urls`, `allowedHosts`, `sitemapPathPattern`, `productPathPattern` |
| `json-feed` | Merchant APIs and JSON affiliate feeds | `urls` or `urlTemplate`, `allowedHosts`, `productPathPattern`, `itemsPath`, `mapping` |
| `csv-feed` | CSV affiliate/product feeds | `urls` or `urlTemplate`, `allowedHosts`, `productPathPattern`, `mapping` |
| `xml-feed` | XML/RSS affiliate/product feeds | `urls` or `urlTemplate`, `allowedHosts`, `productPathPattern`, `itemPath`, `mapping` |
| `shopify-products-json` | Public Shopify collection feeds | Existing `engine/scout-shopify.py` lead path |
| `self-hosted-browser` | Rendered official men's categories followed by fresh PDP verification | Existing `engine/scout-browser.py` verified path |

The feed mappings may populate `url`, `title`, `brand`, `sku`, `category`, `imageUrl`, `price`, `originalPrice`, `currency`, `availability`, and `lastModified`. JSON paths use dotted keys and numeric list indexes, such as `offers.0.price`. A mapping value may be a list of fallback paths.

## Sitemap example

```json
{
  "id": "levis",
  "name": "Levi's",
  "fetch": {
    "method": "sitemap-xml",
    "urls": ["https://www.levi.com/US/en_US/sitemap.xml"],
    "allowedHosts": ["www.levi.com"],
    "sitemapPathPattern": "^/US/en_US/sitemap(?:\\.xml|/medias/Product-en-US-USD-\\d+\\.xml)$",
    "productPathPattern": "^/US/en_US/(?:clothing/men/|jeans-by-fit-number/men/).+/p/\\d+$",
    "maxSitemaps": 120,
    "maxCandidates": 10000,
    "delaySeconds": 0.1
  }
}
```

## JSON feed example

```json
{
  "method": "json-feed",
  "urlTemplate": "https://feed.example/products?page={page}",
  "pagination": { "start": 1, "maxPages": 20 },
  "allowedHosts": ["feed.example", "shop.example"],
  "productPathPattern": "^/products/",
  "itemsPath": "data.products",
  "mapping": {
    "url": "link",
    "title": "name",
    "sku": "id",
    "imageUrl": ["image.url", "images.0.url"],
    "price": "offers.0.price",
    "currency": "offers.0.currency",
    "availability": "offers.0.availability"
  }
}
```

CSV mappings use column headers. XML mappings use child paths relative to `itemPath`.

## Authentication and safety

- Feed secrets never belong in `config/sources.json`. `headersEnv` maps an HTTP header to an environment-variable name, for example `{ "Authorization": "SHOPBOT_UO_FEED_AUTH" }`.
- Retrieval accepts HTTPS only, enforces allowed hosts and path patterns, caps responses at 50 MiB, bounds sitemap recursion and pagination, and retries only transient failures.
- A failed source preserves its last good candidates. A bounded partial sitemap run also retains previously seen candidates that were outside the new scan.
- The adapter does not solve CAPTCHAs, rotate identities, or bypass access controls. A normal manually completed headed-browser challenge may supply an ordinary local session for the existing browser verifier.

## Commands

```bash
npm run ingest:sources -- --source levis --dry-run
npm run ingest:sources -- --source levis
npm run test:ingest
```

Use `--max-sitemaps` and `--max-candidates` for bounded probes. Prefer `--dry-run` for a deliberately partial test.
