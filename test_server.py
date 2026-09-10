import http.client
import json
import queue
import threading
import unittest
from http.server import HTTPServer
from orders import Store
from server import make_handler


class HTTPTests(unittest.TestCase):
    def setUp(self):
        ready = queue.Queue()

        def serve():
            store = Store(":memory:")
            server = HTTPServer(("127.0.0.1", 0), make_handler(store, 0))
            server.RequestHandlerClass = make_handler(store, server.server_port)
            ready.put(server)
            server.serve_forever(poll_interval=0.01)
            store.close()
            server.server_close()

        self.thread = threading.Thread(target=serve)
        self.thread.start()
        self.server = ready.get(timeout=5)
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(5)

    def request(self, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
            **(headers or {}),
        }
        c.request(
            "POST" if body is not None else "GET",
            path,
            json.dumps(body) if body is not None else None,
            h,
        )
        r = c.getresponse()
        result = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return result

    def test_session_and_order(self):
        s, h, _ = self.request("/api/session", {"actor": "north-ca"})
        self.assertEqual(s, 200)
        cookie = h["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", h["Set-Cookie"])
        self.assertIn("SameSite=Strict", h["Set-Cookie"])
        s, _, b = self.request(
            "/api/orders",
            {"lines": [{"sku": "FIELD-KIT", "quantity": 4}]},
            {"Cookie": cookie},
        )
        self.assertEqual(s, 200)
        self.assertEqual(json.loads(b)["total"], 14400)

    def test_foreign_origin_rejected(self):
        self.assertEqual(
            self.request(
                "/api/session", {"actor": "admin"}, {"Origin": "https://example.com"}
            )[0],
            403,
        )

    def test_foreign_host_rejected(self):
        self.assertEqual(self.request("/", headers={"Host": "example.com"})[0], 403)

    def test_no_session(self):
        self.assertEqual(self.request("/api/state")[0], 403)

    def test_static_allowlist(self):
        self.assertEqual(self.request("/orders.sqlite3")[0], 403)

    def test_invalid_json_shape(self):
        self.assertEqual(self.request("/api/session", [])[0], 400)

    def test_index_headers(self):
        s, h, b = self.request("/")
        self.assertEqual(s, 200)
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertIn(b"FIELDWORK", b)


if __name__ == "__main__":
    unittest.main()
