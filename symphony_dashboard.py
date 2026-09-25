"""Independent, loopback-only Symphony monitoring web entry point."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

import symphony_registry as registry
from symphony_monitor import Monitor

ASSETS = Path(__file__).resolve().parent / 'templates' / 'symphony' / 'monitor'


def server(monitor, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log incoming paths, state or private upstream data.

        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                self.send_error(403)
                return
            if self.path == '/api/state':
                body = json.dumps(monitor.snapshot(), allow_nan=False).encode()
                content_type = 'application/json'
            elif self.path in ('/', '/app.js', '/style.css'):
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[self.path]
                body = (ASSETS / name).read_bytes()
                content_type = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript', '/style.css': 'text/css'}[self.path]
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(path=None, *, port=8790, interval=5., timeout=2.):
    if not 1 <= port <= 65535:
        raise ValueError('Dashboard port must be between 1 and 65535')
    monitor = Monitor(path, interval=interval, timeout=timeout)
    try:
        httpd = server(monitor, port)
    except OSError:
        raise ValueError('Cannot bind dashboard port; choose another --port. No service was changed.') from None
    monitor.start()
    print(f'Symphony monitor: http://127.0.0.1:{port} (read-only)', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        monitor.close()


def add_parsers(actions):
    parser = actions.add_parser('dashboard', help='read-only machine-wide web monitor; no workers started')
    parser.add_argument('--port', type=int, default=8790, help='monitor port (default 8790); never rebinds instances')
    parser.add_argument('--refresh', type=float, default=5, help='poll seconds (1–300)')
    parser.add_argument('--timeout', type=float, default=2, help='per-instance timeout seconds (0.1–30)')
    parser.add_argument('--registry', type=Path, help='machine-local registry override')
    parser.set_defaults(handler=dispatch)
    parser = actions.add_parser('register', help='register/import a local instance without starting or restarting it')
    parser.add_argument('--project-dir', type=Path, required=True)
    parser.add_argument('--name', help='project/repository display name (do not include secrets)')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--endpoint', help='external instance HTTP loopback origin, e.g. http://127.0.0.1:8788')
    group.add_argument('--disabled', action='store_true', help='record unavailable HTTP dashboard')
    parser.add_argument('--registry', type=Path)
    parser.set_defaults(handler=dispatch)


def _dispatch(args):
    if args.symphony_action == 'dashboard':
        serve(args.registry, port=args.port, interval=args.refresh, timeout=args.timeout)
    else:
        address = args.endpoint
        if address is None and not args.disabled:
            # Import only the endpoint metadata; never check readiness or run hooks.
            import symphony_project
            config = symphony_project.load(args.project_dir)
            port = config['dashboard_port']
            address = f'http://127.0.0.1:{port}' if port is not None else None
        registry.register(str(args.project_dir), address, args.name, path=args.registry)
        print('Registered monitoring metadata; no process or workflow changed.')
    return 0


def dispatch(args):
    try:
        return _dispatch(args)
    except ValueError as exc:
        import install
        raise install.InstallError(str(exc)) from None
