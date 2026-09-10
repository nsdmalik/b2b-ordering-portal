import unittest
from orders import Store, OrderError, Forbidden, Conflict


class OrdersTests(unittest.TestCase):
    def setUp(self):
        self.s = Store(":memory:")
        self.lines = [{"sku": "STUDIO-CASE", "quantity": 6}]

    def tearDown(self):
        self.s.close()

    def test_regions(self):
        ca = self.s.submit("north-ca", self.lines)
        us = self.s.submit("coast-us", self.lines)
        self.assertEqual((ca["currency"], ca["total"]), ("CAD", 14400))
        self.assertEqual((us["currency"], us["total"]), ("USD", 10800))

    def test_scoped_orders(self):
        self.s.submit("north-ca", self.lines)
        self.assertEqual(self.s.list_orders("coast-us"), [])
        self.assertEqual(len(self.s.list_orders("admin")), 1)

    def test_cross_account_revision_denied(self):
        o = self.s.submit("north-ca", self.lines)
        with self.assertRaises(Forbidden):
            self.s.submit("coast-us", self.lines, o["id"], 1)

    def test_stale_revision(self):
        o = self.s.submit("north-ca", self.lines)
        self.s.submit("north-ca", self.lines, o["id"], 1)
        with self.assertRaises(Conflict):
            self.s.submit("north-ca", self.lines, o["id"], 1)

    def test_case_packs(self):
        for qty in (1, 0, -6, True, 6.0, 10002):
            with self.subTest(qty=qty), self.assertRaises(OrderError):
                self.s.submit("north-ca", [{"sku": "STUDIO-CASE", "quantity": qty}])

    def test_untrusted_prices_rejected(self):
        with self.assertRaises(OrderError):
            self.s.submit(
                "north-ca", [{"sku": "STUDIO-CASE", "quantity": 6, "unit_cents": 1}]
            )

    def test_duplicates_rejected(self):
        with self.assertRaises(OrderError):
            self.s.submit("north-ca", self.lines * 2)

    def test_window_closed(self):
        self.s.configure("admin", {"open": False})
        with self.assertRaises(Conflict):
            self.s.submit("north-ca", self.lines)

    def test_buyer_cannot_configure(self):
        with self.assertRaises(Forbidden):
            self.s.configure("north-ca", {"open": False})

    def test_price_snapshot_and_revision_repricing(self):
        o = self.s.submit("north-ca", self.lines)
        self.s.configure("admin", {"sku": "STUDIO-CASE", "region": "CA", "cents": 3000})
        self.assertEqual(self.s.list_orders("north-ca")[0]["total"], 14400)
        revised = self.s.submit("north-ca", self.lines, o["id"], 1)
        self.assertEqual(revised["total"], 18000)
        events = self.s.db.execute(
            "SELECT payload FROM events WHERE kind='order.created'"
        ).fetchone()[0]
        self.assertIn("14400", events)

    def test_bad_line_rolls_back(self):
        with self.assertRaises(OrderError):
            self.s.submit("north-ca", self.lines + [{"sku": "NOPE", "quantity": 4}])
        self.assertEqual(self.s.list_orders("admin"), [])
        self.assertEqual(
            self.s.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0
        )

    def test_unknown_actor(self):
        with self.assertRaises(Forbidden):
            self.s.catalog("other")

    def test_admin_cannot_submit(self):
        with self.assertRaises(Forbidden):
            self.s.submit("admin", self.lines)

    def test_integer_revision_required(self):
        with self.assertRaises(OrderError):
            self.s.submit("north-ca", self.lines, True, True)


if __name__ == "__main__":
    unittest.main()
