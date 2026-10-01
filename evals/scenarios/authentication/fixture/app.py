"""Minimal server-rendered admin panel (stdlib only)."""

from http.server import BaseHTTPRequestHandler, HTTPServer

PAGE = b"<html><body><h1>admin-panel</h1><form action='/login'>sign-in form</form></body></html>"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(PAGE)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8080), Handler).serve_forever()
