# API and demo limitations

All POST requests require JSON and an `Origin` matching the local `Host`. The server binds to loopback and accepts only its localhost/127.0.0.1 host names. A demo session cookie identifies the selected account.

| Route | Request or result |
| --- | --- |
| `POST /api/session` | Select `north-ca`, `coast-us`, or `admin` with `{ "actor": "north-ca" }`. |
| `GET /api/state` | Returns the selected account's catalog, currency, preorder window and orders. |
| `POST /api/orders` | Submit `{ "lines": [{ "sku": "STUDIO-CASE", "quantity": 6 }] }`. Include `id` and `revision` to update an order. |
| `POST /api/config` | Operations only: `{ "open": false }` or `{ "sku": "STUDIO-CASE", "region": "CA", "cents": 3000 }`. |

## Order rules

The server resolves the buyer's region and reads prices from SQLite. Order lines accept only SKU and quantity. Each quantity must be a positive case-pack multiple, at most 10,000; duplicate SKUs are rejected. Totals use integer cents and an explicit currency.

Buyers can read and revise their own orders. Operations can read all orders and change the campaign configuration. A closed window rejects new submissions and revisions.

`BEGIN IMMEDIATE` covers the window check, revision check, order write and event write. An exception rolls the transaction back. SQLite serializes these writes; this is not a distributed implementation.

An update must supply the current revision number. An outdated revision returns HTTP 409. A revision recalculates every line using the current regional price. The order stores the new line-price snapshot, while the event trail retains prior submissions.

See [test_orders.py](../test_orders.py) for these rules and [test_server.py](../test_server.py) for HTTP checks.

## Before deploying anything based on this

Demo account selection is intentionally open. It is not production authentication, even though subsequent requests are scoped to the selected account. Sessions are in memory, have no expiry, and are cleared on restart. Cookies are HttpOnly and SameSite, but this localhost HTTP server is not configured for a public deployment.

A real service would need authenticated identities, server-managed account membership, TLS and secure cookies, session expiry, rate limits and monitoring. The event trail is maintained by the application, not tamper-proof storage.

There are no payments, tax calculations, inventory reservations, fulfillment integrations or automatic cutoff scheduler. Operations controls the preorder window manually. All supplied accounts, products and prices are fictional.
