"""Command-line interface: python -m shopping_sa instances/example.json --exact."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .exact import exact_solve
from .model import breakdown, cheapest_assignment, evaluate, load_problem, state_count
from .solver import anneal


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize shopping assignments with simulated annealing.")
    parser.add_argument("instance", help="Path to a JSON instance")
    parser.add_argument("--iterations", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--start-temp-cents", type=float, default=2000.0)
    parser.add_argument("--end-temp-cents", type=float, default=1.0)
    parser.add_argument("--exact", action="store_true", help="Also enumerate every feasible assignment")
    parser.add_argument("--max-states", type=int, default=2_000_000)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()
    try:
        problem = load_problem(args.instance)
        result = anneal(problem, seed=args.seed, iterations=args.iterations, start_temp_cents=args.start_temp_cents, end_temp_cents=args.end_temp_cents)
        exact = exact_solve(problem, max_states=args.max_states) if args.exact else None
    except (OSError, ValueError) as error:
        parser.error(str(error))
    payload = {
        "problem": problem.name,
        "state_count": state_count(problem),
        "seed": args.seed,
        "initial_total_cents": evaluate(problem, cheapest_assignment(problem)),
        "annealing": asdict(result),
        "stores": breakdown(problem, result.assignment),
        "items": [{"item": item.name, "quantity": item.quantity, "store": problem.stores[j].name} for item, j in zip(problem.items, result.assignment)],
        "exact": asdict(exact) if exact is not None else None,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"Problem: {problem.name}")
    print(f"Feasible assignments: {payload['state_count']}")
    print(f"Initial cost: EUR {payload['initial_total_cents'] / 100:.2f}")
    print(f"SA best cost: EUR {result.total_cents / 100:.2f}")
    print(f"Runtime: {result.elapsed_seconds:.6f} s; iterations: {result.iterations}; seed: {args.seed}")
    for row in payload["stores"]:
        if row["item_count"]:
            print(f"  {row['store']}: products EUR {row['products_cents'] / 100:.2f}, delivery EUR {row['delivery_cents'] / 100:.2f}")
    for row in payload["items"]:
        print(f"  {row['item']} x{row['quantity']} -> {row['store']}")
    if exact is not None:
        difference = result.total_cents - exact.total_cents
        gap = f"{100 * difference / exact.total_cents:.3f}%" if exact.total_cents else ("0.000%" if difference == 0 else "undefined (zero optimum)")
        print(f"Exact optimum: EUR {exact.total_cents / 100:.2f}; gap: {gap}; enumeration: {exact.elapsed_seconds:.6f} s")


if __name__ == "__main__":
    main()
