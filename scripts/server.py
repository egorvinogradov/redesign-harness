#!/usr/bin/env python3
"""Loopback-only review server and timer. No third-party Python packages."""
import argparse
import fcntl
import json
import mimetypes
import os
import secrets
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from store import DEFAULT_HOME, Store
from supervisor import SKILL, Supervisor


def make_handler(store, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, payload, mime='application/json'):
            body = json.dumps(payload).encode() if mime == 'application/json' else payload
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Local access only'})
            path = urlparse(self.path).path
            if path == '/api/state':
                return self.send(200, store.snapshot())
            if path == '/api/session':
                return self.send(200, {'token': token})
            if path == '/health':
                return self.send(200, {'ok': True, 'service': 'design-director'})
            if path.startswith('/assets/'):
                filename = path.removeprefix('/assets/')
                if '/' in filename or not filename.endswith('.png'):
                    return self.send(404, {'error': 'Missing image'})
                file = store.home / 'assets' / filename
            else:
                file = SKILL / 'assets' / {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}.get(path, 'missing')
            if not file.is_file():
                return self.send(404, {'error': 'Not found'})
            self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')

        def do_POST(self):
            allowed = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
            if not self.valid_host() or self.headers.get('Origin') not in allowed or self.headers.get('X-Review-Token') != token:
                return self.send(403, {'error': 'Local review session required'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size < 100_000:
                    raise ValueError('Request is too large or empty')
                data = json.loads(self.rfile.read(size))
                if self.path == '/api/control':
                    result = store.control(data)
                elif self.path == '/api/feedback':
                    result = store.add_feedback(data)
                elif self.path == '/api/viewed':
                    store.review(data['ids'], {'viewed': True})
                    result = {'ok': True}
                elif self.path == '/api/reviewed':
                    store.review(data['ids'], {'viewed': True, 'reviewed': True})
                    result = {'ok': True}
                else:
                    return self.send(404, {'error': 'Unknown action'})
                self.send(200, result)
            except (ValueError, KeyError, TypeError) as exc:
                self.send(400, {'error': str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME)
    parser.add_argument('--port', type=int, default=4317)
    parser.add_argument('--no-worker', action='store_true')
    args = parser.parse_args()
    store = Store(args.home)
    lock = (store.home / 'server.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(store, secrets.token_urlsafe(32)))
    server.daemon_threads = True
    supervisor = Supervisor(store)
    if not args.no_worker:
        supervisor.recover()
    stopped = threading.Event()

    def shutdown(*_):
        stopped.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'Design review: http://127.0.0.1:{args.port}', flush=True)
    try:
        while not stopped.wait(1):
            if not args.no_worker:
                try:
                    supervisor.tick()
                except Exception as exc:
                    supervisor.close()
                    store.update_settings({'paused': True, 'lastError': str(exc)})
                    store.event('Director paused after an internal error: ' + str(exc), 'error')
    finally:
        supervisor.close()
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
