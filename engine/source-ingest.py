#!/usr/bin/env python3
"""Discover normalized catalog candidates from declarative public/feed sources.

This layer discovers products; it never upgrades feed or sitemap data to a
purchase-ready verification. Browser/PDP verification remains a separate step.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.json"
OUTPUT_PATH = ROOT / "data" / "ingestion-candidates.json"
USER_AGENT = "shopbot-catalog/1.0 (+local personal catalog)"
SUPPORTED_METHODS = {"sitemap-xml", "json-feed", "csv-feed", "xml-feed"}
MAX_RESPONSE_BYTES = 50 * 1024 * 1024


class IngestError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def canonical_url(value: object) -> str:
    try:
        parsed = urlparse(str(value or "").strip())
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return ""
    authority = parsed.hostname.lower()
    if port and port != 443:
        authority += f":{port}"
    path = parsed.path or "/"
    return f"https://{authority}{path}"


def allowed_url(url: str, fetch: dict, *, sitemap: bool = False) -> bool:
    canonical = canonical_url(url)
    if not canonical:
        return False
    parsed = urlparse(canonical)
    hosts = {str(host).lower() for host in fetch.get("allowedHosts") or []}
    if hosts and parsed.hostname not in hosts:
        return False
    pattern_key = "sitemapPathPattern" if sitemap else "productPathPattern"
    pattern = fetch.get(pattern_key)
    try:
        return not pattern or re.search(str(pattern), parsed.path) is not None
    except re.error:
        return False


def allowed_fetch_url(url: str, fetch: dict) -> bool:
    canonical = canonical_url(url)
    if not canonical:
        return False
    hosts = {str(host).lower() for host in fetch.get("allowedHosts") or []}
    return bool(hosts) and urlparse(canonical).hostname in hosts


def source_contract_errors(source: dict) -> list[str]:
    fetch = source.get("fetch") or {}
    errors = []
    if not source.get("id"):
        errors.append("missing id")
    if fetch.get("method") not in SUPPORTED_METHODS:
        errors.append(f"unsupported method {fetch.get('method')!r}")
    if not fetch.get("urls") and not fetch.get("urlTemplate"):
        errors.append("missing fetch.urls or fetch.urlTemplate")
    if not fetch.get("allowedHosts"):
        errors.append("missing fetch.allowedHosts")
    for key in ("productPathPattern", "sitemapPathPattern"):
        if fetch.get(key):
            try:
                re.compile(str(fetch[key]))
            except re.error as error:
                errors.append(f"invalid {key}: {error}")
    if fetch.get("method") in {"json-feed", "csv-feed", "xml-feed"} and not fetch.get("mapping"):
        errors.append("feed adapter requires fetch.mapping")
    if fetch.get("method") == "xml-feed" and not fetch.get("itemPath"):
        errors.append("xml-feed requires fetch.itemPath")
    try:
        if int(fetch.get("maxCandidates") or 10000) < 1:
            errors.append("maxCandidates must be positive")
    except (TypeError, ValueError):
        errors.append("maxCandidates must be an integer")
    return errors


def request_headers(fetch: dict) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/xml, text/xml, text/csv, */*;q=0.5"}
    for name, env_name in (fetch.get("headersEnv") or {}).items():
        value = os.environ.get(str(env_name))
        if not value:
            raise IngestError(f"required environment variable {env_name} is missing")
        headers[str(name)] = value
    return headers


def fetch_bytes(url: str, fetch: dict, *, sleeper=time.sleep) -> bytes:
    if not allowed_fetch_url(url, fetch):
        raise IngestError(f"fetch URL violates HTTPS/host contract: {url}")
    request = urllib.request.Request(url, headers=request_headers(fetch))
    class AllowedRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not allowed_fetch_url(newurl, fetch):
                raise IngestError(f"redirect violates HTTPS/host contract: {newurl}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(AllowedRedirects())
    attempts = max(1, min(3, int(fetch.get("attempts") or 2)))
    last_error = None
    for attempt in range(attempts):
        try:
            with opener.open(request, timeout=float(fetch.get("timeoutSeconds") or 30)) as response:
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > MAX_RESPONSE_BYTES:
                    raise IngestError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise IngestError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
                if urlparse(url).path.endswith(".gz") or response.headers.get("Content-Encoding") == "gzip":
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
                        payload = compressed.read(MAX_RESPONSE_BYTES + 1)
                    if len(payload) > MAX_RESPONSE_BYTES:
                        raise IngestError(f"expanded response exceeds {MAX_RESPONSE_BYTES} bytes")
                return payload
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {429, 500, 502, 503, 504} or attempt + 1 >= attempts:
                break
            retry_after = error.headers.get("Retry-After")
            delay = min(10.0, float(retry_after)) if retry_after and retry_after.isdigit() else 1.0 + attempt
            sleeper(delay)
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            last_error = error
            if attempt + 1 < attempts:
                sleeper(1.0 + attempt)
    raise IngestError(f"fetch failed for {url}: {last_error}")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(element: ET.Element, path: str) -> str | None:
    current = [element]
    for part in str(path).strip("./").split("/"):
        if not part:
            continue
        next_nodes = []
        for node in current:
            next_nodes.extend(child for child in list(node) if local_name(child.tag) == part)
        current = next_nodes
        if not current:
            return None
    text = " ".join("".join(node.itertext()).strip() for node in current if "".join(node.itertext()).strip())
    return text or None


def value_at(value, path: str):
    current = value
    for part in str(path or "").split("."):
        if part == "":
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def mapped_value(item, mapping_value, *, xml: bool = False):
    paths = mapping_value if isinstance(mapping_value, list) else [mapping_value]
    for path in paths:
        value = child_text(item, str(path)) if xml else value_at(item, str(path))
        if value not in (None, "", []):
            return value
    return None


def number(value) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:[,.]\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    try:
        return round(float(match.group(0)), 2)
    except ValueError:
        return None


def candidate_id(source_id: str, url: str, sku: object = None) -> str:
    identity = str(sku or url)
    slug = re.sub(r"[^a-z0-9]+", "-", identity.lower()).strip("-")[-48:]
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{source_id}-{slug or 'product'}-{digest}"


def normalize_candidate(raw: dict, source: dict, observed_at: str, adapter: str) -> dict | None:
    fetch = source.get("fetch") or {}
    url = canonical_url(raw.get("url"))
    if not url or not allowed_url(url, fetch):
        return None
    title = str(raw.get("title") or "").strip() or re.sub(r"[-_]+", " ", Path(urlparse(url).path).parts[-3] if "/p/" in urlparse(url).path else Path(urlparse(url).path).stem).strip().title()
    image_value = raw.get("imageUrl")
    if isinstance(image_value, list):
        image_value = next((value for value in image_value if value), None)
    if isinstance(image_value, dict):
        image_value = image_value.get("url") or image_value.get("src")
    image = canonical_url(image_value) if image_value else None
    price = number(raw.get("price"))
    original = number(raw.get("originalPrice"))
    currency = str(raw.get("currency") or fetch.get("currency") or "").upper() or None
    inferred_sku = raw.get("sku")
    if not inferred_sku:
        sku_match = re.search(r"/p/([^/]+)$", urlparse(url).path)
        inferred_sku = sku_match.group(1) if sku_match else None
    record = {
        "id": candidate_id(str(source.get("id")), url, inferred_sku),
        "sourceId": source.get("id"),
        "adapter": adapter,
        "url": url,
        "title": title,
        "brand": raw.get("brand") or source.get("name"),
        "sku": inferred_sku,
        "category": raw.get("category"),
        "imageUrl": image,
        "price": {"amount": price, "currency": currency} if price is not None else None,
        "originalPrice": {"amount": original, "currency": currency} if original is not None else None,
        "availability": raw.get("availability"),
        "lastModified": raw.get("lastModified"),
        "observedAt": observed_at,
        "evidence": {
            "status": "lead",
            "method": adapter,
            "note": "Discovery/feed metadata only; verify the current retailer PDP before purchase.",
        },
    }
    return {key: value for key, value in record.items() if value is not None}


def parse_sitemap(payload: bytes) -> tuple[str, list[dict]]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise IngestError(f"invalid sitemap XML: {error}") from error
    kind = local_name(root.tag)
    if kind == "sitemapindex":
        return kind, [{"url": child_text(node, "loc"), "lastModified": child_text(node, "lastmod")} for node in root if local_name(node.tag) == "sitemap"]
    if kind != "urlset":
        raise IngestError(f"unsupported sitemap root {kind}")
    items = []
    for node in root:
        if local_name(node.tag) != "url":
            continue
        image = None
        for child in node:
            if local_name(child.tag) != "image":
                continue
            image = next(("".join(descendant.itertext()).strip() for descendant in child.iter() if local_name(descendant.tag) == "loc"), None)
            if image:
                break
        items.append({"url": child_text(node, "loc"), "imageUrl": image, "lastModified": child_text(node, "lastmod")})
    return kind, items


def ingest_sitemaps(source: dict, fetcher=fetch_bytes, limits: dict | None = None, sleeper=time.sleep) -> tuple[list[dict], dict]:
    fetch = source.get("fetch") or {}
    limits = limits or {}
    max_sitemaps = min(int(fetch.get("maxSitemaps") or 200), int(limits.get("maxSitemaps") or 10**9))
    max_candidates = min(int(fetch.get("maxCandidates") or 10000), int(limits.get("maxCandidates") or 10**9))
    queue = list(fetch.get("urls") or [])
    seen_sitemaps = set()
    raw_candidates = []
    while queue and len(seen_sitemaps) < max_sitemaps and len(raw_candidates) < max_candidates:
        url = canonical_url(queue.pop(0))
        if not url or url in seen_sitemaps or not allowed_url(url, fetch, sitemap=True):
            continue
        seen_sitemaps.add(url)
        kind, items = parse_sitemap(fetcher(url, fetch))
        if kind == "sitemapindex":
            queue.extend(item["url"] for item in items if item.get("url"))
        else:
            raw_candidates.extend(item for item in items if item.get("url"))
        delay = max(0.0, float(fetch.get("delaySeconds") or 0.0))
        if delay and queue:
            sleeper(delay)
    candidate_limit_reached = len(raw_candidates) > max_candidates or (len(raw_candidates) >= max_candidates and bool(queue))
    scan_complete = not queue and len(seen_sitemaps) < max_sitemaps and not candidate_limit_reached
    return raw_candidates[:max_candidates], {
        "sitemapsRead": len(seen_sitemaps),
        "queuedSitemapsRemaining": len(queue),
        "candidateLimitReached": candidate_limit_reached,
        "scanComplete": scan_complete,
    }


def preserve_unseen_from_partial_scan(candidates: list[dict], previous: list[dict], stats: dict) -> list[dict]:
    if stats.get("scanComplete", True):
        return candidates
    fresh_urls = {candidate.get("url") for candidate in candidates}
    preserved = [candidate for candidate in previous if candidate.get("url") not in fresh_urls]
    stats["preservedUnseenFromPartialScan"] = len(preserved)
    return candidates + preserved


def feed_urls(fetch: dict) -> list[str]:
    urls = list(fetch.get("urls") or [])
    template = fetch.get("urlTemplate")
    if template:
        start = int((fetch.get("pagination") or {}).get("start") or 1)
        pages = int((fetch.get("pagination") or {}).get("maxPages") or 1)
        urls.extend(str(template).replace("{page}", str(page)) for page in range(start, start + pages))
    return urls


def map_feed_item(item, source: dict, *, xml: bool = False) -> dict:
    mapping = (source.get("fetch") or {}).get("mapping") or {}
    return {field: mapped_value(item, path, xml=xml) for field, path in mapping.items()}


def ingest_feed(source: dict, fetcher=fetch_bytes, sleeper=time.sleep) -> tuple[list[dict], dict]:
    fetch = source.get("fetch") or {}
    method = fetch.get("method")
    results = []
    requests = 0
    for url in feed_urls(fetch):
        payload = fetcher(url, fetch)
        requests += 1
        if method == "json-feed":
            parsed = json.loads(payload.decode(fetch.get("encoding") or "utf-8"))
            items = value_at(parsed, fetch.get("itemsPath") or "")
            if not isinstance(items, list):
                raise IngestError(f"itemsPath did not resolve to a list for {url}")
            results.extend(map_feed_item(item, source) for item in items if isinstance(item, dict))
        elif method == "csv-feed":
            reader = csv.DictReader(io.StringIO(payload.decode(fetch.get("encoding") or "utf-8-sig")))
            results.extend(map_feed_item(item, source) for item in reader)
        elif method == "xml-feed":
            root = ET.fromstring(payload)
            item_name = str(fetch.get("itemPath")).strip("./").split("/")[-1]
            items = [node for node in root.iter() if local_name(node.tag) == item_name]
            results.extend(map_feed_item(item, source, xml=True) for item in items)
        delay = max(0.0, float(fetch.get("delaySeconds") or 0.0))
        if delay:
            sleeper(delay)
    return results, {"feedRequests": requests}


def ingest_source(source: dict, observed_at: str, fetcher=fetch_bytes, limits: dict | None = None) -> tuple[list[dict], dict]:
    method = (source.get("fetch") or {}).get("method")
    raw, stats = ingest_sitemaps(source, fetcher, limits) if method == "sitemap-xml" else ingest_feed(source, fetcher)
    candidates = []
    seen = set()
    for item in raw:
        candidate = normalize_candidate(item, source, observed_at, method)
        if not candidate or candidate["url"] in seen:
            continue
        seen.add(candidate["url"])
        candidates.append(candidate)
    stats.update({"rawCandidates": len(raw), "acceptedCandidates": len(candidates)})
    return candidates, stats


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Ingest normalized discovery candidates from configured catalog sources.")
    parser.add_argument("--source", action="append", dest="source_ids")
    parser.add_argument("--max-sitemaps", type=int)
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def run(args, fetcher=fetch_bytes) -> int:
    roster = load_json(SOURCES_PATH, {})
    wanted = set(args.source_ids or [])
    sources = [source for source in roster.get("sources") or [] if (source.get("fetch") or {}).get("method") in SUPPORTED_METHODS and (not wanted or source.get("id") in wanted)]
    if not sources:
        print("no matching ingest source configured", file=sys.stderr)
        return 1
    invalid = [(source.get("id"), source_contract_errors(source)) for source in sources]
    invalid = [(source_id, errors) for source_id, errors in invalid if errors]
    if invalid:
        for source_id, errors in invalid:
            print(f"invalid source {source_id}: {'; '.join(errors)}", file=sys.stderr)
        return 1

    previous = load_json(OUTPUT_PATH, {"schemaVersion": 1, "candidates": [], "sources": []})
    previous_by_source = {}
    for candidate in previous.get("candidates") or []:
        previous_by_source.setdefault(candidate.get("sourceId"), []).append(candidate)
    observed_at = utc_now()
    all_candidates = [candidate for candidate in previous.get("candidates") or [] if candidate.get("sourceId") not in {source.get("id") for source in sources}]
    reports = []
    successes = 0
    for source in sources:
        try:
            candidates, stats = ingest_source(source, observed_at, fetcher, {"maxSitemaps": args.max_sitemaps, "maxCandidates": args.max_candidates})
            minimum = max(1, int((source.get("fetch") or {}).get("minCandidates") or 1))
            if len(candidates) < minimum:
                raise IngestError(f"accepted {len(candidates)} candidates, below configured minimum {minimum}")
            if not args.dry_run:
                candidates = preserve_unseen_from_partial_scan(candidates, previous_by_source.get(source.get("id"), []), stats)
            all_candidates.extend(candidates)
            reports.append({"sourceId": source.get("id"), "method": (source.get("fetch") or {}).get("method"), "ok": True, **stats})
            successes += 1
            print(f"INGEST {source.get('id')} {len(candidates)} candidates")
        except Exception as error:
            preserved = previous_by_source.get(source.get("id"), [])
            all_candidates.extend(preserved)
            reports.append({"sourceId": source.get("id"), "method": (source.get("fetch") or {}).get("method"), "ok": False, "preserved": len(preserved), "error": str(error)})
            print(f"FAIL {source.get('id')}: {error}; preserved {len(preserved)}", file=sys.stderr)
    output = {"schemaVersion": 1, "generatedAt": observed_at, "candidates": all_candidates, "sources": reports}
    if not args.dry_run and successes:
        atomic_write_json(OUTPUT_PATH, output)
    print(f"{'dry-run' if args.dry_run else 'run'}: {len(all_candidates)} candidates across {successes}/{len(sources)} successful sources")
    return 0 if successes else 1


def main(argv=None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
