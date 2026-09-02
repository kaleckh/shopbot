import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("discover-brands.py")
SPEC = importlib.util.spec_from_file_location("discover_brands", MODULE_PATH)
DISCOVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DISCOVER)


def product(title, vendor, handle, product_type="Mens", tags=None, price="100.00"):
    return {
        "title": title,
        "vendor": vendor,
        "handle": handle,
        "product_type": product_type,
        "tags": tags or [],
        "images": [{"src": "https://cdn.example/image.jpg"}],
        "variants": [{"price": price, "compare_at_price": None}],
    }


def main():
    assert DISCOVER.brand_key("Samurai Jeans") == DISCOVER.brand_key("Samurai")
    source = {"id": "trusted-shop", "name": "Trusted Shop", "kind": "retailer-direct"}
    roster = {
        "scoutRules": {"skipProductContains": ["women", "womens", "skinny"]},
        "sources": [source, {"id": "known", "name": "Known Brand"}],
    }
    payload = {
        "products": [
            product("Relaxed Chore Jacket", "New Label", "relaxed-chore"),
            product("Wide Utility Pant", "New Label", "wide-utility", price="80.00"),
            product("Women's Relaxed Jean", "Wrong Audience", "womens-jean", product_type="Womens"),
            product("Kids Cargo Pant", "Wrong Audience", "kids-cargo", product_type="Kids"),
            product("Relaxed Oxford", "Known Brand", "known-oxford"),
            product("Logo Cap", "Weak Match", "logo-cap"),
        ]
    }
    discovered = DISCOVER.discover_candidates([(source, "https://trusted.example/products.json", payload)], roster, "2026-09-01T00:00:00Z")
    assert [item["brand"] for item in discovered] == ["New Label"]
    candidate = discovered[0]
    assert candidate["id"] == "brand-new-label"
    assert candidate["confidence"] == "exploratory"
    assert len(candidate["representativeProducts"]) == 2
    assert {item["title"] for item in candidate["representativeProducts"]} == {"Relaxed Chore Jacket", "Wide Utility Pant"}
    assert candidate["evidence"]["sampledMatchingProducts"] == 2
    assert "Trusted Shop" in candidate["reason"]
    excluded_source = {**source, "excludeHandles": ["wrong-vendor-product"]}
    excluded_payload = {"products": [product("Wide Work Pant", "Wrong Vendor", "wrong-vendor-product")]}
    assert DISCOVER.discover_candidates([(excluded_source, "https://trusted.example/products.json", excluded_payload)], {**roster, "sources": [excluded_source]}, "now") == []

    learned = DISCOVER.learned_signal_weights(
        {"candidates": [{"id": "brand-liked", "matchedSignals": ["relaxed", "wide"]}, {"id": "brand-price", "matchedSignals": ["knit"]}]},
        {"brand-liked": {"decision": "follow"}, "brand-price": {"decision": "too-expensive"}},
    )
    assert learned == {"relaxed": 3, "wide": 3, "knit": 0}
    base_score, _ = DISCOVER.product_score(product("Relaxed Chore Jacket", "New", "new"), roster["scoutRules"])
    learned_score, _ = DISCOVER.product_score(product("Relaxed Chore Jacket", "New", "new"), roster["scoutRules"], learned)
    assert learned_score > base_score

    previous = {"candidates": [{"id": "brand-new-label", "brand": "New Label", "score": 1, "firstFoundAt": "old", "representativeProducts": [{"id": "trusted-shop-relaxed-chore", "imageUrl": "/product-images/cached.jpg"}]}, {"id": "brand-old", "brand": "Old", "score": 2}]}
    merged = DISCOVER.merge_candidates(previous, discovered, "now", 10)
    assert merged["candidates"][0]["firstFoundAt"] == "old"
    assert next(product for product in merged["candidates"][0]["representativeProducts"] if product["id"] == "trusted-shop-relaxed-chore")["imageUrl"] == "/product-images/cached.jpg"
    assert {item["id"] for item in merged["candidates"]} == {"brand-new-label", "brand-old"}
    merged_again = DISCOVER.merge_candidates(merged, discovered, "later", 10)
    assert len(merged_again["candidates"]) == 2
    live_candidates = DISCOVER.load_json(Path(__file__).parents[1] / "data" / "brand-candidates.json", {})["candidates"]
    assert all(item.get("confidence") and isinstance(item.get("learnedSignals"), list) for item in live_candidates)
    print("brand discovery tests: 15 assertions passed, 0 failed")


if __name__ == "__main__":
    main()
