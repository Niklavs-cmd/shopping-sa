"""A from-scratch simulated annealing implementation with feasible symmetric moves."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Sequence

from .model import Problem, cheapest_assignment, delivery_cost, validate_assignment


@dataclass(frozen=True)
class AnnealingResult:
    assignment: tuple[int, ...]
    total_cents: int
    elapsed_seconds: float
    iterations: int
    accepted_moves: int
    improvements: int


def anneal(
    problem: Problem,
    *,
    seed: int = 0,
    iterations: int = 20_000,
    start_temp_cents: float = 2000.0,
    end_temp_cents: float = 1.0,
    initial: Sequence[int] | None = None,
) -> AnnealingResult:
    """Minimize total purchase cost and return the best state seen, including start.

    A proposal relocates one movable item with probability .75, or two distinct
    movable items with probability .25. Each new store is chosen uniformly from
    available stores excluding the current one. The movable-item set is fixed,
    so reverse and forward proposal probabilities match. With one movable item
    only the single-item move is used. Each selected item moves in its entirety.

    Temperature follows T(k) = T0 * (Tend/T0)**(k/(K-1)), k=0,...,K-1.
    For K=1 only T0 is used; K=0 returns the initial state. Runtime includes
    initialization and optimization, and excludes file loading and output.
    """
    started = time.perf_counter()
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 0:
        raise ValueError("iterations must be an integer >= 0")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    for name, temperature in (("start_temp_cents", start_temp_cents), ("end_temp_cents", end_temp_cents)):
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature) or temperature <= 0:
            raise ValueError(f"{name} must be finite and > 0")
    if end_temp_cents > start_temp_cents:
        raise ValueError("end_temp_cents must not exceed start_temp_cents")

    rng = random.Random(seed)
    current = list(cheapest_assignment(problem) if initial is None else initial)
    validate_assignment(problem, current)
    available = [tuple(j for j, price in enumerate(item.prices_cents) if price is not None) for item in problem.items]
    movable = tuple(index for index, choices in enumerate(available) if len(choices) > 1)
    costs = [tuple(None if price is None else price * item.quantity for price in item.prices_cents) for item in problem.items]
    subtotals = [0] * len(problem.stores)
    counts = [0] * len(problem.stores)
    for index, store_index in enumerate(current):
        cost = costs[index][store_index]
        assert cost is not None
        subtotals[store_index] += cost
        counts[store_index] += 1
    current_total = sum(subtotals) + sum(delivery_cost(store, subtotals[j], counts[j]) for j, store in enumerate(problem.stores))
    best = tuple(current)
    best_total = current_total
    accepted = improvements = completed = 0
    # Log interpolation avoids underflow when valid temperatures have extreme ratios.
    log_start = math.log(start_temp_cents)
    log_end = math.log(end_temp_cents)

    for step in range(iterations if movable else 0):
        completed += 1
        if len(movable) >= 2 and rng.random() < 0.25:
            chosen = rng.sample(movable, 2)
        else:
            chosen = [rng.choice(movable)]

        changes: list[tuple[int, int]] = []
        subtotal_deltas: dict[int, int] = {}
        count_deltas: dict[int, int] = {}
        for index in chosen:
            old = current[index]
            new = rng.choice(tuple(j for j in available[index] if j != old))
            old_cost, new_cost = costs[index][old], costs[index][new]
            assert old_cost is not None and new_cost is not None
            changes.append((index, new))
            subtotal_deltas[old] = subtotal_deltas.get(old, 0) - old_cost
            subtotal_deltas[new] = subtotal_deltas.get(new, 0) + new_cost
            count_deltas[old] = count_deltas.get(old, 0) - 1
            count_deltas[new] = count_deltas.get(new, 0) + 1

        delta = 0
        for j, subtotal_delta in subtotal_deltas.items():
            old_delivery = delivery_cost(problem.stores[j], subtotals[j], counts[j])
            new_delivery = delivery_cost(problem.stores[j], subtotals[j] + subtotal_delta, counts[j] + count_deltas[j])
            delta += subtotal_delta + new_delivery - old_delivery
        fraction = step / (iterations - 1) if iterations > 1 else 0.0
        temperature = math.exp(log_start + (log_end - log_start) * fraction)
        if delta <= 0 or rng.random() < math.exp(-delta / temperature):
            accepted += 1
            for index, new in changes:
                current[index] = new
            for j, subtotal_delta in subtotal_deltas.items():
                subtotals[j] += subtotal_delta
                counts[j] += count_deltas[j]
            current_total += delta
            if current_total < best_total:
                improvements += 1
                best_total = current_total
                best = tuple(current)

    return AnnealingResult(best, best_total, time.perf_counter() - started, completed, accepted, improvements)
