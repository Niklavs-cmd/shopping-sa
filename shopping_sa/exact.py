"""Independent complete enumeration, intended only for small feasible state spaces."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .model import Problem, state_count


@dataclass(frozen=True)
class ExactResult:
    assignment: tuple[int, ...]
    total_cents: int
    elapsed_seconds: float
    states_checked: int


def exact_solve(problem: Problem, max_states: int = 2_000_000) -> ExactResult:
    """Check every feasible assignment; no pruning or optimization library is used.

    Store subtotals are updated while descending the enumeration tree. At each
    leaf the objective, including thresholds, is computed independently from
    the public evaluator and the annealing implementation.
    """
    started = time.perf_counter()
    if isinstance(max_states, bool) or not isinstance(max_states, int) or max_states < 1:
        raise ValueError("max_states must be an integer >= 1")
    number_of_states = state_count(problem)
    if number_of_states > max_states:
        raise ValueError(f"exact enumeration needs {number_of_states} states, exceeding limit {max_states}")
    choices = [tuple((j, price * item.quantity) for j, price in enumerate(item.prices_cents) if price is not None) for item in problem.items]
    assignment = [0] * len(problem.items)
    subtotals = [0] * len(problem.stores)
    counts = [0] * len(problem.stores)
    best_assignment: tuple[int, ...] | None = None
    best_cost: int | None = None
    checked = 0

    def visit(item_index: int) -> None:
        nonlocal best_assignment, best_cost, checked
        if item_index == len(problem.items):
            checked += 1
            total = 0
            for j, store in enumerate(problem.stores):
                if counts[j]:
                    total += subtotals[j]
                    threshold = store.free_delivery_threshold_cents
                    if threshold is None or subtotals[j] < threshold:
                        total += store.delivery_cents
            if best_cost is None or total < best_cost:
                best_cost = total
                best_assignment = tuple(assignment)
            return
        for store_index, cost in choices[item_index]:
            assignment[item_index] = store_index
            subtotals[store_index] += cost
            counts[store_index] += 1
            visit(item_index + 1)
            subtotals[store_index] -= cost
            counts[store_index] -= 1

    visit(0)
    assert best_assignment is not None and best_cost is not None
    return ExactResult(best_assignment, best_cost, time.perf_counter() - started, checked)
