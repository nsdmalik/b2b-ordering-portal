# B2B Ordering Portal

A small Python and SQLite app for trying out regional pricing and order revisions. Buyers can submit case quantities and revise their orders. Operations can change prices and close the preorder window.

It uses fictional Canadian and US accounts. The account selector is for the demo, not a real login system. For a React, Node.js and PostgreSQL implementation of related ordering problems, see [Orderdesk](https://github.com/nsdmalik/commerce-orderdesk).

## Start it

Python 3.11 or later. No dependencies or cloud accounts are needed.

```sh
python3 server.py
```

Open http://127.0.0.1:8081. Choose **North Supply** and submit six Studio storage cases: the initial total is CAD 144.00. Switch to **Coast Supply** to see US prices, or **Operations** to review orders and close the window.

Data stays in `orders.sqlite3` between runs. Use `--database another.sqlite3` for a separate demo or `--port 8082` for another port. Keep this demo on localhost; account selection lets anyone using it choose the Operations role.

## Try editing the same order twice

1. Submit an order as North Supply.
2. Open it in two tabs and select **Revise** in both.
3. Save a change in the first tab, then save from the second.

The second save returns a conflict because its revision is out of date. Refresh the order before trying again.

There is another deliberate rule here: revising an order uses today's regional prices. The interface says so before saving. The previous submission, including its original prices, remains in the event trail. The order update and event are saved in one SQLite transaction so they cannot succeed independently.

## Read the code

- [orders.py](orders.py): pricing, case quantities, revision checks and persistence.
- [server.py](server.py): local HTTP API and demo sessions.
- [app.js](app.js): buyer and Operations interfaces.
- [API and limitations](docs/api.md): request formats, transaction behavior and what a real deployment would need.

Run the tests separately from the server:

```sh
python3 -m unittest -v
```

[MIT license](LICENSE). This is an independent reference project with no payments, inventory reservations or fulfillment integrations.
