"""Reproducible benchmark: ordinary SA, independent reference SA, exact search.

Only Python's standard library is used. From the repository root, run:
    python scripts/benchmark.py

Preserve the supplied results during a quick verification:
    python scripts/benchmark.py --runs 2 --iterations 1000 \
        --reference-runs 2 --reference-iterations 2000 --output-dir work/smoke

Timing comes from each solver's perf_counter measurement and excludes file I/O,
reference construction and result aggregation. All runs execute sequentially.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopping_sa.exact import exact_solve
from shopping_sa.model import cheapest_assignment, evaluate, load_problem, state_count
from shopping_sa.solver import anneal


RUN_FIELDS = (
    "instance", "seed", "iterations", "initialization", "cost_cents",
    "elapsed_seconds", "gap_percent", "reference_hit", "accepted_moves",
    "improvements",
)

SUMMARY_FIELDS = (
    "instance", "items", "stores", "feasible_assignments", "runs", "iterations",
    "lower_bound_cents", "baseline_cost_cents", "reference_cost_cents",
    "reference_kind", "best_cost_cents", "mean_cost_cents", "stdev_cost_cents",
    "worst_cost_cents", "best_gap_percent", "mean_gap_percent",
    "worst_gap_percent", "reference_hits", "reference_hit_rate_percent",
    "mean_seconds", "median_seconds", "stdev_seconds", "min_seconds",
    "max_seconds", "exact_seconds", "exact_states_checked",
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stdev(values: list[float] | list[int]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def gap(cost: int, reference: int) -> float:
    if reference == 0:
        # A nonzero objective relative to a zero optimum has no finite percent.
        return 0.0 if cost == 0 else math.inf
    return 100.0 * (cost - reference) / reference


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances-dir", type=Path, default=ROOT / "instances")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--runs", type=positive_int, default=20)
    parser.add_argument("--iterations", type=positive_int, default=20000)
    parser.add_argument("--reference-runs", type=positive_int, default=10)
    parser.add_argument("--reference-iterations", type=positive_int, default=100000)
    parser.add_argument("--max-exact-states", type=positive_int, default=2000000)
    parser.add_argument("--start-temp-cents", type=float, default=2000.0)
    parser.add_argument("--end-temp-cents", type=float, default=1.0)
    args = parser.parse_args()
    if not 0 < args.end_temp_cents <= args.start_temp_cents:
        parser.error("temperatures must satisfy 0 < end <= start")
    if not math.isfinite(args.start_temp_cents):
        parser.error("temperatures must be finite")
    return args


def pack_run(name: str, seed: int, initialization: str, result: object,
             problem: object) -> tuple[dict, dict]:
    """Re-evaluate every saved state rather than trusting cached solver costs."""
    assignment = list(result.assignment)
    observed = evaluate(problem, assignment)
    if observed != result.total_cents:
        raise AssertionError(f"{name}, seed {seed}: saved assignment cost mismatch")
    row = {
        "instance": name, "seed": seed, "iterations": result.iterations,
        "initialization": initialization, "cost_cents": observed,
        "elapsed_seconds": result.elapsed_seconds,
        "accepted_moves": result.accepted_moves,
        "improvements": result.improvements,
    }
    saved = {
        "seed": seed, "initialization": initialization,
        "assignment": assignment, "total_cents": observed,
    }
    return row, saved


def main() -> None:
    args = arguments()
    files = list(args.instances_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No JSON instances in {args.instances_dir}")
    # Sorting by size gives a legible table and excludes nested edge-case data.
    inputs = []
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        inputs.append((len(raw["items"]), len(raw["stores"]), path, raw))
    inputs.sort(key=lambda item: (item[0], item[1], item[2].name))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    started = timestamp()
    start_wall = time.perf_counter()
    ordinary_rows: list[dict] = []
    reference_rows: list[dict] = []
    summaries: list[dict] = []
    solutions: dict[str, dict] = {}
    input_metadata: list[dict] = []
    ordinary_seeds = list(range(args.runs))
    reference_seeds = list(range(1000, 1000 + args.reference_runs))
    params = {
        "start_temp_cents": args.start_temp_cents,
        "end_temp_cents": args.end_temp_cents,
    }

    for n, m, path, raw in inputs:
        name = raw["name"]
        if name in solutions:
            raise ValueError(f"Duplicate instance name: {name}")
        problem = load_problem(path)
        choices = [tuple(j for j, price in enumerate(item["prices_cents"])
                         if price is not None) for item in raw["items"]]
        states = state_count(problem)
        if states != math.prod(map(len, choices)):
            raise AssertionError(f"{name}: inconsistent search space size")
        lower_bound = sum(item["quantity"] * min(
            price for price in item["prices_cents"] if price is not None)
            for item in raw["items"])
        baseline = tuple(cheapest_assignment(problem))
        baseline_cost = evaluate(problem, baseline)
        print(f"{name}: {n} items, {m} stores, {states} feasible states", flush=True)

        exact = None
        if states <= args.max_exact_states:
            exact = exact_solve(problem, max_states=args.max_exact_states)
            if evaluate(problem, exact.assignment) != exact.total_cents:
                raise AssertionError(f"{name}: exact solution cost mismatch")
            if exact.states_checked != states:
                raise AssertionError(f"{name}: exact solver did not enumerate all states")

        local_rows = []
        ordinary_saved = []
        for seed in ordinary_seeds:
            result = anneal(problem, seed=seed, iterations=args.iterations, **params)
            row, saved = pack_run(name, seed, "cheapest", result, problem)
            local_rows.append(row)
            ordinary_saved.append(saved)

        local_ref_rows = []
        reference_saved = []
        if exact is None:
            for index, seed in enumerate(reference_seeds):
                # A separate RNG keeps initial-state generation reproducible
                # without consuming the annealing RNG's stream.
                if index % 2:
                    rng = random.Random(seed)
                    initial = tuple(rng.choice(available) for available in choices)
                    initialization = "random_feasible"
                else:
                    initial = baseline
                    initialization = "cheapest"
                result = anneal(problem, seed=seed,
                                iterations=args.reference_iterations,
                                initial=initial, **params)
                row, saved = pack_run(name, seed, initialization, result, problem)
                saved["initial_assignment"] = list(initial)
                local_ref_rows.append(row)
                reference_saved.append(saved)

        candidates = [{"assignment": list(baseline), "total_cents": baseline_cost,
                       "source": "cheapest_baseline"}]
        candidates.extend(dict(saved, source="ordinary_sa") for saved in ordinary_saved)
        candidates.extend(dict(saved, source="reference_sa") for saved in reference_saved)
        best_observed = min(candidates, key=lambda saved: saved["total_cents"])
        if exact is not None:
            if best_observed["total_cents"] < exact.total_cents:
                raise AssertionError(f"{name}: SA beat the claimed exact optimum")
            reference = exact.total_cents
            reference_kind = "exact_enumeration"
            best_reference = {
                "assignment": list(exact.assignment), "total_cents": reference,
                "source": "exact_enumeration",
            }
        else:
            best_reference = best_observed
            reference = best_reference["total_cents"]
            reference_kind = ("lower_bound_proven_optimum" if reference == lower_bound
                              else "best_observed_not_proven")
        if reference < lower_bound:
            raise AssertionError(f"{name}: reference falls below elementary lower bound")

        for row in local_rows + local_ref_rows:
            row["gap_percent"] = gap(row["cost_cents"], reference)
            row["reference_hit"] = int(row["cost_cents"] == reference)
        ordinary_rows.extend(local_rows)
        reference_rows.extend(local_ref_rows)
        costs = [row["cost_cents"] for row in local_rows]
        times = [row["elapsed_seconds"] for row in local_rows]
        gaps = [row["gap_percent"] for row in local_rows]
        hits = sum(row["reference_hit"] for row in local_rows)
        summaries.append({
            "instance": name, "items": n, "stores": m,
            "feasible_assignments": states, "runs": args.runs,
            "iterations": args.iterations, "lower_bound_cents": lower_bound,
            "baseline_cost_cents": baseline_cost, "reference_cost_cents": reference,
            "reference_kind": reference_kind, "best_cost_cents": min(costs),
            "mean_cost_cents": statistics.mean(costs), "stdev_cost_cents": stdev(costs),
            "worst_cost_cents": max(costs), "best_gap_percent": min(gaps),
            "mean_gap_percent": statistics.mean(gaps), "worst_gap_percent": max(gaps),
            "reference_hits": hits, "reference_hit_rate_percent": 100 * hits / args.runs,
            "mean_seconds": statistics.mean(times),
            "median_seconds": statistics.median(times), "stdev_seconds": stdev(times),
            "min_seconds": min(times), "max_seconds": max(times),
            "exact_seconds": exact.elapsed_seconds if exact else "",
            "exact_states_checked": exact.states_checked if exact else "",
        })
        solutions[name] = {
            "store_indexing": "Zero-based store index for each item in original input order.",
            "baseline": {"assignment": list(baseline), "total_cents": baseline_cost},
            "lower_bound_cents": lower_bound,
            "reference_kind": reference_kind, "best_reference": best_reference,
            "ordinary_runs": ordinary_saved, "reference_runs": reference_saved,
        }
        if exact is not None:
            solutions[name]["exact"] = {
                "assignment": list(exact.assignment), "total_cents": exact.total_cents,
                "elapsed_seconds": exact.elapsed_seconds,
                "states_checked": exact.states_checked,
            }
        input_metadata.append({
            "instance": name, "file": path.name, "sha256": digest(path),
            "items": n, "stores": m, "feasible_assignments": states,
        })
        print(f"  reference={reference / 100:.2f} EUR ({reference_kind}); "
              f"SA mean={statistics.mean(costs) / 100:.2f} EUR; "
              f"hits={hits}/{args.runs}; mean time={statistics.mean(times):.4f} s",
              flush=True)

    experiment_sources = sorted([
        *(ROOT / "shopping_sa").glob("*.py"),
        ROOT / "scripts" / "benchmark.py",
        ROOT / "scripts" / "generate_instances.py",
        *(ROOT / "tests").glob("*.py"),
    ])
    metadata = {
        "schema_version": 1,
        "started_at_utc": started, "completed_at_utc": timestamp(),
        "timestamp_source": "Host system clock, UTC; wall timestamps are not runtime measurements.",
        "total_wall_seconds": time.perf_counter() - start_wall,
        "environment": {
            "python": sys.version, "python_implementation": platform.python_implementation(),
            "python_executable": Path(sys.executable).name, "os": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
        },
        "parameters": {
            "ordinary_seeds": ordinary_seeds, "ordinary_iterations": args.iterations,
            "ordinary_initialization": "Cheapest available unit price for each item; deterministic ties.",
            "reference_seeds": reference_seeds,
            "reference_iterations": args.reference_iterations,
            "reference_initialization": "Alternating cheapest (even run index) and random feasible (odd run index).",
            "reference_initial_rng": "Separate random.Random(seed), independent of the SA RNG object.",
            "reference_scope": "Instances whose feasible state count exceeds max_exact_states only.",
            "max_exact_states": args.max_exact_states,
            **params,
        },
        "definitions": {
            "objective": "Integer euro cents: sum(quantity * chosen store unit price) + delivery for each used store whose subtotal is below its free delivery threshold, or which has no free delivery threshold.",
            "used_store": "At least one item assigned, including a zero-priced item; empty stores pay no delivery.",
            "reference": "Exact exhaustive optimum for small instances. Otherwise minimum across cheapest baseline, ordinary SA and separate higher-budget SA; not a proven optimum unless equal to the elementary lower bound.",
            "lower_bound": "Sum over items of quantity times cheapest available unit price; excludes all nonnegative delivery costs.",
            "gap_percent": "100 * (cost - reference) / reference. Zero against zero is 0; positive against zero is infinity.",
            "stdev": "Sample standard deviation (n-1 denominator); 0 when only one sample.",
            "runtime": "Elapsed seconds measured by solver-internal time.perf_counter; excludes file I/O, reference/exact computations from SA times, and aggregation.",
            "runtime_limitations": "Sequential single-process runs, without CPU affinity or control over operating-system background activity. Timings describe this machine and run only.",
            "units": "Integer EUR cents for individual objectives; sample means and standard deviations may have fractional cents.",
        },
        "inputs": input_metadata,
        "source_sha256": {
            str(path.relative_to(ROOT)).replace("\\", "/"): digest(path)
            for path in experiment_sources
        },
        "output_files": ["runs.csv", "reference_runs.csv", "summary.csv", "solutions.json", "metadata.json"],
    }
    write_csv(args.output_dir / "runs.csv", RUN_FIELDS, ordinary_rows)
    write_csv(args.output_dir / "reference_runs.csv", RUN_FIELDS, reference_rows)
    write_csv(args.output_dir / "summary.csv", SUMMARY_FIELDS, summaries)
    write_json(args.output_dir / "solutions.json", solutions)
    write_json(args.output_dir / "metadata.json", metadata)
    print(f"Saved {len(ordinary_rows)} ordinary runs and {len(reference_rows)} "
          f"reference runs to {args.output_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
