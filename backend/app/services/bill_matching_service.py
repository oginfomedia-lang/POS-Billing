"""Bill lines → our products, first match wins:

    1. alias          this supplier's bill said exactly this before (supplier_item_aliases)
    2. supplier_code  the supplier's item code printed on the line (supplier_products.supplier_product_code)
    3. barcode        an EAN printed on the line
    4. name           closest product name (rapidfuzz), in English letters or sound-alike (search_key)

remember() saves 1. when a bill is saved, so each supplier's bills match better over time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process
from sqlalchemy import select

from app.extensions import db
from app.models.product import Product, ProductBarcode
from app.models.supplier_item_alias import SupplierItemAlias
from app.models.supplier_product import SupplierProduct
from app.utils.search_key import search_key

SURE = 90  # name score taken as the right product ...
MIN_GAP = 5  # ... when the next best is at least this far behind
POSSIBLE = 70  # below this: "not found"
LINKED_BONUS = 5  # products already bought from this supplier


@dataclass
class Match:
    status: str  # matched / check / not_found
    product: Product | None = None
    source: str | None = None
    candidates: list[tuple[Product, int]] = field(default_factory=list)  # (product, score), best first


@dataclass
class _Catalog:
    """Everything needed to match one bill, loaded once."""
    products: list[Product]
    by_id: dict[int, Product]
    names: list[str]
    keys: list[str]
    aliases: dict[str, int]
    codes: dict[str, int]
    linked: set[int]


def _catalog(supplier_id: int | None, store_id: int) -> _Catalog:
    products = list(db.session.scalars(
        select(Product).where(Product.is_active.is_(True),
                              (Product.store_id == store_id) | (Product.store_id.is_(None)))
    ))
    aliases: dict[str, int] = {}
    codes: dict[str, int] = {}
    linked: set[int] = set()
    if supplier_id:
        aliases = {a.description_key: a.product_id for a in db.session.scalars(
            select(SupplierItemAlias).where(SupplierItemAlias.supplier_id == supplier_id))}
        for sp in db.session.scalars(select(SupplierProduct).where(
                SupplierProduct.supplier_id == supplier_id, SupplierProduct.is_active.is_(True))):
            linked.add(sp.product_id)
            if sp.supplier_product_code:
                codes[sp.supplier_product_code.strip().upper()] = sp.product_id
    return _Catalog(products, {p.id: p for p in products}, [p.name.lower() for p in products],
                    [p.search_key or "" for p in products], aliases, codes, linked)


def match_lines(supplier_id: int | None, store_id: int, descriptions: list[str]) -> list[Match]:
    if not descriptions:
        return []
    catalog = _catalog(supplier_id, store_id)
    return [_match_one(d, catalog) for d in descriptions]


def _match_one(description: str, c: _Catalog) -> Match:
    pid = c.aliases.get(search_key(description))
    if pid in c.by_id:
        return Match("matched", c.by_id[pid], "alias")

    for token in re.findall(r"[A-Za-z0-9\-]+", description):
        pid = c.codes.get(token.upper())
        if pid in c.by_id:
            return Match("matched", c.by_id[pid], "supplier_code")

    for token in re.findall(r"\b\d{8,14}\b", description):
        pid = db.session.scalar(select(ProductBarcode.product_id).where(ProductBarcode.barcode == token))
        if pid in c.by_id:
            return Match("matched", c.by_id[pid], "barcode")

    if not c.products:
        return Match("not_found")
    scores: dict[int, float] = {}
    for _, score, i in process.extract(description.lower(), c.names, scorer=fuzz.token_set_ratio, limit=5):
        scores[i] = max(scores.get(i, 0), score)
    key = search_key(description)
    if key:
        for _, score, i in process.extract(key, c.keys, scorer=fuzz.ratio, limit=5):
            scores[i] = max(scores.get(i, 0), score)
    ranked = sorted(
        ((c.products[i], int(min(100, s + (LINKED_BONUS if c.products[i].id in c.linked else 0))))
         for i, s in scores.items()),
        key=lambda pair: -pair[1],
    )[:3]
    best = ranked[0][1] if ranked else 0
    second = ranked[1][1] if len(ranked) > 1 else 0
    if best >= SURE and best - second >= MIN_GAP:
        return Match("matched", ranked[0][0], "name", ranked)
    if best >= POSSIBLE:
        return Match("check", ranked[0][0], "name", ranked)
    return Match("not_found", candidates=ranked)


def remember(supplier_id: int, pairs: list[tuple[str, int]]) -> None:
    """(text on the bill, product chosen) for each saved line. Runs inside the caller's transaction."""
    latest: dict[str, tuple[str, int]] = {}
    for description, product_id in pairs:
        key = search_key(description)[:400]
        if key:
            latest[key] = (description.strip()[:300], product_id)
    for key, (description, product_id) in latest.items():
        alias = db.session.scalar(select(SupplierItemAlias).where(
            SupplierItemAlias.supplier_id == supplier_id, SupplierItemAlias.description_key == key))
        if alias:
            alias.product_id = product_id
            alias.description = description
            alias.times_used += 1
        else:
            db.session.add(SupplierItemAlias(supplier_id=supplier_id, description_key=key,
                                             description=description, product_id=product_id, times_used=1))
    db.session.flush()