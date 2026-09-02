"""Discover and verify menswear with Shopbot's self-hosted browser crawler.

Products are accepted only when an official men's category page contains the product
link. The category page is the audience boundary; a PDP by itself is not sufficient
evidence that a product belongs in the menswear catalogue.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.json"
SUGGESTIONS_PATH = ROOT / "data" / "suggestions.json"
VOTES_PATH = ROOT / "taste" / "votes.json"
REPORT_PATH = ROOT / "data" / "crawler-last-run.json"
SCOUT_PATH = Path(__file__).with_name("scout-shopify.py")
CHECKED_BY = "shopbot scout-browser.py"
LEGACY_CHECKED_BY = "shopbot scout-firecrawl.py"
PROFILE_PATH = ROOT / "data" / "crawler-profile"
TASTE_TERMS = {
    "baggy", "boxy", "carpenter", "chore", "denim", "double knee", "heritage",
    "knit", "loose", "minimal", "oxford", "pleated", "relaxed", "selvedge",
    "straight", "textured", "utility", "wide", "workwear",
}

SPEC = importlib.util.spec_from_file_location("shopbot_scout", SCOUT_PATH)
SCOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOUT)


class CrawlError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, blocked: bool = False):
        super().__init__(message)
        self.status = status
        self.blocked = blocked


class Crawl4AIClient:
    """Small adapter around a locally installed Crawl4AI browser.

    Imports stay lazy so deterministic parser/planner tests do not require a browser
    installation. A persistent profile lets a normal headed run retain retailer cookies.
    """

    def __init__(
        self,
        headed: bool = False,
        profile_path: Path = PROFILE_PATH,
        crawler_factory=None,
        config_factory=None,
        sleeper=asyncio.sleep,
        fresh: bool = False,
    ):
        self.headed = headed
        self.profile_path = profile_path
        self.crawler_factory = crawler_factory
        self.config_factory = config_factory
        self.sleeper = sleeper
        self.fresh = fresh
        self.crawler = None
        self.requests = Counter()
        self.network_attempts = Counter()
        self.cache_hits = 0

    async def __aenter__(self):
        if self.crawler_factory is not None:
            self.crawler = self.crawler_factory()
        else:
            try:
                from crawl4ai import AsyncWebCrawler, BrowserConfig
            except ImportError as error:
                raise CrawlError("Crawl4AI is not installed; run `npm run crawler:setup`") from error
            self.profile_path.mkdir(parents=True, exist_ok=True)
            browser_config = BrowserConfig(
                browser_type="chromium",
                headless=not self.headed,
                use_persistent_context=True,
                user_data_dir=str(self.profile_path),
                verbose=False,
            )
            self.crawler = AsyncWebCrawler(config=browser_config)
        await self.crawler.__aenter__()
        return self

    async def __aexit__(self, *args):
        if self.crawler is not None:
            await self.crawler.__aexit__(*args)

    async def fetch(self, url: str, kind: str) -> dict:
        self.requests[kind] += 1
        for attempt in range(2):
            if self.config_factory is not None:
                config = self.config_factory(kind, attempt)
            else:
                try:
                    from crawl4ai import CacheMode, CrawlerRunConfig
                except ImportError as error:
                    raise CrawlError("Crawl4AI is not installed; run `npm run crawler:setup`") from error
                bypass = self.fresh or kind == "product" or attempt > 0
                config = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS if bypass else CacheMode.ENABLED,
                    page_timeout=60000,
                    delay_before_return_html=2.0,
                    wait_for_images=kind == "product",
                    scan_full_page=kind == "category",
                    scroll_delay=0.4,
                )
            self.network_attempts[kind] += 1
            try:
                result = await self.crawler.arun(url=url, config=config)
            except Exception as error:
                if attempt == 0:
                    await self.sleeper(0.75)
                    continue
                raise CrawlError(f"browser transport failed after 2 attempts ({error})") from error
            status = int(getattr(result, "status_code", 0) or 0)
            html = str(getattr(result, "html", "") or "")
            if bool(getattr(result, "success", False)) and html:
                if is_challenge_html(html):
                    raise CrawlError("retailer challenge page returned instead of content", status=status or None, blocked=True)
                if len(html) < 500:
                    if attempt == 0:
                        await self.sleeper(0.25)
                        continue
                    raise CrawlError(f"browser returned unusably small {kind} content ({len(html)} bytes)", status=status or None)
                if str(getattr(result, "cache_status", "") or "").startswith("hit"):
                    self.cache_hits += 1
                links = getattr(result, "links", {}) or {}
                return {
                    "url": str(getattr(result, "redirected_url", "") or getattr(result, "url", "") or url),
                    "status": status,
                    "html": html,
                    "links": list(links.get("internal") or []),
                }
            message = str(getattr(result, "error_message", "") or f"HTTP {status or 'unknown'}")
            blocked = status in {401, 403, 429} or is_challenge_html(html) or is_block_message(message)
            if blocked:
                raise CrawlError(f"retailer blocked browser crawl ({message})", status=status or None, blocked=True)
            if attempt == 0:
                await self.sleeper(0.75)
                continue
            raise CrawlError(f"browser crawl failed after 2 attempts ({message})", status=status or None)
        raise CrawlError("browser crawl failed")


def canonical_url(url: str) -> str:
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    try:
        parsed_port = parsed.port
    except ValueError:
        return ""
    port = f":{parsed_port}" if parsed_port and not (parsed.scheme.lower() == "https" and parsed_port == 443) else ""
    path = parsed.path or "/"
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{port}{path}"


def allowed_url(url: str, source: dict, pattern_key: str) -> bool:
    fetch = source.get("fetch") or {}
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    allowed_hosts = {str(host).lower() for host in fetch.get("allowedHosts") or []}
    pattern = str(fetch.get(pattern_key) or "")
    try:
        path_matches = bool(pattern) and re.fullmatch(pattern, parsed.path) is not None
    except re.error:
        path_matches = False
    return parsed.scheme == "https" and parsed.hostname is not None and parsed.hostname.lower() in allowed_hosts and path_matches


def source_contract_errors(source: dict) -> list[str]:
    errors = []
    fetch = source.get("fetch") or {}
    if not source.get("id"):
        errors.append("missing source id")
    if not source.get("categories"):
        errors.append("missing supported categories")
    hosts = [str(host).lower() for host in fetch.get("allowedHosts") or []]
    if not hosts:
        errors.append("missing allowedHosts")
    for key in ("audienceCategoryPathPattern", "productPathPattern"):
        pattern = str(fetch.get(key) or "")
        if not pattern:
            errors.append(f"missing {key}")
            continue
        try:
            re.compile(pattern)
        except re.error as error:
            errors.append(f"invalid {key}: {error}")
    urls = fetch.get("urls") or []
    if not urls:
        errors.append("missing category URLs")
    for url in urls:
        if not allowed_url(str(url), source, "audienceCategoryPathPattern"):
            errors.append(f"category URL violates audience/host contract: {url}")
    try:
        if float(fetch.get("delaySeconds") or 0) < 0:
            errors.append("delaySeconds must be non-negative")
    except (TypeError, ValueError):
        errors.append("delaySeconds must be numeric")
    return errors


def clean_link_title(value: str, url: str) -> str:
    title = re.sub(r"[*_`]+", "", value or "")
    title = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", title)
    title = re.sub(r"\s+", " ", title).strip(" -")
    if title:
        return title
    slug = Path(urlparse(url).path).stem
    slug = re.sub(r"-p\d+$", "", slug)
    return slug.replace("-", " ").upper()


def is_challenge_html(html: str) -> bool:
    lowered = (html or "").lower()
    signals = ("bm-verify", "access denied", "akamai", "captcha", "verify you are human")
    return any(signal in lowered for signal in signals) and len(lowered) < 100_000


def is_block_message(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(signal in lowered for signal in ("anti-bot", "akamai block", "captcha", "access denied"))


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.in_title = False
        self.anchor = None
        self.anchor_parts = []
        self.links = []
        self.in_script = False
        self.script_type = ""
        self.script_id = ""
        self.script_parts = []
        self.json_scripts = []
        self.json_documents = []
        self.app_scripts = []
        self.meta = {}
        self.itemprops = {}
        self.data_prices = []

    def handle_starttag(self, tag, attrs):
        values = {str(key).lower(): value for key, value in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "a" and values.get("href"):
            self.anchor = str(values["href"])
            self.anchor_parts = []
        elif tag == "script":
            self.in_script = True
            self.script_type = str(values.get("type") or "").lower()
            self.script_id = str(values.get("id") or "")
            self.script_parts = []
        elif tag == "meta":
            key = str(values.get("property") or values.get("name") or "").lower()
            if key and values.get("content") is not None:
                self.meta[key] = str(values["content"])
        elif tag == "data" and values.get("value") is not None:
            self.data_prices.append(
                {"amount": str(values.get("value") or ""), "currency": str(values.get("data-currency") or "")}
            )
        itemprop = str(values.get("itemprop") or "").lower()
        if itemprop:
            value = values.get("content") or values.get("href") or values.get("src") or values.get("value")
            if value is not None:
                self.itemprops[itemprop] = str(value)

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.anchor is not None:
            self.anchor_parts.append(data)
        if self.in_script:
            self.script_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "a" and self.anchor is not None:
            self.links.append({"href": self.anchor, "text": " ".join(self.anchor_parts).strip()})
            self.anchor = None
            self.anchor_parts = []
        elif tag == "script":
            raw = "".join(self.script_parts)
            if self.script_type == "application/ld+json":
                self.json_scripts.append(raw)
            if "json" in self.script_type or self.script_id == "__NEXT_DATA__":
                self.json_documents.append({"type": self.script_type, "id": self.script_id, "text": raw})
            elif raw and len(raw) <= 5_000_000:
                self.app_scripts.append(raw)
            self.in_script = False
            self.script_type = ""
            self.script_id = ""
            self.script_parts = []

    @property
    def title(self):
        return re.sub(r"\s+", " ", "".join(self.title_parts)).strip()


def parse_page(html: str) -> PageParser:
    parser = PageParser()
    parser.feed(html or "")
    return parser


def product_refs_from_pages(pages: list[dict], source: dict, stats: dict | None = None) -> list[dict]:
    refs = []
    seen = set()
    counts = stats if stats is not None else {}
    counts["categoryPages"] = counts.get("categoryPages", 0) + len(pages)
    for page in pages:
        category_url = str(page.get("url") or "")
        parsed_page = parse_page(str(page.get("html") or ""))
        category_title = parsed_page.title
        if not allowed_url(category_url, source, "audienceCategoryPathPattern"):
            counts["invalidCategoryPages"] = counts.get("invalidCategoryPages", 0) + 1
            continue
        if re.search(r"\b(women|woman|girls?|kids?|boys?)\b", category_title, re.IGNORECASE):
            counts["audienceRejectedCategories"] = counts.get("audienceRejectedCategories", 0) + 1
            continue
        counts["acceptedCategoryPages"] = counts.get("acceptedCategoryPages", 0) + 1
        links = list(page.get("links") or []) + parsed_page.links
        for link in links:
            raw_url = str(link.get("href") or "") if isinstance(link, dict) else str(link or "")
            url = canonical_url(urljoin(category_url, raw_url).rstrip(".,;'"))
            link_title = str(link.get("text") or "") if isinstance(link, dict) else ""
            if not allowed_url(url, source, "productPathPattern"):
                counts["invalidProductLinks"] = counts.get("invalidProductLinks", 0) + 1
                continue
            if url in seen:
                counts["duplicateProductLinks"] = counts.get("duplicateProductLinks", 0) + 1
                continue
            seen.add(url)
            refs.append(
                {
                    "url": url,
                    "discoveryTitle": clean_link_title(link_title, url),
                    "audienceEvidence": {
                        "audience": "men",
                        "categoryUrl": category_url,
                        "categoryTitle": category_title,
                        "method": "product linked from official men's category page crawled by Shopbot's browser",
                    },
                }
            )
    counts["uniqueProductLinks"] = len(refs)
    return refs


def vote_value(entry) -> int | None:
    raw = entry.get("vote") if isinstance(entry, dict) else entry
    try:
        vote = int(raw)
    except (TypeError, ValueError):
        return None
    return max(-2, min(2, vote)) if vote else None


def owned_records(existing: dict, source: dict) -> list[dict]:
    source_id = str(source.get("id") or "")
    prefix = f"{source_id}-"
    return [
        item
        for item in existing.get("suggestions") or []
        if isinstance(item, dict)
        and (
            (item.get("provenance") or {}).get("sourceId") == source_id
            or (
                str(item.get("id") or "").startswith(prefix)
                and (item.get("provenance") or {}).get("checkedBy") in {CHECKED_BY, LEGACY_CHECKED_BY}
            )
        )
    ]


def normalize_owned_categories(existing: dict, source: dict) -> int:
    changed = 0
    allowed = set(source.get("categories") or [])
    for item in owned_records(existing, source):
        provenance = item.get("provenance") or {}
        if not provenance.get("sourceId"):
            item["provenance"] = dict(provenance, sourceId=source.get("id"))
            changed += 1
        product = {"title": item.get("title") or "", "product_type": "", "tags": []}
        category = SCOUT.guess_category(product)
        if category in allowed and category != item.get("category"):
            item["category"] = category
            changed += 1
    return changed


def learned_preferences(records: list[dict], votes: dict) -> dict:
    category_weights = Counter()
    signal_weights = Counter()
    for item in records:
        vote = vote_value(votes.get(item.get("id")))
        if vote is None:
            continue
        category_weights[str(item.get("category") or "other")] += vote * 2
        for mode in item.get("modes") or []:
            signal_weights[str(mode).lower()] += vote
        text = f"{item.get('title', '')} {item.get('verdict', '')}".lower()
        for term in TASTE_TERMS:
            if term in text:
                signal_weights[term] += vote
    return {"categories": dict(category_weights), "signals": dict(signal_weights)}


def candidate_detail(ref: dict, source: dict, rules: dict, learned: dict) -> tuple[dict | None, str | None]:
    title = str(ref.get("discoveryTitle") or "")
    synthetic = {
        "title": title,
        "handle": Path(urlparse(ref.get("url") or "").path).stem,
        "product_type": "",
        "tags": [],
        "vendor": source.get("name") or "",
    }
    if SCOUT.skip_product(synthetic, source, rules):
        return None, "excluded-product-signal"
    category = SCOUT.guess_category(synthetic)
    if category not in set(source.get("categories") or []):
        return None, "unsupported-or-unknown-category"
    text = SCOUT.product_search_text(synthetic)
    matched = sorted(term for term in TASTE_TERMS if term in text)
    score = len(matched) * 2
    score += int((learned.get("categories") or {}).get(category, 0))
    score += sum(int((learned.get("signals") or {}).get(term, 0)) for term in matched)
    detail = dict(ref)
    detail.update({"category": category, "tasteScore": score, "matchedSignals": matched})
    return detail, None


def plan_source(existing: dict, votes: dict, refs: list[dict], source: dict, rules: dict, cli_max: int | None = None) -> dict:
    policy = source.get("catalogPolicy") or {}
    initial_target = max(1, int(policy.get("initialTarget") or 24))
    max_unreviewed = max(1, int(policy.get("maxUnreviewed") or 24))
    new_per_refresh = max(1, int(policy.get("newPerRefresh") or 8))
    active_ceiling = max(initial_target, int(policy.get("activeCeiling") or 50))
    per_category = max(1, int(policy.get("bootstrapPerCategory") or 4))
    refresh_limit = max(0, int(policy.get("refreshLikedLimit") or 8))

    records = owned_records(existing, source)
    active = [
        item for item in records
        if vote_value(votes.get(item.get("id"))) != -2
        and (item.get("verification") or {}).get("stock") != "out-of-stock"
    ]
    unreviewed = [item for item in active if vote_value(votes.get(item.get("id"))) is None]
    backpressure = len(unreviewed) >= max_unreviewed
    if backpressure or len(active) >= active_ceiling:
        new_budget = 0
    elif len(active) < initial_target:
        new_budget = min(initial_target - len(active), active_ceiling - len(active))
    else:
        new_budget = min(new_per_refresh, max_unreviewed - len(unreviewed), active_ceiling - len(active))
    if cli_max is not None:
        new_budget = min(new_budget, max(0, cli_max))

    positive = [item for item in records if (vote_value(votes.get(item.get("id"))) or 0) > 0]
    positive.sort(key=lambda item: (-(vote_value(votes.get(item.get("id"))) or 0), str(item.get("id") or "")))
    refresh_records = positive[:refresh_limit]
    existing_urls = {str(item.get("url") or "") for item in records}
    learned = learned_preferences(records, votes)
    rejected = Counter()
    candidates = []
    for ref in refs:
        if ref.get("url") in existing_urls:
            continue
        detail, reason = candidate_detail(ref, source, rules, learned)
        if detail is None:
            rejected[reason or "unknown"] += 1
        else:
            candidates.append(detail)

    groups = {category: [] for category in source.get("categories") or []}
    for item in candidates:
        groups.setdefault(item["category"], []).append(item)
    eligible_by_category = {category: len(group) for category, group in groups.items() if group}
    for group in groups.values():
        group.sort(key=lambda item: (-item["tasteScore"], item["discoveryTitle"].lower(), item["url"]))
    counts = Counter(item.get("category") for item in active)
    selected = []
    selected_urls = set()
    selection_limit = min(len(candidates), new_budget * 3)
    while len(selected) < selection_limit:
        eligible = [
            category for category in source.get("categories") or []
            if groups.get(category) and counts[category] < per_category
        ]
        if not eligible:
            break
        eligible.sort(key=lambda category: (counts[category], -int((learned.get("categories") or {}).get(category, 0)), (source.get("categories") or []).index(category)))
        category = eligible[0]
        item = groups[category].pop(0)
        selected.append(item)
        selected_urls.add(item["url"])
        counts[category] += 1
    remainder = sorted(
        (item for item in candidates if item["url"] not in selected_urls),
        key=lambda item: (-item["tasteScore"], counts[item["category"]], item["discoveryTitle"].lower()),
    )
    selected.extend(remainder[: max(0, selection_limit - len(selected))])
    return {
        "activeBefore": len(active),
        "unreviewedBefore": len(unreviewed),
        "backpressure": backpressure,
        "newBudget": new_budget,
        "newRefs": selected,
        "eligibleByCategory": eligible_by_category,
        "selectedByCategory": dict(Counter(item["category"] for item in selected)),
        "refreshRecords": refresh_records,
        "rejectedBeforeScrape": dict(rejected),
        "learnedPreferences": learned,
        "policy": {
            "initialTarget": initial_target,
            "maxUnreviewed": max_unreviewed,
            "newPerRefresh": new_per_refresh,
            "activeCeiling": active_ceiling,
            "bootstrapPerCategory": per_category,
            "refreshLikedLimit": refresh_limit,
        },
    }


def json_nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from json_nodes(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from json_nodes(item)


def assigned_json_documents(scripts: list[str]):
    decoder = json.JSONDecoder()
    marker = re.compile(r"(?:window\.)?(?:__NEXT_DATA__|__INITIAL_STATE__|__APOLLO_STATE__)\s*=\s*")
    for script in scripts:
        for match in marker.finditer(script):
            try:
                value, _ = decoder.raw_decode(script[match.end():].lstrip())
            except (json.JSONDecodeError, TypeError):
                continue
            yield value


def type_names(value) -> set[str]:
    values = value if isinstance(value, list) else [value]
    return {str(item).lower() for item in values if item is not None}


def availability_flag(value) -> bool | None:
    text = str(value or "").lower()
    if "instock" in text or "in_stock" in text:
        return True
    if "outofstock" in text or "out_of_stock" in text or "soldout" in text:
        return False
    return None


def normalize_offer(offer: dict, images: list[str]) -> dict | None:
    if not isinstance(offer, dict):
        return None
    specifications = offer.get("priceSpecification") or []
    if isinstance(specifications, dict):
        specifications = [specifications]
    current_spec = next((item for item in specifications if isinstance(item, dict) and item.get("price")), {})
    price = offer.get("price") or offer.get("lowPrice") or current_spec.get("price")
    currency = offer.get("priceCurrency") or current_spec.get("priceCurrency") or "USD"
    if numeric_amount(price) is None:
        return None
    image_values = offer.get("image") or images
    if not isinstance(image_values, list):
        image_values = [image_values]
    available = availability_flag(offer.get("availability"))
    result = {
        "id": str(offer.get("sku") or offer.get("url") or "offer"),
        "sku": str(offer.get("sku") or ""),
        "price": {"amount": numeric_amount(price), "currency": str(currency).upper()},
        "availability": {"inStock": available, "text": str(offer.get("availability") or "")},
        "images": [
            {"url": str(image.get("url") or image.get("contentUrl") or "") if isinstance(image, dict) else str(image)}
            for image in image_values
            if image and (not isinstance(image, dict) or image.get("url") or image.get("contentUrl"))
        ],
    }
    # AggregateOffer.highPrice is a variant range, not a crossed-out list price.
    original = numeric_amount(offer.get("priceBeforeDiscount"))
    specification_prices = [
        numeric_amount(item.get("price")) for item in specifications if isinstance(item, dict)
    ]
    higher = [amount for amount in [original, *specification_prices] if amount is not None and amount > result["price"]["amount"]]
    if higher:
        result["originalPrice"] = {"amount": max(higher), "currency": str(currency).upper()}
    return result


def product_from_page(page: dict, expected_url: str) -> dict:
    html = str(page.get("html") or "")
    if is_challenge_html(html):
        raise CrawlError("retailer challenge page returned instead of product", status=page.get("status"), blocked=True)
    parsed = parse_page(html)
    product = None
    extraction_method = ""
    for document in parsed.json_documents:
        try:
            value = json.loads(document["text"])
        except (json.JSONDecodeError, TypeError):
            continue
        product = next(
            (node for node in json_nodes(value) if type_names(node.get("@type")) & {"product", "productgroup"}),
            None,
        )
        if product is not None:
            extraction_method = "json-ld" if document["type"] == "application/ld+json" else "embedded-json"
            break
    if product is None:
        for value in assigned_json_documents(parsed.app_scripts):
            product = next(
                (node for node in json_nodes(value) if type_names(node.get("@type")) & {"product", "productgroup"}),
                None,
            )
            if product is not None:
                extraction_method = "embedded-app-state"
                break
    if product is not None:
        brand_value = product.get("brand") or ""
        brand = brand_value.get("name") if isinstance(brand_value, dict) else brand_value
        image_values = product.get("image") or []
        if isinstance(image_values, dict):
            image_values = [image_values.get("url") or image_values.get("contentUrl")]
        elif not isinstance(image_values, list):
            image_values = [image_values]
        images = [
            str(image.get("url") or image.get("contentUrl") or "") if isinstance(image, dict) else str(image)
            for image in image_values
        ]
        variants = []
        raw_variants = product.get("hasVariant") or []
        if isinstance(raw_variants, dict):
            raw_variants = [raw_variants]
        for variant in raw_variants:
            if not isinstance(variant, dict):
                continue
            variant_images = variant.get("image") or images
            if not isinstance(variant_images, list):
                variant_images = [variant_images]
            variant_offers = variant.get("offers") or []
            if isinstance(variant_offers, dict):
                variant_offers = variant_offers.get("offers") or [variant_offers]
            for offer in variant_offers:
                normalized = normalize_offer(offer, variant_images)
                if normalized:
                    normalized["id"] = str(variant.get("sku") or normalized["id"])
                    normalized["sku"] = str(variant.get("sku") or normalized["sku"])
                    variants.append(normalized)
        raw_offers = product.get("offers") or []
        if isinstance(raw_offers, dict):
            raw_offers = raw_offers.get("offers") or [raw_offers]
        variants.extend(normalized for offer in raw_offers if (normalized := normalize_offer(offer, images)))
        if variants:
            return {
                "title": str(product.get("name") or ""),
                "brand": str(brand or ""),
                "category": str(product.get("category") or ""),
                "url": str(page.get("url") or product.get("url") or expected_url),
                "description": str(product.get("description") or ""),
                "variants": variants,
                "extractionMethod": f"{extraction_method}-{'product-group' if 'productgroup' in type_names(product.get('@type')) else 'product'}",
            }

    title = parsed.meta.get("og:title") or parsed.itemprops.get("name") or parsed.title
    image = parsed.meta.get("og:image") or parsed.meta.get("twitter:image") or parsed.itemprops.get("image")
    price = parsed.meta.get("product:price:amount") or parsed.itemprops.get("price")
    currency = parsed.meta.get("product:price:currency") or parsed.itemprops.get("pricecurrency") or ""
    if numeric_amount(price) is None and parsed.data_prices:
        price = parsed.data_prices[0]["amount"]
        currency = currency or parsed.data_prices[0]["currency"]
    currency = currency or "USD"
    if title and image and numeric_amount(price) is not None:
        available = availability_flag(parsed.meta.get("product:availability") or parsed.itemprops.get("availability"))
        return {
            "title": title,
            "brand": parsed.meta.get("product:brand") or parsed.itemprops.get("brand") or "",
            "category": parsed.itemprops.get("category") or "",
            "url": str(page.get("url") or expected_url),
            "description": parsed.meta.get("og:description") or "",
            "variants": [{
                "id": "page-meta",
                "sku": "",
                "price": {"amount": numeric_amount(price), "currency": currency.upper()},
                "availability": {"inStock": available, "text": parsed.meta.get("product:availability") or parsed.itemprops.get("availability") or ""},
                "images": [{"url": image}],
            }],
            "extractionMethod": "rendered-product-metadata",
        }
    raise CrawlError(f"no deterministic product data found at {expected_url}")


def numeric_amount(value) -> float | None:
    if isinstance(value, dict):
        value = value.get("amount")
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def product_to_record(
    product: dict,
    source: dict,
    ref: dict,
    now: str,
    rules: dict | None = None,
    cache_images: bool = True,
    rejection_counts: Counter | None = None,
    rejection_details: list[dict] | None = None,
) -> dict | None:
    def reject(reason: str):
        if rejection_counts is not None:
            rejection_counts[reason] += 1
        if rejection_details is not None and len(rejection_details) < 20:
            rejection_details.append(
                {
                    "url": str(product.get("url") or ref.get("url") or ""),
                    "discoveryTitle": ref.get("discoveryTitle"),
                    "productTitle": product.get("title"),
                    "reason": reason,
                }
            )
        return None

    url = canonical_url(str(product.get("url") or ref.get("url") or ""))
    if url != canonical_url(ref.get("url") or "") or not allowed_url(url, source, "productPathPattern"):
        return reject("invalid-or-redirected-product-url")
    title = str(product.get("title") or "").strip()
    brand = str(product.get("brand") or source.get("name") or "").strip()
    description = str(product.get("description") or "").strip()
    synthetic = {
        "title": title,
        "handle": urlparse(url).path.rsplit("/", 1)[-1],
        "product_type": str(product.get("category") or ""),
        "tags": [description],
        "vendor": brand,
    }
    if not title:
        return reject("missing-title")
    if SCOUT.skip_product(synthetic, source, rules or {}):
        return reject("excluded-product-signal")

    variants = [variant for variant in product.get("variants") or [] if isinstance(variant, dict)]
    usd_variants = []
    for variant in variants:
        price = variant.get("price") or {}
        currency = str(price.get("currency") or "USD").upper() if isinstance(price, dict) else "USD"
        amount = numeric_amount(price)
        if amount is not None and currency == "USD":
            usd_variants.append((amount, variant))
    if not usd_variants:
        return reject("missing-usd-variants")
    available = [entry for entry in usd_variants if bool((entry[1].get("availability") or {}).get("inStock"))]
    price, selected_variant = min(available or usd_variants, key=lambda entry: entry[0])
    originals = []
    for key in ("originalPrice", "compareAtPrice"):
        amount = numeric_amount(selected_variant.get(key))
        if amount is not None and amount > price:
            originals.append(amount)
    list_price = max(originals) if originals else None
    image_source = next(
        (
            str(image.get("url"))
            for variant in [selected_variant, *(entry[1] for entry in usd_variants if entry[1] is not selected_variant)]
            for image in variant.get("images") or []
            if isinstance(image, dict) and image.get("url")
        ),
        "",
    )
    image_source = urljoin(url, image_source) if image_source else ""
    if not image_source.startswith("https://"):
        return reject("invalid-image-url")
    path_stem = Path(urlparse(url).path).stem
    item_id = SCOUT.kebab(f"{source.get('id')}-{path_stem}")
    category = SCOUT.guess_category(synthetic)
    if category not in {"knit", "outerwear", "pants", "shoes", "shorts", "tops"}:
        return reject("unsupported-or-unknown-category")
    image_url = SCOUT.cache_image(item_id, image_source) if cache_images else image_source
    if not image_url:
        return reject("image-unavailable")
    availability_flags = [
        (variant.get("availability") or {}).get("inStock")
        for variant in variants
        if isinstance((variant.get("availability") or {}).get("inStock"), bool)
    ]
    stock = "in-stock" if any(availability_flags) else "out-of-stock" if availability_flags and len(availability_flags) == len(variants) else "unknown"
    return {
        "id": item_id,
        "title": title,
        "brand": brand,
        "category": category,
        "imageUrl": image_url,
        "priceUSD": price,
        "listPriceUSD": list_price,
        "retailer": f"{source.get('name')} (brand direct)",
        "url": url,
        "modes": SCOUT.guess_modes(synthetic),
        "verdict": f"{source.get('tasteFit') or 'Taste-matched product'} from {brand}.",
        "matchReasons": [
            {"signal": "source", "detail": source.get("tasteFit") or "Configured taste-matched source."},
            {"signal": "audience", "detail": "Linked from an official men's category page; product metadata passed the exclusion rules."},
            *(
                [{"signal": "taste", "detail": f"Discovery title matched: {', '.join(ref.get('matchedSignals') or [])}."}]
                if ref.get("matchedSignals")
                else []
            ),
        ],
        "provenance": {
            "sourceId": source.get("id"),
            "sourceType": "brand-direct",
            "retailer": urlparse(url).hostname,
            "foundVia": "Shopbot self-hosted browser crawl of an official men's category followed by deterministic product-page extraction",
            "evidence": f"Product page returned {len(variants)} variants through {product.get('extractionMethod') or 'deterministic metadata'}; lowest current USD price ${price:.2f}; stock derived from variant availability.",
            "extractionMethod": product.get("extractionMethod") or "deterministic-metadata",
            "audienceEvidence": ref.get("audienceEvidence"),
            "checkedBy": CHECKED_BY,
        },
        "verification": {
            "status": "verified",
            "checkedAt": now,
            "priceObservedUSD": price,
            "stock": stock,
        },
        "addedAt": now,
    }


def merge_records(existing: dict, records: list[dict]) -> tuple[dict, dict]:
    suggestions = list(existing.get("suggestions") or [])
    positions = {item.get("id"): index for index, item in enumerate(suggestions) if isinstance(item, dict)}
    counts = {"added": 0, "updated": 0}
    for record in records:
        position = positions.get(record["id"])
        if position is None:
            positions[record["id"]] = len(suggestions)
            suggestions.append(record)
            counts["added"] += 1
        elif (suggestions[position].get("provenance") or {}).get("checkedBy") in {CHECKED_BY, LEGACY_CHECKED_BY}:
            record["addedAt"] = suggestions[position].get("addedAt") or record["addedAt"]
            suggestions[position] = record
            counts["updated"] += 1
    result = dict(existing)
    result["schemaVersion"] = max(2, int(existing.get("schemaVersion") or 0))
    result["suggestions"] = suggestions
    return result, counts


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Discover and verify products with Shopbot's self-hosted browser.")
    parser.add_argument("--source", action="append", dest="source_ids")
    parser.add_argument("--max-products", type=int, default=None, help="Optional per-source cap for new products in this run.")
    parser.add_argument("--headed", action="store_true", help="Show the persistent browser so a normal retailer challenge can be completed.")
    parser.add_argument("--fresh", action="store_true", help="Bypass category cache; product verification is always fresh.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


async def run(args, client_factory=None) -> int:

    roster = SCOUT.load_json(SOURCES_PATH, {})
    rules = roster.get("scoutRules") or {}
    wanted = set(args.source_ids) if args.source_ids else None
    sources = [
        source
        for source in roster.get("sources") or []
        if (source.get("fetch") or {}).get("method") == "self-hosted-browser"
        and (wanted is None or source.get("id") in wanted)
    ]
    if not sources:
        print("no matching self-hosted-browser source configured", file=sys.stderr)
        return 1
    invalid_sources = [(source.get("id"), source_contract_errors(source)) for source in sources]
    invalid_sources = [(source_id, errors) for source_id, errors in invalid_sources if errors]
    if invalid_sources:
        for source_id, errors in invalid_sources:
            print(f"invalid source {source_id}: {'; '.join(errors)}", file=sys.stderr)
        return 1

    client = client_factory() if client_factory else Crawl4AIClient(headed=args.headed, fresh=args.fresh)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    existing = SCOUT.load_json(SUGGESTIONS_PATH, {"schemaVersion": 2, "suggestions": []})
    votes = SCOUT.load_json(VOTES_PATH, {})
    records = []
    report = {
        "schemaVersion": 1,
        "generatedAt": now,
        "dryRun": args.dry_run,
        "engine": "crawl4ai-local",
        "headed": args.headed,
        "fresh": args.fresh,
        "sources": [],
    }
    total_failures = 0
    planned_operations = 0
    normalized_categories = 0
    async with client:
        for source in sources:
            source_requests_before = Counter(client.requests)
            source_attempts_before = Counter(client.network_attempts)
            source_cache_before = client.cache_hits
            discovery_stats = {}
            failures = []
            pages = []
            blocked = False
            source_normalized = normalize_owned_categories(existing, source)
            normalized_categories += source_normalized
            preliminary = plan_source(existing, votes, [], source, rules, args.max_products)
            if preliminary["newBudget"] > 0:
                for category_url in (source.get("fetch") or {}).get("urls") or []:
                    try:
                        pages.append(await client.fetch(str(category_url), "category"))
                    except CrawlError as error:
                        failures.append(f"category {category_url}: {error}")
                        blocked = blocked or error.blocked
                        if error.blocked:
                            break
                    except Exception as error:
                        failures.append(f"category {category_url}: unexpected crawler failure ({error})")
            refs = product_refs_from_pages(pages, source, discovery_stats)
            plan = plan_source(existing, votes, refs, source, rules, args.max_products)
            refresh_refs = []
            for item in plan["refreshRecords"]:
                audience = (item.get("provenance") or {}).get("audienceEvidence")
                if not audience:
                    failures.append(f"refresh {item.get('id')}: missing audience evidence")
                    continue
                refresh_refs.append(
                    {
                        "url": item.get("url"),
                        "discoveryTitle": item.get("title"),
                        "audienceEvidence": audience,
                        "matchedSignals": [],
                        "operation": "refresh",
                    }
                )
            new_refs = [dict(ref, operation="new") for ref in plan["newRefs"]]
            tasks = refresh_refs + new_refs
            planned_operations += plan["newBudget"] + len(refresh_refs)
            verified_new = 0
            refreshed = 0
            rejected_product = Counter()
            rejection_details = []
            attempted_new = 0
            category_counts = Counter()
            extraction_counts = Counter()
            for ref in tasks:
                if ref["operation"] == "new":
                    if verified_new >= plan["newBudget"]:
                        break
                    attempted_new += 1
                try:
                    page = await client.fetch(ref["url"], "product")
                    product = product_from_page(page, ref["url"])
                    record = product_to_record(
                        product,
                        source,
                        ref,
                        now,
                        rules,
                        cache_images=not args.dry_run,
                        rejection_counts=rejected_product,
                        rejection_details=rejection_details,
                    )
                    if record is not None:
                        records.append(record)
                        category_counts[record["category"]] += 1
                        extraction_counts[(record.get("provenance") or {}).get("extractionMethod") or "unknown"] += 1
                        if ref["operation"] == "refresh":
                            refreshed += 1
                        else:
                            verified_new += 1
                        print(f"VERIFY {ref['operation']} {record['id']} ${record['priceUSD']:.2f} {record['title']}")
                except CrawlError as error:
                    failures.append(f"product {ref['url']}: {error}")
                    blocked = blocked or error.blocked
                    if error.blocked:
                        break
                except Exception as error:
                    failures.append(f"product {ref['url']}: unexpected extraction failure ({error})")
                if tasks:
                    await asyncio.sleep(max(0.0, float((source.get("fetch") or {}).get("delaySeconds") or 1.0)))
            total_failures += len(failures)
            for failure in failures:
                print(f"FAIL {source.get('id')} {failure}", file=sys.stderr)
            report["sources"].append(
                {
                    "sourceId": source.get("id"),
                    "existingBefore": len(owned_records(existing, source)),
                    "normalizedCategories": source_normalized,
                    "activeBefore": plan["activeBefore"],
                    "unreviewedBefore": plan["unreviewedBefore"],
                    "backpressure": plan["backpressure"],
                    "blocked": blocked,
                    "policy": plan["policy"],
                    "newBudget": plan["newBudget"],
                    "discovery": discovery_stats,
                    "rejectedBeforeScrape": plan["rejectedBeforeScrape"],
                    "eligibleByCategory": plan["eligibleByCategory"],
                    "selectedByCategory": plan["selectedByCategory"],
                    "candidateQueueNew": len(new_refs),
                    "attemptedNew": attempted_new,
                    "scheduledRefresh": len(refresh_refs),
                    "verifiedNew": verified_new,
                    "refreshed": refreshed,
                    "rejectedAfterScrape": dict(rejected_product),
                    "rejectionDetails": rejection_details,
                    "verifiedCategories": dict(category_counts),
                    "extractionMethods": dict(extraction_counts),
                    "failures": failures,
                    "cacheHits": client.cache_hits - source_cache_before,
                    "requests": dict(Counter(client.requests) - source_requests_before),
                    "networkAttempts": dict(Counter(client.network_attempts) - source_attempts_before),
                }
            )

    counts = {"added": 0, "updated": 0}
    output = existing
    if records:
        output, counts = merge_records(existing, records)
        output["generatedAt"] = now
    if not args.dry_run and (records or normalized_categories):
        atomic_write_json(SUGGESTIONS_PATH, output)
    report["cacheHits"] = client.cache_hits
    report["requests"] = dict(client.requests)
    report["networkAttempts"] = dict(client.network_attempts)
    report["normalizedCategories"] = normalized_categories
    report["published"] = counts
    if not args.dry_run:
        atomic_write_json(REPORT_PATH, report)
    prefix = "dry-run" if args.dry_run else "run"
    print(
        f"{prefix}: discovered {sum((item.get('discovery') or {}).get('uniqueProductLinks', 0) for item in report['sources'])} unique PDPs; "
        f"verified {counts['added']} new and refreshed {counts['updated']}; "
        f"requests {sum(client.requests.values())}; cache hits {client.cache_hits}; failures {total_failures}"
    )
    if planned_operations and not records:
        print("Browser scout published nothing; existing suggestions were preserved", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
