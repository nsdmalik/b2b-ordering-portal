"""Local demonstration server. Demo role selection is not production authentication."""

import argparse
import json
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from orders import Store, OrderError, Forbidden, Conflict

ROOT = Path(__file__).parent


def make_handler(store, port):
    sessions = {}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, data, content_type="application/json", cookie=None):
            body = (
                json.dumps(data).encode()
                if content_type == "application/json"
                else data
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def actor(self):
            c = SimpleCookie()
            c.load(self.headers.get("Cookie", ""))
            actor = sessions.get(c["session"].value) if "session" in c else None
            if actor is None:
                raise Forbidden("Select a demo account")
            return actor

        def handle_request(self, post=False):
            try:
                host = self.headers.get("Host", "")
                if host not in hosts:
                    raise Forbidden("Local host required")
                if post and self.headers.get("Origin") != f"http://{host}":
                    raise Forbidden("Same-origin requests required")
                if not post and self.path in ("/", "/app.js", "/style.css"):
                    name = {
                        "/": "index.html",
                        "/app.js": "app.js",
                        "/style.css": "style.css",
                    }[self.path]
                    return self.reply(
                        200,
                        (ROOT / name).read_bytes(),
                        {
                            "index.html": "text/html; charset=utf-8",
                            "app.js": "text/javascript",
                            "style.css": "text/css",
                        }[name],
                    )
                if not post:
                    actor = self.actor()
                    if self.path == "/api/state":
                        return self.reply(
                            200,
                            {
                                "actor": actor,
                                "catalog": store.catalog(actor),
                                "orders": store.list_orders(actor),
                            },
                        )
                else:
                    if (
                        self.headers.get("Content-Type", "").split(";")[0]
                        != "application/json"
                    ):
                        raise OrderError("Use application/json")
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 16384:
                        raise OrderError("Request body must be 1 to 16384 bytes")
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise OrderError("Expected a JSON object")
                    if self.path == "/api/session":
                        actor = data.get("actor")
                        store.actor(actor)
                        if len(sessions) >= 1000:
                            sessions.clear()
                        token = secrets.token_urlsafe(32)
                        sessions[token] = actor
                        return self.reply(
                            200,
                            {"actor": actor},
                            cookie=f"session={token}; HttpOnly; SameSite=Strict; Path=/",
                        )
                    actor = self.actor()
                    if self.path == "/api/orders":
                        return self.reply(
                            200,
                            store.submit(
                                actor,
                                data.get("lines"),
                                data.get("id"),
                                data.get("revision"),
                            ),
                        )
                    if self.path == "/api/config":
                        store.configure(actor, data)
                        return self.reply(200, {"ok": True})
                self.reply(404, {"error": "Not found"})
            except Forbidden as e:
                self.reply(403, {"error": str(e)})
            except Conflict as e:
                self.reply(409, {"error": str(e)})
            except (OrderError, ValueError, TypeError) as e:
                self.reply(400, {"error": str(e)})

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request(True)

    return Handler


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8081)
    p.add_argument("--database", default="orders.sqlite3")
    a = p.parse_args()
    store = Store(a.database)
    with HTTPServer(("127.0.0.1", a.port), make_handler(store, a.port)) as server:
        print(f"Demo only: http://127.0.0.1:{a.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            store.close()
