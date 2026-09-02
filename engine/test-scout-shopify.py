import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("scout-shopify.py")
SPEC = importlib.util.spec_from_file_location("scout_shopify", MODULE_PATH)
SCOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOUT)


def product(title, product_type="", tags=None, handle=""):
    return {"title": title, "handle": handle, "product_type": product_type, "tags": tags or []}


def main():
    category_cases = {
        "P550 Basketball Oxfords": "shoes",
        "Japanese Seersucker Short Sleeve Shirt": "tops",
        "Tin Cloth Short Lined Cruiser Jacket": "outerwear",
        "Terry Sweatshort 7 inch": "shorts",
        "True Guy Selvedge": "pants",
        "Ventile Mac": "outerwear",
        "Relaxed-Fit Denim Hoodie Jacket": "outerwear",
        "V Neck Jumper": "knit",
        "Canvas Tote": "accessories",
    }
    for title, expected in category_cases.items():
        actual = SCOUT.guess_category(product(title))
        assert actual == expected, f"{title}: expected {expected}, got {actual}"

    modes = SCOUT.guess_modes(product("GORE-TEX Trail Shell"))
    assert "athletic-tech" in modes
    assert "classic-casual" not in modes
    modes = SCOUT.guess_modes(product("Pleated Wool Trouser"))
    assert "corporate-presentable" in modes
    assert "minimal-clean" in modes

    rules = {"skipProductContains": ["slim", "skinny", "women", "womens", "gals"]}
    assert SCOUT.skip_product(product("Pixie || Dreamland", "Home > Women > Pants > Jeans"), {}, rules)
    assert SCOUT.skip_product(product("Bree Stovepipe", handle="bree-slim-skinny-deja-blue"), {}, rules)
    assert SCOUT.skip_product(product("Relaxed Straight Jean", tags=["Womens Denim"]), {}, rules)
    assert SCOUT.skip_product(product("Utility Pant", tags=["gals"]), {}, rules)
    assert SCOUT.skip_product(
        product("Jodi Cropped Jacket", handle="jodi-jacket-in-borderline"),
        {"excludeHandles": ["jodi-jacket-in-borderline"]},
        rules,
    )
    assert not SCOUT.skip_product(product("Men's Relaxed Straight Jean", "Denim"), {}, rules)

    data = {
        "suggestions": [
            {"id": "curated", "category": "accessory", "modes": ["minimal-clean"], "provenance": {"checkedBy": "human"}},
            {"id": "scout", "title": "Graphic Tee", "category": "other", "modes": ["streetwear", "classic-casual"], "provenance": {"checkedBy": "shopbot scout-shopify.py"}},
        ]
    }
    normalized = SCOUT.normalize_existing_scout_records(data)
    assert normalized["changed"] == 2
    assert data["suggestions"][0]["category"] == "accessories"
    assert data["suggestions"][0]["modes"] == ["minimal-clean"]
    assert data["suggestions"][1]["category"] == "tops"
    assert data["suggestions"][1]["modes"] == ["streetwear"]
    preserved = {"suggestions": [{"id": "raleigh-alexander-stretch-thyme", "title": "Alexander Stretch | Thyme", "category": "pants", "modes": ["classic-casual"], "provenance": {"checkedBy": "shopbot scout-shopify.py"}}]}
    SCOUT.normalize_existing_scout_records(preserved)
    assert preserved["suggestions"][0]["category"] == "pants"
    print("scout classifier tests: 23 assertions passed, 0 failed")


if __name__ == "__main__":
    main()
