from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.json"
CANDIDATES_PATH = ROOT / "data" / "brand-candidates.json"
BRAND_DECISIONS_PATH = ROOT / "taste" / "brand-decisions.json"
SCOUT_PATH = Path(__file__).with_name("scout-shopify.py")

SPEC = importlib.util.spec_from_file_location("shopbot_scout", SCOUT_PATH)
SCOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOUT)

TASTE_TERMS = {
    "baggy", "boxy", "carpenter", "cargo", "chore", "denim", "double knee",
    "heritage", "knit", "loose", "minimal", "oxford", "pleated", "relaxed",
    "selvedge", "skate", "straight", "sweater", "utility", "wide", "workwear",
}
AUDIENCE_SKIP = {
    "baby", "boys", "girls", "infant", "junior", "kids", "toddler", "youth",
}


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def brand_key(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", str(value or "").lower())
    while words and words[-1] in {"clothing", "co", "company", "denim", "inc", "jeans", "ltd"}:
        words.pop()
    return "".join(words)


def candidate_id(brand: str) -> str:
    return SCOUT.kebab(f"brand-{brand}")


def product_score(product: dict, rules: dict, signal_weights: dict[str, int] | None = None) -> tuple[int, list[str]]:
    text = SCOUT.product_search_text(product)
    terms = TASTE_TERMS | {str(value).lower() for value in rules.get("preferTitleContains") or []}
    matched = sorted(term for term in terms if term in text)
    learned = signal_weights or {}
    return len(matched) + sum(learned.get(term, 0) for term in matched), matched


def learned_signal_weights(previous: dict, decisions: dict) -> dict[str, int]:
    by_id = {item.get("id"): item for item in previous.get("candidates") or []}
    weights: dict[str, int] = {}
    decision_weight = {"follow": 3, "occasional": 1, "reject": -3, "too-expensive": 0}
    for candidate_id_value, entry in decisions.items():
        candidate = by_id.get(candidate_id_value)
        if not candidate or not isinstance(entry, dict):
            continue
        weight = decision_weight.get(entry.get("decision"), 0)
        for signal in candidate.get("matchedSignals") or []:
            weights[str(signal).lower()] = weights.get(str(signal).lower(), 0) + weight
    return weights


def storefront(url: str) -> str:
    return url.split("/collections")[0].split("/products.json")[0].rstrip("/")


def fetch_catalog(url: str) -> dict:
    try:
        return SCOUT.fetch_json(url)
    except Exception as first_error:
        try:
            result = subprocess.run(
                ["curl", "-fsSL", "--max-time", "30", "-A", "Mozilla/5.0 shopbot-brand-discovery", url],
                check=True,
                capture_output=True,
                text=True,
                timeout=35,
            )
            return json.loads(result.stdout)
        except Exception as fallback_error:
            raise RuntimeError(f"python fetch failed ({first_error}); curl fallback failed ({fallback_error})") from fallback_error


def product_record(product: dict, source: dict, source_url: str, score: int, matched: list[str]) -> dict | None:
    price, list_price = SCOUT.pick_price(product)
    images = product.get("images") or []
    image_src = images[0].get("src") if images else None
    handle = str(product.get("handle") or "").strip()
    title = str(product.get("title") or "").strip()
    if not handle or not title or not image_src or price is None or price <= 0:
        return None
    return {
        "id": SCOUT.kebab(f"{source.get('id')}-{handle}"),
        "title": title,
        "priceUSD": price,
        "listPriceUSD": list_price,
        "imageSourceUrl": image_src,
        "imageUrl": None,
        "url": f"{storefront(source_url)}/products/{handle}",
        "retailer": source.get("name") or source.get("id"),
        "category": SCOUT.guess_category(product),
        "modes": SCOUT.guess_modes(product),
        "tasteScore": score,
        "matchedSignals": matched[:5],
    }


def discover_candidates(payloads: list[tuple[dict, str, dict]], roster: dict, now: str, signal_weights: dict[str, int] | None = None) -> list[dict]:
    rules = roster.get("scoutRules") or {}
    known = {brand_key(source.get("name")) for source in roster.get("sources") or []}
    grouped: dict[str, dict] = {}
    for source, source_url, payload in payloads:
        for product in payload.get("products") or []:
            text = SCOUT.product_search_text(product)
            if SCOUT.skip_product(product, source, rules) or any(term in text for term in AUDIENCE_SKIP):
                continue
            brand = str(product.get("vendor") or "").strip()
            key = brand_key(brand)
            if not key or key in known or key == brand_key(source.get("name")):
                continue
            score, matched = product_score(product, rules, signal_weights)
            if score < 1:
                continue
            record = product_record(product, source, source_url, score, matched)
            if record is None or record["category"] not in {"knit", "outerwear", "pants", "shoes", "shorts", "tops"}:
                continue
            group = grouped.setdefault(key, {"brand": brand, "products": {}, "retailers": set()})
            if len(brand) < len(group["brand"]):
                group["brand"] = brand
            existing = group["products"].get(record["id"])
            if existing is None or record["tasteScore"] > existing["tasteScore"]:
                group["products"][record["id"]] = record
            group["retailers"].add(record["retailer"])

    candidates = []
    for group in grouped.values():
        products = sorted(
            group["products"].values(),
            key=lambda item: (-item["tasteScore"], item["priceUSD"], item["title"].lower()),
        )
        if not products:
            continue
        signals = []
        for item in products:
            for signal in item["matchedSignals"]:
                if signal not in signals:
                    signals.append(signal)
        retailers = sorted(group["retailers"])
        learned_signals = [signal for signal in signals if (signal_weights or {}).get(signal, 0)]
        candidates.append({
            "id": candidate_id(group["brand"]),
            "brand": group["brand"],
            "confidence": "exploratory",
            "score": sum(item["tasteScore"] for item in products[:3]),
            "reason": f"Exploratory match from {', '.join(retailers)}: {', '.join(signals[:4])} product signals overlap your current taste prior.",
            "matchedSignals": signals[:8],
            "learnedSignals": learned_signals[:8],
            "retailers": retailers,
            "representativeProducts": products[:3],
            "evidence": {
                "sampledMatchingProducts": len(products),
                "discoveryMethod": "trusted multi-brand retailer catalog",
            },
            "firstFoundAt": now,
            "lastSeenAt": now,
        })
    return sorted(candidates, key=lambda item: (-item["score"], item["brand"].lower()))


def merge_candidates(previous: dict, discovered: list[dict], now: str, limit: int) -> dict:
    old = {item.get("id"): item for item in previous.get("candidates") or [] if item.get("id")}
    merged = []
    for item in discovered:
        prior = old.get(item["id"]) or {}
        item["firstFoundAt"] = prior.get("firstFoundAt") or item["firstFoundAt"]
        old_products = {product.get("id"): product for product in prior.get("representativeProducts") or []}
        for product in item.get("representativeProducts") or []:
            old_product = old_products.get(product.get("id")) or {}
            if old_product.get("imageUrl"):
                product["imageUrl"] = old_product["imageUrl"]
                product.pop("imageSourceUrl", None)
        merged.append(item)
    seen = {item["id"] for item in merged}
    merged.extend(item for key, item in old.items() if key not in seen)
    merged.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("brand") or "").lower()))
    return {"schemaVersion": 1, "generatedAt": now, "candidates": merged[:limit]}


def cache_candidate_images(candidates: list[dict]) -> None:
    for candidate in candidates:
        for product in candidate.get("representativeProducts") or []:
            source_url = product.pop("imageSourceUrl", None)
            if source_url:
                product["imageUrl"] = SCOUT.cache_image(product["id"], source_url)


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover new brands through trusted multi-brand Shopify retailers.")
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-candidates", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    roster = load_json(SOURCES_PATH, {})
    payloads = []
    failures = []
    for source in roster.get("sources") or []:
        fetch = source.get("fetch") or {}
        if source.get("kind") != "retailer-direct" or source.get("status") != "works":
            continue
        if fetch.get("method") not in {"shopify-products-json", "stocking-retailer-json"}:
            continue
        for url in fetch.get("urls") or []:
            for page in range(1, max(1, args.pages) + 1):
                page_size = max(1, min(250, args.page_size))
                request_url = url + ("&" if "?" in url else "?") + f"limit={page_size}&page={page}"
                try:
                    payloads.append((source, url, fetch_catalog(request_url)))
                except Exception as error:
                    failures.append(f"{source.get('id')} page {page}: {error}")
                    break
    if not payloads:
        for failure in failures:
            print(f"FAIL {failure}")
        print("brand discovery failed: no retailer catalog was readable")
        return 1
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    previous = load_json(CANDIDATES_PATH, {})
    signal_weights = learned_signal_weights(previous, load_json(BRAND_DECISIONS_PATH, {}))
    discovered = discover_candidates(payloads, roster, now, signal_weights)
    result = merge_candidates(previous, discovered, now, max(1, args.max_candidates))
    if not args.dry_run:
        cache_candidate_images(result["candidates"])
        atomic_write_json(CANDIDATES_PATH, result)
    print(f"discovered {len(discovered)} brands from {len(payloads)} retailer pages; retained {len(result['candidates'])}")
    if failures:
        print(f"{len(failures)} retailer fetches failed; readable sources still published")
    for item in result["candidates"][:10]:
        print(f"BRAND {item['brand']} score={item.get('score', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
