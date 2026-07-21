"""Category mapping + price/deal synthesis for AdidLaBs mock catalog.

This module is deliberately dependency-free (stdlib only) so it can be imported
by the fetch/seed scripts, the unit tests, and — if needed — a Lambda, without
pulling `requests` or any AWS SDK into the import graph.

The six contract categories are:

    shoes, pants, tshirt, jumper, jacket, accessory

Every HuggingFace `ashraq/fashion-product-images-small` row exposes (among
others) these metadata fields:

    articleType, subCategory, masterCategory, gender, season, baseColour,
    usage, productDisplayName, year, id

We map `articleType` (fine-grained) with a fallback to `subCategory` /
`masterCategory` (coarse) onto the six categories. Rows that cannot be mapped to
one of the six are dropped by the caller (mapping returns ``None``).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

# The six contract categories, in canonical order.
CATEGORIES = ("shoes", "pants", "tshirt", "jumper", "jacket", "accessory")

# --------------------------------------------------------------------------- #
# articleType -> category. articleType is the most specific HF field; keys are
# lower-cased for case-insensitive lookup. This table is intentionally broad so
# a ~200-row sample lands enough items in every one of the six buckets.
# --------------------------------------------------------------------------- #
_ARTICLE_TYPE_MAP: Dict[str, str] = {
    # --- shoes ---
    "casual shoes": "shoes",
    "sports shoes": "shoes",
    "formal shoes": "shoes",
    "sandals": "shoes",
    "flip flops": "shoes",
    "heels": "shoes",
    "flats": "shoes",
    "sneakers": "shoes",
    "boots": "shoes",
    "sports sandals": "shoes",
    "loafers": "shoes",
    "shoe accessories": "accessory",  # laces etc. -> accessory, not shoes
    # --- pants ---
    "jeans": "pants",
    "trousers": "pants",
    "track pants": "pants",
    "shorts": "pants",
    "leggings": "pants",
    "capris": "pants",
    "trunk": "pants",
    "tracksuits": "pants",
    "jeggings": "pants",
    "churidar": "pants",
    "salwar": "pants",
    "rain trousers": "pants",
    # --- tshirt ---
    "tshirts": "tshirt",
    "tshirt": "tshirt",
    "tops": "tshirt",
    "shirts": "tshirt",
    "tunics": "tshirt",
    "camisoles": "tshirt",
    "tank tops": "tshirt",
    "polo": "tshirt",
    # --- jumper ---
    "sweaters": "jumper",
    "sweatshirts": "jumper",
    "pullover": "jumper",
    "cardigan": "jumper",
    "hoodie": "jumper",
    "hoodies": "jumper",
    # --- jacket ---
    "jackets": "jacket",
    "blazers": "jacket",
    "coats": "jacket",
    "rain jacket": "jacket",
    "waistcoat": "jacket",
    "nehru jackets": "jacket",
    "parka": "jacket",
    # --- accessory ---
    "watches": "accessory",
    "belts": "accessory",
    "sunglasses": "accessory",
    "caps": "accessory",
    "hat": "accessory",
    "hats": "accessory",
    "scarves": "accessory",
    "socks": "accessory",
    "gloves": "accessory",
    "backpacks": "accessory",
    "handbags": "accessory",
    "wallets": "accessory",
    "ties": "accessory",
    "bracelet": "accessory",
    "necklace and chains": "accessory",
    "earrings": "accessory",
    "ring": "accessory",
    "jewellery set": "accessory",
    "pendant": "accessory",
    "headband": "accessory",
    "muffler": "accessory",
    "stoles": "accessory",
    "duffel bag": "accessory",
    "clutches": "accessory",
    "messenger bag": "accessory",
    "laptop bag": "accessory",
    "mobile pouch": "accessory",
    "waist pouch": "accessory",
    "sports accessories": "accessory",
    "accessory gift set": "accessory",
    "beauty accessory": "accessory",
    "travel accessory": "accessory",
}

# --------------------------------------------------------------------------- #
# Coarse fallbacks. `subCategory` / `masterCategory` catch article types the
# fine table missed (dataset has hundreds of long-tail article types).
# --------------------------------------------------------------------------- #
_SUBCATEGORY_MAP: Dict[str, str] = {
    "shoes": "shoes",
    "sandal": "shoes",
    "flip flops": "shoes",
    "topwear": "tshirt",
    "bottomwear": "pants",
    "innerwear": "tshirt",
    "loungewear and nightwear": "tshirt",
    "sweaters": "jumper",
    "sweatshirts": "jumper",
    "jackets": "jacket",
    "coats": "jacket",
    "winterwear": "jacket",
    "watches": "accessory",
    "belts": "accessory",
    "bags": "accessory",
    "eyewear": "accessory",
    "headwear": "accessory",
    "socks": "accessory",
    "gloves": "accessory",
    "scarves": "accessory",
    "ties": "accessory",
    "jewellery": "accessory",
    "wallets": "accessory",
    "accessories": "accessory",
    "mufflers": "accessory",
    "stoles": "accessory",
    "cufflinks": "accessory",
    "sports accessories": "accessory",
    "wristbands": "accessory",
}

_MASTERCATEGORY_MAP: Dict[str, str] = {
    "footwear": "shoes",
    "accessories": "accessory",
}


def _norm(value: Any) -> str:
    """Lower-case, trimmed string; ``None`` and non-str become empty string."""
    if value is None:
        return ""
    return str(value).strip().lower()


def map_category(row: Dict[str, Any]) -> Optional[str]:
    """Map a HF metadata row to one of the six contract categories.

    Resolution order (most specific first):
      1. ``articleType`` exact match
      2. ``subCategory`` match
      3. ``masterCategory`` match
      4. a couple of last-ditch keyword heuristics on articleType

    Returns the category string, or ``None`` when the row does not belong to any
    of the six categories (caller drops it).
    """
    article = _norm(row.get("articleType"))
    if article in _ARTICLE_TYPE_MAP:
        return _ARTICLE_TYPE_MAP[article]

    sub = _norm(row.get("subCategory"))
    if sub in _SUBCATEGORY_MAP:
        return _SUBCATEGORY_MAP[sub]

    master = _norm(row.get("masterCategory"))
    if master in _MASTERCATEGORY_MAP:
        return _MASTERCATEGORY_MAP[master]

    # Last-ditch keyword heuristics on the fine field.
    if article:
        if "shoe" in article or "sandal" in article or "boot" in article:
            return "shoes"
        if "jean" in article or "trouser" in article or "pant" in article or "short" in article:
            return "pants"
        if "shirt" in article or "tee" in article or "top" in article:
            return "tshirt"
        if "sweat" in article or "jumper" in article or "hood" in article or "pullover" in article:
            return "jumper"
        if "jacket" in article or "coat" in article or "blazer" in article:
            return "jacket"
        if "bag" in article or "watch" in article or "belt" in article or "cap" in article:
            return "accessory"

    return None


# --------------------------------------------------------------------------- #
# Deterministic synthetic pricing. We hash the item id so the same row always
# gets the same price/deal across runs (idempotent seeding), while different
# categories occupy different, sensible USD bands. Prices are fictional.
# --------------------------------------------------------------------------- #
# (min, max) USD base-price band per category.
_PRICE_BANDS: Dict[str, tuple[int, int]] = {
    "shoes": (49, 189),
    "pants": (29, 129),
    "tshirt": (15, 59),
    "jumper": (39, 149),
    "jacket": (69, 259),
    "accessory": (9, 89),
}

# Nice-looking price endings so synthetic prices read like retail.
_PRICE_ENDINGS = (0.00, 0.95, 0.99, 0.50, 0.90)


def _hash_int(seed: str) -> int:
    """Stable non-negative int from a string (md5 -> int)."""
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def synthesize_price(item_id: str, category: str) -> Dict[str, Any]:
    """Deterministically synthesize an USD price + optional deal for an item.

    Returns a dict with:
        price          -> float, the current sell price in USD
        original_price -> float, the pre-deal price (== price when no deal)
        currency       -> "USD"
        on_deal        -> bool
        discount_pct   -> int (0 when no deal)

    Deterministic in ``item_id`` so re-seeding never churns the table.
    """
    band = _PRICE_BANDS.get(category, (19, 99))
    h = _hash_int(f"{item_id}:{category}")

    span = band[1] - band[0]
    whole = band[0] + (h % (span + 1))
    ending = _PRICE_ENDINGS[(h >> 8) % len(_PRICE_ENDINGS)]
    original = round(whole + ending, 2)

    # ~35% of items are on deal; discount tiers 10/20/30/40/50%.
    on_deal = (h >> 16) % 100 < 35
    discount_pct = 0
    price = original
    if on_deal:
        tiers = (10, 20, 30, 40, 50)
        discount_pct = tiers[(h >> 20) % len(tiers)]
        price = round(original * (100 - discount_pct) / 100.0, 2)

    return {
        "price": price,
        "original_price": original,
        "currency": "USD",
        "on_deal": on_deal,
        "discount_pct": discount_pct,
    }


# --------------------------------------------------------------------------- #
# Fictional product-name synthesis.
#
# The raw HF `productDisplayName` field carries REAL brand + product names
# ("Nike ... Shoe", "ADIDAS Men Spry M Sandals", "Puma ..."). The AdidLaBs
# contract is hard: NO adidas trademarks, all products fictional. So we NEVER
# surface the upstream name. Instead we deterministically synthesize a
# fictional AdidLaBs product name from the item_id, keeping only the neutral,
# non-branded descriptors (base colour + article type) so the name still reads
# naturally and stays weather/style-relevant.
# --------------------------------------------------------------------------- #
_NAME_ADJECTIVES = (
    "Stratus", "Meridian", "Halcyon", "Cirrus", "Vector", "Solace", "Nimbus",
    "Beacon", "Signal", "Marlowe", "Willow", "Ember", "Cove", "Loft", "Drift",
    "Cabin", "Relay", "Haven", "Pulse", "Tempest", "Harbor", "Atlas", "Vesper",
    "Sterling", "Frost", "Orbit", "Ridge", "Summit", "Quartz", "Dune", "Anchor",
    "Aurora", "Zephyr", "Onyx", "Cascade", "Terra", "Lumen", "Nomad", "Verve",
)

# Neutral article-type nouns per category (never brand-derived).
_NAME_NOUNS: Dict[str, tuple[str, ...]] = {
    "shoes": ("Runner", "Trainer", "Low", "Sneaker", "Boot", "Court", "Sandal"),
    "pants": ("Jean", "Trouser", "Chino", "Track Pant", "Short", "Legging"),
    "tshirt": ("Tee", "Shirt", "Top", "Ringer Tee", "Henley"),
    "jumper": ("Crew", "Hoodie", "Knit", "Sweatshirt", "Cardigan", "Pullover"),
    "jacket": ("Shell", "Field Jacket", "Coat", "Wind Runner", "Blazer", "Vest"),
    "accessory": ("Watch", "Daypack", "Sunglasses", "Belt", "Beanie", "Scarf",
                  "Tote", "Wallet", "Cap"),
}

_COLOUR_WORDS = {
    "black", "white", "grey", "gray", "navy", "blue", "green", "olive", "brown",
    "tan", "red", "burgundy", "pink", "beige", "cream", "charcoal", "sand",
    "teal", "mustard", "silver", "gold", "slate", "sage", "rust", "khaki",
}


def synthesize_name(item_id: str, category: str, base_colour: str) -> str:
    """Deterministic, brand-safe fictional product name.

    Form: "<Adjective> [<Colour>] <Noun>" — e.g. "Stratus Olive Runner".
    Colour is included only when it's a recognised plain colour word (so we
    never echo a brand token that happened to sit in the colour field).
    """
    h = _hash_int(f"name:{item_id}:{category}")
    adj = _NAME_ADJECTIVES[h % len(_NAME_ADJECTIVES)]
    nouns = _NAME_NOUNS.get(category, ("Piece",))
    noun = nouns[(h >> 8) % len(nouns)]

    colour = _norm(base_colour).split()[0] if base_colour else ""
    colour_part = f" {colour.title()}" if colour in _COLOUR_WORDS else ""
    return f"{adj}{colour_part} {noun}"


def build_item(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn a raw HF metadata row into a normalized catalog item.

    Returns ``None`` if the row can't be mapped to one of the six categories.
    The output dict is the exact shape written to the ``adidlabs-catalog``
    DynamoDB table (pk: ``item_id``).

    IMPORTANT: the upstream ``productDisplayName`` (which contains real brand
    names) is DISCARDED. We synthesize a fictional AdidLaBs name so no real
    trademark — adidas or otherwise — ever reaches the catalog, KB, or UI.
    """
    category = map_category(row)
    if category is None:
        return None

    raw_id = row.get("id")
    if raw_id is None or _norm(raw_id) == "":
        return None
    item_id = f"hf-{_norm(raw_id)}"

    name = synthesize_name(item_id, category, row.get("baseColour", ""))
    pricing = synthesize_price(item_id, category)

    return {
        "item_id": item_id,
        "name": str(name).strip(),
        "category": category,
        "gender": _norm(row.get("gender")) or "unisex",
        "season": _norm(row.get("season")) or "all",
        "base_colour": _norm(row.get("baseColour")) or "assorted",
        "usage": _norm(row.get("usage")) or "casual",
        "article_type": _norm(row.get("articleType")),
        "source": "huggingface:ashraq/fashion-product-images-small",
        **pricing,
    }
