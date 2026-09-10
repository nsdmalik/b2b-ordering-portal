"""Regional preorder rules and SQLite persistence. Monetary amounts use integer cents."""

import json
import sqlite3
from datetime import datetime, timezone

ACCOUNTS = {
    "north-ca": {"name": "North Supply", "region": "CA"},
    "coast-us": {"name": "Coast Supply", "region": "US"},
}
PRODUCTS = {
    "STUDIO-CASE": {
        "name": "Studio storage case",
        "pack": 6,
        "prices": {"CA": 2400, "US": 1800},
    },
    "FIELD-KIT": {
        "name": "Field sample kit",
        "pack": 4,
        "prices": {"CA": 3600, "US": 2700},
    },
}


class OrderError(ValueError):
    pass


class Conflict(OrderError):
    pass


class Forbidden(OrderError):
    pass


class Store:
    def __init__(self, path="orders.sqlite3"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS campaign(id INTEGER PRIMARY KEY, open INTEGER NOT NULL);
        INSERT OR IGNORE INTO campaign VALUES(1,1);
        CREATE TABLE IF NOT EXISTS prices(sku TEXT,region TEXT,cents INTEGER NOT NULL,PRIMARY KEY(sku,region));
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,account TEXT NOT NULL,revision INTEGER NOT NULL,currency TEXT NOT NULL,total INTEGER NOT NULL,lines TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL);
        """)
        with self.db:
            for sku, p in PRODUCTS.items():
                for region, cents in p["prices"].items():
                    self.db.execute(
                        "INSERT OR IGNORE INTO prices VALUES(?,?,?)",
                        (sku, region, cents),
                    )

    def close(self):
        self.db.close()

    def actor(self, actor):
        if actor not in ACCOUNTS and actor != "admin":
            raise Forbidden("Unknown demo account")

    def event(self, actor, kind, payload):
        self.db.execute(
            "INSERT INTO events(actor,kind,payload,created) VALUES(?,?,?,?)",
            (actor, kind, json.dumps(payload), datetime.now(timezone.utc).isoformat()),
        )

    def catalog(self, actor):
        self.actor(actor)
        region = ACCOUNTS.get(actor, {"region": "CA"})["region"]
        return {
            "region": region,
            "currency": {"CA": "CAD", "US": "USD"}[region],
            "open": bool(self.db.execute("SELECT open FROM campaign").fetchone()[0]),
            "products": [
                {
                    "sku": s,
                    "name": p["name"],
                    "pack": p["pack"],
                    "cents": self.db.execute(
                        "SELECT cents FROM prices WHERE sku=? AND region=?", (s, region)
                    ).fetchone()[0],
                }
                for s, p in PRODUCTS.items()
            ],
        }

    def list_orders(self, actor):
        self.actor(actor)
        rows = (
            self.db.execute("SELECT * FROM orders ORDER BY id")
            if actor == "admin"
            else self.db.execute(
                "SELECT * FROM orders WHERE account=? ORDER BY id", (actor,)
            )
        )
        return [{**dict(r), "lines": json.loads(r["lines"])} for r in rows]

    def submit(self, actor, lines, order_id=None, revision=None):
        self.actor(actor)
        if actor == "admin":
            raise Forbidden("Choose a buyer account to place an order")
        if not isinstance(lines, list) or not 1 <= len(lines) <= 50:
            raise OrderError("Provide 1 to 50 order lines")
        if order_id is not None and (type(order_id) != int or type(revision) != int):
            raise OrderError("Order ID and revision must be integers")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if not self.db.execute("SELECT open FROM campaign").fetchone()[0]:
                raise Conflict("Preorder window is closed")
            old = None
            if order_id is not None:
                old = self.db.execute(
                    "SELECT * FROM orders WHERE id=?", (order_id,)
                ).fetchone()
                if old is None or old["account"] != actor:
                    raise Forbidden("Order is not available to this account")
                if old["revision"] != revision:
                    raise Conflict("Order changed. Reload before revising it")
            cat = self.catalog(actor)
            prices = {p["sku"]: p for p in cat["products"]}
            saved = []
            seen = set()
            for line in lines:
                if not isinstance(line, dict) or set(line) != {"sku", "quantity"}:
                    raise OrderError("Lines accept only sku and quantity")
                sku = line["sku"]
                qty = line["quantity"]
                if not isinstance(sku, str) or sku not in prices or sku in seen:
                    raise OrderError("Unknown or duplicate SKU")
                p = prices[sku]
                if type(qty) != int or not 0 < qty <= 10000 or qty % p["pack"]:
                    raise OrderError(
                        "Quantity must be a positive case-pack multiple, at most 10000"
                    )
                seen.add(sku)
                saved.append(
                    {
                        "sku": sku,
                        "quantity": qty,
                        "unit_cents": p["cents"],
                        "line_cents": qty * p["cents"],
                    }
                )
            total = sum(x["line_cents"] for x in saved)
            version = old["revision"] + 1 if old else 1
            if old:
                self.db.execute(
                    "UPDATE orders SET revision=?,total=?,lines=? WHERE id=?",
                    (version, total, json.dumps(saved), order_id),
                )
            else:
                order_id = self.db.execute(
                    "INSERT INTO orders(account,revision,currency,total,lines) VALUES(?,?,?,?,?)",
                    (actor, version, cat["currency"], total, json.dumps(saved)),
                ).lastrowid
            self.event(
                actor,
                "order.revised" if old else "order.created",
                {
                    "order_id": order_id,
                    "revision": version,
                    "currency": cat["currency"],
                    "total": total,
                    "lines": saved,
                },
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return next(x for x in self.list_orders(actor) if x["id"] == order_id)

    def configure(self, actor, change):
        self.actor(actor)
        if actor != "admin":
            raise Forbidden("Administrator role required")
        if not isinstance(change, dict):
            raise OrderError("Expected a configuration object")
        with self.db:
            if set(change) == {"open"} and type(change["open"]) == bool:
                self.db.execute("UPDATE campaign SET open=?", (int(change["open"]),))
            elif set(change) == {"sku", "region", "cents"}:
                if (
                    not isinstance(change["sku"], str)
                    or change["sku"] not in PRODUCTS
                    or change["region"] not in ("CA", "US")
                    or type(change["cents"]) != int
                    or not 0 < change["cents"] <= 1000000
                ):
                    raise OrderError("Invalid regional price")
                self.db.execute(
                    "UPDATE prices SET cents=? WHERE sku=? AND region=?",
                    (change["cents"], change["sku"], change["region"]),
                )
            else:
                raise OrderError("Unsupported configuration change")
            self.event(actor, "campaign.configured", change)
