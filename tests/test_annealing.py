"""Behavioral tests for feasibility, cached cost correctness and reproducibility."""

import math
import random
import unittest
from pathlib import Path

from shopping_sa.model import Item, Problem, Store, cheapest_assignment, evaluate, load_problem
from shopping_sa.solver import anneal
from tests.test_model_and_exact import independent_brute_force, independent_cost


ROOT = Path(__file__).resolve().parents[1]


class AnnealingTests(unittest.TestCase):
    def setUp(self):
        self.problem = load_problem(ROOT / "instances/edge_cases/shipping_barrier.json")

    def test_zero_iterations_returns_given_initial(self):
        initial = [1, 1]
        result = anneal(self.problem, iterations=0, initial=initial)
        self.assertEqual(result.assignment, (1, 1))
        self.assertEqual(result.total_cents, 2200)
        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.accepted_moves, 0)
        self.assertEqual(result.improvements, 0)
        self.assertEqual(initial, [1, 1])

    def test_default_start_is_cheapest_assignment(self):
        result = anneal(self.problem, iterations=0)
        self.assertEqual(result.assignment, cheapest_assignment(self.problem))
        self.assertEqual(result.total_cents, 3200)

    def test_best_includes_initial_even_at_high_temperature(self):
        for seed in range(6):
            result = anneal(self.problem, seed=seed, iterations=100,
                            start_temp_cents=1_000_000,
                            end_temp_cents=1_000_000, initial=(0, 0))
            self.assertEqual(result.total_cents, 2200)
            self.assertEqual(independent_cost(self.problem, result.assignment), 2200)

    def test_seed_reproduces_assignment_cost_and_counters(self):
        problem = load_problem(ROOT / "instances/small_10x04.json")
        first = anneal(problem, seed=371, iterations=1000)
        second = anneal(problem, seed=371, iterations=1000)
        for field in ("assignment", "total_cents", "iterations", "accepted_moves", "improvements"):
            self.assertEqual(getattr(first, field), getattr(second, field))

    def test_global_random_generator_is_not_changed(self):
        before = random.getstate()
        anneal(self.problem, seed=12, iterations=50)
        self.assertEqual(random.getstate(), before)

    def test_no_movable_item_returns_without_proposals(self):
        problem = load_problem(ROOT / "instances/edge_cases/forced_and_zero.json")
        result = anneal(problem, iterations=1000)
        self.assertEqual(result.assignment, (0, 1))
        self.assertEqual(result.total_cents, 1500)
        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.accepted_moves, 0)

    def test_one_movable_item(self):
        problem = Problem("one movable", (Store("A", 0), Store("B", 0)),
                          (Item("fixed", 1, (100, None)), Item("movable", 1, (200, 100))))
        result = anneal(problem, seed=7, iterations=100)
        self.assertEqual(result.total_cents, 200)
        self.assertEqual(result.assignment, (0, 1))
        self.assertEqual(result.iterations, 100)

    def test_one_iteration_is_valid(self):
        result = anneal(self.problem, seed=1, iterations=1)
        self.assertEqual(result.iterations, 1)
        self.assertEqual(result.total_cents, independent_cost(self.problem, result.assignment))

    def test_invalid_parameters_rejected(self):
        bad_arguments = [
            {"iterations": -1}, {"iterations": 1.5}, {"iterations": True},
            {"start_temp_cents": 0}, {"start_temp_cents": -1},
            {"end_temp_cents": 0}, {"end_temp_cents": -1},
            {"start_temp_cents": math.inf}, {"end_temp_cents": math.nan},
            {"start_temp_cents": True}, {"end_temp_cents": True},
            {"start_temp_cents": 1, "end_temp_cents": 2},
            {"seed": 1.5}, {"seed": True},
            {"initial": ()}, {"initial": (-1, 0)},
        ]
        for arguments in bad_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises((ValueError, TypeError)):
                    anneal(self.problem, **arguments)

    def test_unavailable_initial_assignment_rejected(self):
        problem = load_problem(ROOT / "instances/edge_cases/forced_and_zero.json")
        with self.assertRaises((ValueError, TypeError)):
            anneal(problem, initial=(1, 0))

    def test_extreme_finite_temperature_range(self):
        result = anneal(self.problem, iterations=10, start_temp_cents=1e300,
                        end_temp_cents=1e-300)
        self.assertEqual(result.total_cents, independent_cost(self.problem, result.assignment))

    def test_random_tiny_instances_match_independent_objective(self):
        rng = random.Random(41121)
        for case in range(12):
            n, m = rng.randint(2, 6), rng.randint(2, 4)
            stores = tuple(Store(f"S{j}", rng.randint(0, 500),
                                 rng.choice((None, 0, 500, 1000))) for j in range(m))
            items = []
            for i in range(n):
                prices = [rng.randint(0, 500) if rng.random() > .3 else None
                          for _ in range(m)]
                prices[rng.randrange(m)] = rng.randint(0, 500)
                items.append(Item(f"P{i}", rng.randint(1, 3), tuple(prices)))
            problem = Problem(f"case {case}", stores, tuple(items))
            lower_bound, _ = independent_brute_force(problem)
            initial_cost = independent_cost(problem, cheapest_assignment(problem))
            for seed in range(4):
                with self.subTest(case=case, seed=seed):
                    result = anneal(problem, seed=seed, iterations=250)
                    self.assertEqual(result.total_cents, independent_cost(problem, result.assignment))
                    self.assertEqual(result.total_cents, evaluate(problem, result.assignment))
                    self.assertGreaterEqual(result.total_cents, lower_bound)
                    self.assertLessEqual(result.total_cents, initial_cost)
                    self.assertGreaterEqual(result.elapsed_seconds, 0)
                    self.assertLessEqual(result.accepted_moves, result.iterations)
                    self.assertLessEqual(result.improvements, result.accepted_moves)

    def test_every_main_instance_has_feasible_non_worsening_result(self):
        for path in sorted((ROOT / "instances").glob("*.json")):
            problem = load_problem(path)
            initial_cost = independent_cost(problem, cheapest_assignment(problem))
            for seed in (0, 19):
                with self.subTest(instance=problem.name, seed=seed):
                    result = anneal(problem, seed=seed, iterations=250)
                    self.assertEqual(result.total_cents, independent_cost(problem, result.assignment))
                    self.assertEqual(result.total_cents, evaluate(problem, result.assignment))
                    self.assertLessEqual(result.total_cents, initial_cost)
                    self.assertEqual(result.iterations, 250)


if __name__ == "__main__":
    unittest.main()
