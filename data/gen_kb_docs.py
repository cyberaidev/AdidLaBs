#!/usr/bin/env python3
"""Generate the AdidLaBs Knowledge Base markdown corpus.

Produces a small markdown corpus that `search_lab_knowledge` retrieves over:

  1. weather-to-outfit style guide  (weather_style_guide.md)
  2. fabric care sheets             (fabric_care.md)
  3. sizing + returns FAQ           (sizing_returns_faq.md)
  4. product stories                (product_stories.md) — references real
                                     catalog item_ids/names so RAG answers can
                                     ground on actual products.

Output dir defaults to ``data/kb_docs/``. That directory is what
``setup_kb.py`` uploads to the S3 corpus bucket for ingestion (and what the
FAISS-in-Lambda fallback would embed offline).

Every generated doc carries the mandatory disclaimer footer.

Usage:
    python data/gen_kb_docs.py [--catalog data/catalog.json] [--out data/kb_docs]
                               [--target 200] [--force-fallback]
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

from category_map import CATEGORIES
from fetch_hf import build_catalog

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CATALOG = os.path.join(HERE, "catalog.json")
DEFAULT_OUT = os.path.join(HERE, "kb_docs")

DISCLAIMER = (
    "\n\n---\n"
    "*Concept demo - no affiliation with adidas AG. All products fictional.*\n"
)


def _load_catalog(path: str, target: int, force_fallback: bool) -> List[Dict[str, Any]]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return list(json.load(fh))
    items, _ = build_catalog(target, force_fallback)
    return items


# --------------------------------------------------------------------------- #
# Doc 1 — weather-to-outfit style guide
# --------------------------------------------------------------------------- #
def weather_style_guide() -> str:
    return """# AdidLaBs Weather-to-Outfit Style Guide

The stylist agents use this guide to translate a 3-day forecast into
weather-matched outfit picks across the six AdidLaBs categories.

## Temperature bands

- **Hot (>= 26 C):** Prioritise breathable tshirts and shorts. Favour light
  colours and linen or moisture-wicking fabrics. Accessory picks: sunglasses,
  caps, canvas totes. Skip jumpers and heavy jackets.
- **Warm (18–25 C):** Tshirts or light shirts with pants or chinos. A packable
  wind jacket is optional for evenings. Sneakers or flats for shoes.
- **Mild (10–17 C):** Layer a tshirt under a light jumper. Full-length pants.
  A field jacket or blazer works. Add a light scarf if breezy.
- **Cool (2–9 C):** Merino or cable-knit jumper as the core layer, jacket or
  coat on top. Closed shoes or boots. Beanie and scarf as accessories.
- **Cold (< 2 C):** Insulated jacket or quilted coat over a jumper. Thermal
  pants. Waterproof boots. Gloves, beanie, merino socks.

## Precipitation

- **Rain expected:** Recommend a rain jacket or shell (jacket category) and
  water-resistant footwear (rain boots, trail runners). Avoid suede and canvas.
- **Snow:** Insulated coat, waterproof boots, merino socks, gloves.
- **Dry:** No waterproofing constraint; optimise for temperature band only.

## Wind

- **Windy (> 25 km/h):** Prefer a wind-runner or shell jacket over an open
  cardigan. Secure accessories (caps over loose hats).

## Season cues

- **Summer:** Lean into tshirts, shorts, sandals, sunglasses.
- **Autumn/Fall:** Layering season — jumpers, field jackets, boots.
- **Winter:** Coats, insulated jackets, knitwear, cold-weather accessories.
- **Spring:** Transitional — light jumpers, wind jackets, sneakers.

## Composition rule

Assemble one coherent outfit per turn: one top (tshirt or jumper), one bottom
(pants), footwear (shoes), an optional outer layer (jacket) chosen by the
temperature/precip bands above, and one or two accessories that match the
conditions. Prefer items flagged `on_deal` when two candidates are otherwise
equivalent.
"""


# --------------------------------------------------------------------------- #
# Doc 2 — fabric care sheets
# --------------------------------------------------------------------------- #
def fabric_care() -> str:
    return """# AdidLaBs Fabric & Care Sheets

Care guidance the agents cite when justifying a pick or answering a care
question. Fictional product line; guidance is generic best-practice.

## Cotton (tshirts, some jumpers)
- Machine wash cold, inside out, with like colours.
- Tumble dry low or line dry to limit shrinkage.
- Warm iron if needed; do not iron prints directly.

## Merino wool (jumpers, socks)
- Hand wash or wool-cycle in cold water with wool detergent.
- Do not wring; dry flat away from direct heat.
- Naturally odour-resistant — air between wears instead of over-washing.

## Linen (summer shirts, trousers)
- Machine wash cool, gentle cycle.
- Remove while damp and hang to keep the natural drape; iron on the linen
  setting while slightly damp.

## Technical / performance synthetics (track pants, wind jackets)
- Machine wash cold, no fabric softener (it clogs wicking fibres).
- Air dry; avoid high heat which degrades DWR coatings.
- Reproof shell jackets periodically to restore water repellency.

## Denim (jeans)
- Wash sparingly, cold, inside out to preserve indigo.
- Line dry to maintain fit and reduce energy use.

## Leather (belts, wallets, some shoes)
- Wipe clean with a damp cloth; condition occasionally.
- Keep away from prolonged water; air dry naturally if wet.

## Down / insulated (quilted coats, puffer vests)
- Wash on a gentle cycle with down-specific detergent.
- Tumble dry low with dryer balls to re-loft the fill.
"""


# --------------------------------------------------------------------------- #
# Doc 3 — sizing + returns FAQ
# --------------------------------------------------------------------------- #
def sizing_returns_faq() -> str:
    return """# AdidLaBs Sizing & Returns FAQ

## Sizing

**Q: How do AdidLaBs sizes run?**
A: True to size for tshirts and jumpers. Pants are offered in EU waist sizing;
size up one if between sizes for a relaxed fit.

**Q: Do shoes run large or small?**
A: Shoes run true to size. For trail runners and boots worn with thick socks,
consider a half size up.

**Q: Is there a size guide per category?**
A: Yes. Each product page links a category size chart (tshirt, pants, jumper,
jacket, shoes). Accessories are one-size unless noted (e.g. belts by waist).

**Q: What about unisex items?**
A: Unisex items follow the men's numeric chart; women should size down one for a
fitted look.

## Returns & exchanges

**Q: What is the returns window?**
A: 30 days from delivery for unworn items with tags attached.

**Q: How do I start a return?**
A: This is a concept demo — checkout and returns are non-functional. In a real
deployment you would open the bag, select the item, and request a return label.

**Q: Are sale / outlet items returnable?**
A: In this fictional store, deal-flagged items follow the same 30-day policy.

**Q: How long do refunds take?**
A: Typically 5–7 business days after the item is received (demo copy).

## Shipping

**Q: Shipping cost?**
A: The demo advertises free shipping on the Forecast Collection. No real orders
are processed.
"""


# --------------------------------------------------------------------------- #
# Doc 4 — product stories (grounded on the real catalog)
# --------------------------------------------------------------------------- #
def product_stories(items: List[Dict[str, Any]]) -> str:
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for it in items:
        by_cat[it["category"]].append(it)

    lines: List[str] = [
        "# AdidLaBs Product Stories",
        "",
        "Short narrative blurbs per product, grouped by category. Agents retrieve "
        "these to add colour and justify weather-matched picks. Prices are "
        "synthetic EUR; all products fictional.",
        "",
    ]

    # Blurb templates keyed by category, filled with item attributes.
    templates = {
        "shoes": "A {colour} {article} built for {usage} days. The **{name}** pairs a "
                 "cushioned ride with an all-weather outsole.",
        "pants": "The **{name}** is a {colour} {article} cut for {usage} wear — "
                 "comfortable through a full {season} forecast.",
        "tshirt": "The **{name}** is a {colour} {article} in a breathable weave, an "
                  "easy base layer for {season} conditions.",
        "jumper": "The **{name}** is a {colour} {article} that traps warmth without "
                  "bulk — the go-to mid-layer when the forecast turns cool.",
        "jacket": "The **{name}** is a {colour} {article} engineered to shrug off "
                  "wind and rain, the outer layer for an unsettled forecast.",
        "accessory": "The **{name}** rounds out the look — a {colour} {article} that "
                     "earns its place in any {season} kit.",
    }

    for cat in CATEGORIES:
        cat_items = by_cat.get(cat, [])
        lines.append(f"## {cat.title()}")
        lines.append("")
        if not cat_items:
            lines.append("_No items in this category in the current sample._")
            lines.append("")
            continue
        # Cap at 12 stories/category to keep the corpus small.
        for it in cat_items[:12]:
            blurb = templates[cat].format(
                name=it.get("name", cat.title()),
                colour=it.get("base_colour", "assorted"),
                article=it.get("article_type") or cat,
                usage=it.get("usage", "everyday"),
                season=it.get("season", "all-season"),
            )
            price = it.get("price")
            original = it.get("original_price", price)
            deal = ""
            if it.get("on_deal"):
                deal = (f" On deal at **EUR {price}** "
                        f"(was EUR {original}, -{it.get('discount_pct', 0)}%).")
            else:
                deal = f" Priced at **EUR {price}**."
            lines.append(f"- `{it['item_id']}` — {blurb}{deal}")
        lines.append("")

    return "\n".join(lines)


DOCS = {
    "weather_style_guide.md": lambda items: weather_style_guide(),
    "fabric_care.md": lambda items: fabric_care(),
    "sizing_returns_faq.md": lambda items: sizing_returns_faq(),
    "product_stories.md": product_stories,
}


def generate(items: List[Dict[str, Any]], out_dir: str) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    for filename, builder in DOCS.items():
        body = builder(items)
        content = body.rstrip() + DISCLAIMER
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        written.append(path)
    return written


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate AdidLaBs KB markdown corpus.")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help="Catalog JSON path.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output directory for KB docs.")
    parser.add_argument("--target", type=int, default=200,
                        help="Items to sample if catalog is built on the fly.")
    parser.add_argument("--force-fallback", action="store_true",
                        help="Use synthetic_fallback.json instead of HF.")
    args = parser.parse_args(argv)

    items = _load_catalog(args.catalog, args.target, args.force_fallback)
    written = generate(items, args.out)
    print(f"[gen_kb_docs] wrote {len(written)} docs to {args.out}:")
    for path in written:
        print(f"  - {os.path.basename(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
