"""Problem model and integer-cent objective; only the Python standard library is used."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import prod
from pathlib import Path
from typing import Sequence


def _integer(value: object, label: str, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")


def _name(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")


@dataclass(frozen=True)
class Store:
    name: str
    delivery_cents: int
    free_delivery_threshold_cents: int | None = None

    def __post_init__(self) -> None:
        _name(self.name, "store name")
        _integer(self.delivery_cents, "delivery_cents")
        if self.free_delivery_threshold_cents is not None:
            _integer(self.free_delivery_threshold_cents, "free_delivery_threshold_cents")


@dataclass(frozen=True)
class Item:
    name: str
    quantity: int
    prices_cents: tuple[int | None, ...]

    def __post_init__(self) -> None:
        _name(self.name, "item name")
        _integer(self.quantity, "quantity", 1)
        if not isinstance(self.prices_cents, (tuple, list)):
            raise ValueError("prices_cents must be an array")
        object.__setattr__(self, "prices_cents", tuple(self.prices_cents))
        for price in self.prices_cents:
            if price is not None:
                _integer(price, "price")


@dataclass(frozen=True)
class Problem:
    name: str
    stores: tuple[Store, ...]
    items: tuple[Item, ...]

    def __post_init__(self) -> None:
        _name(self.name, "problem name")
        if not isinstance(self.stores, (tuple, list)) or not self.stores:
            raise ValueError("problem must contain at least one store")
        if not isinstance(self.items, (tuple, list)) or not self.items:
            raise ValueError("problem must contain at least one item")
        object.__setattr__(self, "stores", tuple(self.stores))
        object.__setattr__(self, "items", tuple(self.items))
        if not all(isinstance(store, Store) for store in self.stores):
            raise ValueError("stores must contain Store objects")
        if not all(isinstance(item, Item) for item in self.items):
            raise ValueError("items must contain Item objects")
        for item in self.items:
            if len(item.prices_cents) != len(self.stores):
                raise ValueError(f"{item.name}: one price entry is required per store")
            if all(price is None for price in item.prices_cents):
                raise ValueError(f"{item.name}: item is unavailable at every store")


def validate_assignment(problem: Problem, assignment: Sequence[int]) -> None:
    if len(assignment) != len(problem.items):
        raise ValueError("assignment must contain one store index per item")
    for item, store_index in zip(problem.items, assignment):
        _integer(store_index, "store index")
        if store_index >= len(problem.stores):
            raise ValueError("store index is outside the store list")
        if item.prices_cents[store_index] is None:
            raise ValueError(f"{item.name}: assigned to an unavailable store")


def delivery_cost(store: Store, subtotal: int, item_count: int) -> int:
    """A used store has free delivery at or above its threshold (if any)."""
    if item_count == 0:
        return 0
    threshold = store.free_delivery_threshold_cents
    return 0 if threshold is not None and subtotal >= threshold else store.delivery_cents


def breakdown(problem: Problem, assignment: Sequence[int]) -> list[dict[str, object]]:
    """Return one row per store, including unused stores with zero cost."""
    validate_assignment(problem, assignment)
    subtotals = [0] * len(problem.stores)
    counts = [0] * len(problem.stores)
    for item, store_index in zip(problem.items, assignment):
        price = item.prices_cents[store_index]
        assert price is not None
        subtotals[store_index] += item.quantity * price
        counts[store_index] += 1
    return [
        {
            "store_index": index,
            "store": store.name,
            "item_count": counts[index],
            "products_cents": subtotals[index],
            "delivery_cents": delivery_cost(store, subtotals[index], counts[index]),
            "total_cents": subtotals[index] + delivery_cost(store, subtotals[index], counts[index]),
        }
        for index, store in enumerate(problem.stores)
    ]


def evaluate(problem: Problem, assignment: Sequence[int]) -> int:
    """Sum product and delivery costs. All arithmetic is exact integer cents."""
    return sum(int(row["total_cents"]) for row in breakdown(problem, assignment))


def cheapest_assignment(problem: Problem) -> tuple[int, ...]:
    """Choose the cheapest available unit price; ties use the first store."""
    return tuple(
        min(
            (index for index, price in enumerate(item.prices_cents) if price is not None),
            key=lambda index: item.prices_cents[index],
        )
        for item in problem.items
    )


def state_count(problem: Problem) -> int:
    return prod(sum(price is not None for price in item.prices_cents) for item in problem.items)


def load_problem(path: str | Path) -> Problem:
    """Load fixed unit prices. JSON null means unavailable; quantities cannot split."""
    with Path(path).open(encoding="utf-8-sig") as handle:
        raw = json.load(handle)
    try:
        return Problem(
            name=raw["name"],
            stores=tuple(
                Store(
                    name=store["name"],
                    delivery_cents=store["delivery_cents"],
                    free_delivery_threshold_cents=store.get("free_delivery_threshold_cents"),
                )
                for store in raw["stores"]
            ),
            items=tuple(
                Item(name=item["name"], quantity=item["quantity"], prices_cents=item["prices_cents"])
                for item in raw["items"]
            ),
        )
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"invalid problem JSON: {error}") from error
