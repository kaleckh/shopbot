# Pull taste-matched leads from Shopify products.json endpoints listed in
# config/sources.json. Publishes schema-v2 leads with locally cached photos.
# A collection JSON dump is a lead, not a product-page verification.
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.json"
SUGGESTIONS_PATH = ROOT / "data" / "suggestions.json"
IMAGES_DIR = ROOT / "data" / "images"
UA = "Mozilla/5.0 shopbot-scout"

SKIP_DEFAULT = [
    "slim",
    "skinny",
    "women",
    "woman",
    "women's",
    "womens",
    "female",
    "ladies",
    "gals",
    "girl",
    "girls",
    "boy",
    "boys",
    "kids",
    "youth",
    "toddler",
    "baby",
    "aerie",
    "legging",
    "yoga",
    "athletic",
    "copy of",
    "appointment",
    "residency",
    "styling",
    "pillow",
    "scrunchie",
    "cardholder",
    "packing cube",
]


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def kebab(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:64]


def product_search_text(product: dict) -> str:
    tags = product.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return " ".join(
        [
            str(product.get("title") or ""),
            str(product.get("handle") or ""),
            str(product.get("product_type") or ""),
            " ".join(str(tag) for tag in tags),
            str(product.get("vendor") or ""),
        ]
    ).lower()


def skip_product(product: dict, source: dict, rules: dict) -> bool:
    text = product_search_text(product)
    needles = rules.get("skipProductContains") or rules.get("skipTitleContains") or SKIP_DEFAULT
    for needle in needles:
        if needle.lower() in text:
            return True
    handle = str(product.get("handle") or "").lower()
    if handle in {str(value).lower() for value in source.get("excludeHandles") or []}:
        return True
    return False


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def sniff_ext(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if len(data) > 12 and data[4:8] == b"ftyp":
        return "avif"
    return None


def cache_image(item_id: str, image_url: str) -> str | None:
    if not image_url:
        return None
    req = urllib.request.Request(image_url, headers={"User-Agent": UA, "Accept": "image/*"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
            data = response.read()
    except Exception:
        return None
    if len(data) < 4000:
        return None
    ext = sniff_ext(data)
    if ext is None:
        return None
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{item_id}.{ext}"
    (IMAGES_DIR / filename).write_bytes(data)
    return f"/product-images/{filename}"


def guess_category(product: dict) -> str:
    blob = " ".join(
        [
            str(product.get("product_type") or ""),
            str(product.get("title") or ""),
            str(product.get("handle") or product.get("id") or ""),
            str(product.get("url") or ""),
            " ".join(product.get("tags") or []),
        ]
    ).lower()
    if any(word in blob for word in ("shoe", "boot", "sneaker", "loafer", "mule", "clog", "weejun", "fuelcell", "p550")):
        return "shoes"
    if any(word in blob for word in ("tote", "beanie", "belt", "cap", "hat", "bag", "scarf")):
        return "accessories"
    if any(word in blob for word in ("jacket", "coat", "chore", "overshirt", "shell", "windshirt", "parka", "shacket", "type 2")) or re.search(r"\bmac\b", blob):
        return "outerwear"
    shorts_blob = blob.replace("short sleeve", "").replace("short-sleeve", "")
    if re.search(r"\b(short|shorts|sweatshort|swimshort)\b", shorts_blob):
        return "shorts"
    if any(word in blob for word in ("jean", "denim")) and not any(word in blob for word in ("jacket", "shirt", "tote")):
        return "pants"
    if any(word in blob for word in ("pant", "trouser", "chino", "cargo", "straight leg", "stovepipe", "true guy", "strong guy", "easy guy", "weird guy")):
        return "pants"
    if any(word in blob for word in ("sweater", "knit", "hoodie", "crew", "cardigan", "pullover", "jumper", "v neck vest")):
        return "knit"
    if any(word in blob for word in ("shirt", "tee", "t-shirt", "polo", "rugby", "raglan", "oxford")):
        return "tops"
    return "other"


def guess_modes(product: dict) -> list[str]:
    blob = " ".join(
        [
            str(product.get("product_type") or ""),
            str(product.get("title") or ""),
            " ".join(product.get("tags") or []),
        ]
    ).lower()
    modes = []
    if any(word in blob for word in ("baggy", "cargo", "hoodie", "graphic", "varsity", "skate", "workwear", "sneaker", "tee")):
        modes.append("streetwear")
    if any(word in blob for word in ("plain", "minimal", "oxford", "polo", "trouser", "loafer", "linen", "selvage")):
        modes.append("minimal-clean")
    if any(word in blob for word in ("gore-tex", "goretex", "running", "fuelcell", "performance", "technical", "trail", "shell")):
        modes.append("athletic-tech")
    if any(word in blob for word in ("trouser", "oxford", "polo", "loafer", "dress", "pleated", "wool")):
        modes.append("corporate-presentable")
    if any(word in blob for word in ("denim", "jean", "chino", "jacket", "coat", "boot", "shirt", "knit", "sweater", "cardigan", "mule", "clog")):
        modes.append("classic-casual")
    return modes or ["classic-casual"]


def normalize_existing_scout_records(existing: dict) -> dict:
    changed = 0
    for item in existing.get("suggestions") or []:
        before = (item.get("category"), item.get("modes"))
        if item.get("category") == "accessory":
            item["category"] = "accessories"
        if (item.get("provenance") or {}).get("checkedBy") != "shopbot scout-shopify.py":
            if before != (item.get("category"), item.get("modes")):
                changed += 1
            continue
        category = guess_category(item)
        modes = guess_modes(item)
        if category != "other" or item.get("category") in (None, "", "other"):
            item["category"] = category
        item["modes"] = modes
        if before != (category, modes):
            changed += 1
    return {"changed": changed, "data": existing}


def pick_price(product: dict) -> tuple[float | None, float | None]:
    prices = []
    compares = []
    for variant in product.get("variants") or []:
        try:
            prices.append(float(variant.get("price")))
        except (TypeError, ValueError):
            pass
        raw = variant.get("compare_at_price")
        if raw not in (None, "", "0", "0.00"):
            try:
                compares.append(float(raw))
            except (TypeError, ValueError):
                pass
    if not prices:
        return None, None
    low = min(prices)
    list_price = max(compares) if compares and max(compares) > low else None
    return low, list_price


def to_record(product: dict, source: dict, now: str) -> dict | None:
    title = product.get("title") or ""
    handle = product.get("handle") or kebab(title)
    item_id = kebab(f"{source['id']}-{handle}")
    price, list_price = pick_price(product)
    if price is None or price <= 0:
        return None
    images = product.get("images") or []
    image_src = images[0].get("src") if images else None
    image_url = cache_image(item_id, image_src)
    if not image_url:
        return None
    vendor = (product.get("vendor") or "").strip()
    brand = vendor or source.get("name") or "Unknown"
    category = guess_category(product)
    base = (source.get("fetch") or {}).get("urls") or [""]
    storefront = base[0].split("/collections")[0].split("/products.json")[0].rstrip("/")
    pdp = f"{storefront}/products/{handle}"
    return {
        "id": item_id,
        "title": title,
        "brand": brand,
        "category": category,
        "imageUrl": image_url,
        "priceUSD": price,
        "listPriceUSD": list_price,
        "retailer": f"{brand} (brand direct)",
        "url": pdp,
        "modes": guess_modes(product),
        "verdict": f"{source.get('tasteFit') or 'Taste-matched lead'} from {brand}.",
        "matchReasons": [
            {
                "signal": "source",
                "detail": source.get("tasteFit") or "Listed on a taste-matched source in config/sources.json.",
            },
            {
                "signal": "silhouette-filter",
                "detail": "Product title, handle, type, and tags passed the menswear and silhouette filters. Confirm the actual cut on vote.",
            },
        ],
        "provenance": {
            "sourceType": "brand-direct",
            "retailer": storefront.replace("https://", "").replace("http://", ""),
            "foundVia": f"Shopify products.json for {source.get('id')} on {now[:10]}, not the individual product page",
            "evidence": f"Collection JSON listed this product at ${price:.2f}"
            + (f" (compare-at ${list_price:.2f})" if list_price else "")
            + ". That is a listing price from the catalog endpoint, so per-size stock and the final PDP price are unconfirmed.",
            "checkedBy": "shopbot scout-shopify.py",
        },
        "verification": {
            "status": "lead",
            "checkedAt": now,
            "priceObservedUSD": price,
            "stock": "unknown",
        },
        "addedAt": now,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", dest="source_ids")
    parser.add_argument("--exclude", action="append", dest="exclude_ids")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--normalize-existing", action="store_true")
    args = parser.parse_args()

    if args.normalize_existing:
        result = normalize_existing_scout_records(load_json(SUGGESTIONS_PATH, {"suggestions": []}))
        print(f"normalized {result['changed']} existing scout records")
        if not args.dry_run:
            SUGGESTIONS_PATH.write_text(json.dumps(result["data"], indent=2) + "\n", encoding="utf-8")
        return 0

    roster = load_json(SOURCES_PATH, {})
    rules = roster.get("scoutRules") or {}
    max_new = int(rules.get("maxNewPerSource") or 4)
    wanted = set(args.source_ids) if args.source_ids else None
    excluded = set(args.exclude_ids or [])

    existing = load_json(SUGGESTIONS_PATH, {"suggestions": []})
    known = {item.get("id") for item in existing.get("suggestions") or []}
    added = []

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for source in roster.get("sources") or []:
        if wanted and source.get("id") not in wanted:
            continue
        if source.get("id") in excluded:
            continue
        if source.get("status") != "works":
            continue
        fetch = source.get("fetch") or {}
        if fetch.get("method") != "shopify-products-json":
            continue
        seen_handles = set()
        seen_titles = set()
        source_added = 0
        for url in fetch.get("urls") or []:
            url_added = 0
            per_url = max(1, max_new // max(1, len(fetch.get("urls") or [])))
            try:
                payload = fetch_json(url + ("&limit=50" if "?" in url else "?limit=50"))
            except Exception as error:
                print(f"FAIL {source.get('id')} {url}: {error}", file=sys.stderr)
                continue
            for product in payload.get("products") or []:
                if url_added >= per_url or source_added >= max_new:
                    break
                handle = product.get("handle")
                title_key = re.sub(r"\s+", " ", (product.get("title") or "").lower())
                title_key = re.sub(r"\|.*$", "", title_key).strip()
                if handle in seen_handles or title_key in seen_titles:
                    continue
                seen_handles.add(handle)
                if skip_product(product, source, rules):
                    continue
                record = to_record(product, source, now)
                if record is None or record["id"] in known:
                    continue
                seen_titles.add(title_key)
                existing.setdefault("suggestions", []).append(record)
                known.add(record["id"])
                added.append(record["id"])
                source_added += 1
                url_added += 1
                print(f"ADD {record['id']} ${record['priceUSD']} {record['title']}")

    if args.dry_run:
        print(f"dry-run: would publish {len(added)} leads")
        return 0

    existing["generatedAt"] = now
    SUGGESTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUGGESTIONS_PATH.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print(f"published {len(added)} leads -> {SUGGESTIONS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
