"""Boundary checks and an independent exhaustive oracle for tiny problems."""

import itertools
import io
import json
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from shopping_sa.exact import exact_solve
from shopping_sa.model import Item, Problem, Store
from shopping_sa.model import cheapest_assignment, evaluate, load_problem, state_count


ROOT = Path(__file__).resolve().parents[1]


def independent_cost(problem, assignment):
    """Deliberately does not call any production evaluator or helper."""
    total = 0
    for shop_id, shop in enumerate(problem.stores):
        purchased = [item for item, chosen in zip(problem.items, assignment)
                     if chosen == shop_id]
        if purchased:
            subtotal = sum(item.quantity * item.prices_cents[shop_id]
                           for item in purchased)
            total += subtotal
            if (shop.free_delivery_threshold_cents is None
                    or subtotal < shop.free_delivery_threshold_cents):
                total += shop.delivery_cents
    return total


def independent_brute_force(problem):
    domains = [tuple(j for j, p in enumerate(item.prices_cents) if p is not None)
               for item in problem.items]
    return min((independent_cost(problem, a), a)
               for a in itertools.product(*domains))


class EvaluationTests(unittest.TestCase):
    def test_free_delivery_at_exact_threshold(self):
        problem = Problem("exact threshold", (Store("A", 399, 1000),),
                          (Item("a", 2, (500,)),))
        self.assertEqual(evaluate(problem, (0,)), 1000)

    def test_delivery_one_cent_below_threshold(self):
        problem = Problem("below threshold", (Store("A", 399, 1000),),
                          (Item("a", 1, (999,)),))
        self.assertEqual(evaluate(problem, (0,)), 1398)

    def test_above_threshold_and_quantity(self):
        problem = Problem("quantity", (Store("A", 399, 1000),),
                          (Item("a", 3, (400,)),))
        self.assertEqual(evaluate(problem, (0,)), 1200)

    def test_unused_shop_has_no_delivery_charge(self):
        problem = Problem("unused", (Store("A", 250), Store("B", 999)),
                          (Item("a", 1, (100, 90)),))
        self.assertEqual(evaluate(problem, (0,)), 350)

    def test_no_threshold_always_charges_used_shop(self):
        problem = Problem("no free", (Store("A", 500, None),),
                          (Item("a", 20, (1000,)),))
        self.assertEqual(evaluate(problem, (0,)), 20500)

    def test_zero_price_item_still_uses_shop(self):
        problem = Problem("zero", (Store("A", 500, None),),
                          (Item("a", 1, (0,)),))
        self.assertEqual(evaluate(problem, (0,)), 500)

    def test_zero_threshold_waives_delivery_for_free_item(self):
        problem = Problem("zero threshold", (Store("A", 500, 0),),
                          (Item("a", 1, (0,)),))
        self.assertEqual(evaluate(problem, (0,)), 0)

    def test_delivery_charged_once_per_used_shop(self):
        problem = Problem("once", (Store("A", 399),),
                          (Item("a", 1, (100,)), Item("b", 2, (200,))))
        self.assertEqual(evaluate(problem, (0, 0)), 899)

    def test_shipping_makes_cheapest_items_suboptimal(self):
        problem = load_problem(ROOT / "instances/edge_cases/shipping_barrier.json")
        self.assertEqual(tuple(cheapest_assignment(problem)), (0, 1))
        self.assertEqual(evaluate(problem, (0, 1)), 3200)
        self.assertEqual(evaluate(problem, (0, 0)), 2200)
        self.assertEqual(exact_solve(problem).total_cents, 2200)

    def test_forced_and_zero_fixture(self):
        problem = load_problem(ROOT / "instances/edge_cases/forced_and_zero.json")
        self.assertEqual(state_count(problem), 1)
        self.assertEqual(evaluate(problem, (0, 1)), 1500)
        self.assertEqual(exact_solve(problem).total_cents, 1500)

    def test_invalid_assignment_rejected(self):
        problem = Problem("unavailable", (Store("A", 200), Store("B", 300)),
                          (Item("a", 1, (100, None)),))
        for bad in ((), (0, 0), (-1,), (2,), (1,), (True,), (0.0,), ("0",)):
            with self.subTest(assignment=bad):
                with self.assertRaises((ValueError, TypeError)):
                    evaluate(problem, bad)

    def test_invalid_problem_data_rejected(self):
        valid_store = Store("A", 300)
        valid_item = Item("x", 1, (100,))
        bad_constructors = [
            lambda: Problem("bad", (), (valid_item,)),
            lambda: Problem("bad", (valid_store,), ()),
            lambda: Problem("", (valid_store,), (valid_item,)),
            lambda: Problem("bad", (Store("", 300),), (valid_item,)),
            lambda: Problem("bad", (Store("A", -1),), (valid_item,)),
            lambda: Problem("bad", (Store("A", True),), (valid_item,)),
            lambda: Problem("bad", (Store("A", 1.5),), (valid_item,)),
            lambda: Problem("bad", (Store("A", 100, -1),), (valid_item,)),
            lambda: Problem("bad", (Store("A", 100, True),), (valid_item,)),
            lambda: Problem("bad", (valid_store,), (Item("", 1, (100,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", 0, (100,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", -1, (100,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", True, (100,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", 1.1, (100,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", 1, (-1,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", 1, (True,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", 1, (100.0,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", 1, (None,)),)),
            lambda: Problem("bad", (valid_store,), (Item("x", 1, (100, 200)),)),
        ]
        for index, constructor in enumerate(bad_constructors):
            with self.subTest(case=index):
                with self.assertRaises((ValueError, TypeError)):
                    constructor()

    def test_loader_rejects_malformed_data(self):
        document = {
            "name": "bad", "stores": [{"name": "A", "delivery_cents": 100}],
            "items": [{"name": "x", "quantity": 1, "prices_cents": [True]}],
        }
        with patch.object(Path, "open", return_value=io.StringIO(json.dumps(document))):
            with self.assertRaises((ValueError, TypeError)):
                load_problem("invalid.json")


class ExactSolverTests(unittest.TestCase):
    def test_exact_matches_independent_oracle_random_tiny_instances(self):
        rng = random.Random(98273)
        for case in range(30):
            n, m = rng.randint(1, 6), rng.randint(1, 4)
            stores = tuple(Store(f"S{j}", rng.randint(0, 800),
                                 rng.choice((None, 0, 1000, 2000))) for j in range(m))
            items = []
            for i in range(n):
                prices = [rng.randint(0, 900) if rng.random() > 0.3 else None
                          for _ in range(m)]
                prices[rng.randrange(m)] = rng.randint(0, 900)
                items.append(Item(f"P{i}", rng.randint(1, 3), tuple(prices)))
            problem = Problem(f"random-{case}", stores, tuple(items))
            expected, _ = independent_brute_force(problem)
            actual = exact_solve(problem)
            with self.subTest(case=case):
                self.assertEqual(actual.total_cents, expected)
                self.assertEqual(independent_cost(problem, actual.assignment), expected)
                self.assertEqual(evaluate(problem, actual.assignment), expected)
                self.assertEqual(actual.states_checked, state_count(problem))
                self.assertGreaterEqual(actual.elapsed_seconds, 0)

    def test_exact_state_limit(self):
        problem = load_problem(ROOT / "instances/edge_cases/shipping_barrier.json")
        self.assertEqual(state_count(problem), 4)
        with self.assertRaises((ValueError, RuntimeError)):
            exact_solve(problem, max_states=3)
        self.assertEqual(exact_solve(problem, max_states=4).states_checked, 4)

    def test_main_instances_cover_requested_sizes_and_metadata(self):
        expected = {(6, 3), (8, 4), (10, 4), (12, 3), (20, 5), (40, 6), (80, 8), (120, 10)}
        observed = set()
        for path in sorted((ROOT / "instances").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            problem = load_problem(path)
            observed.add((len(problem.items), len(problem.stores)))
            self.assertEqual(state_count(problem), data["metadata"]["feasible_assignments"])
            self.assertEqual(evaluate(problem, cheapest_assignment(problem)),
                             independent_cost(problem, cheapest_assignment(problem)))
        self.assertEqual(observed, expected)


if __name__ == "__main__":
    unittest.main()
