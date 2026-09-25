"""Independent, loopback-only Symphony monitoring web entry point."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import hmac
from pathlib import Path

import symphony_registry as registry
from symphony_monitor import Monitor

ASSETS = Path(__file__).resolve().parent / 'templates' / 'symphony' / 'monitor'


def server(monitor, port, control=None):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log incoming paths, state or private upstream data.

        def allowed_host(self):
            return self.headers.get_all('Host', []) == [f'127.0.0.1:{self.server.server_port}'] or self.headers.get_all('Host', []) == [f'localhost:{self.server.server_port}']

        def do_GET(self):
            if not self.allowed_host():
                self.send_error(403)
                return
            if self.path == '/api/state':
                body = json.dumps({**monitor.snapshot(), 'csrf_token': token}, allow_nan=False).encode()
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
        def do_POST(self):
            origin = 'http://' + self.headers.get('Host', '')
            if (not self.allowed_host() or self.headers.get_all('Origin', []) != [origin] or
                    self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin') or
                    not hmac.compare_digest(self.headers.get('X-Symphony-CSRF', '').encode(), token.encode())):
                self.send_error(403)
                return
            if self.path != '/api/action' or control is None:
                self.send_error(404)
                return
            try:
                if self.headers.get_all('Content-Type', []) != ['application/json'] or self.headers.get('Transfer-Encoding'):
                    raise ValueError
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not 0 < int(lengths[0]) <= 4096:
                    raise ValueError
                self.connection.settimeout(5)
                payload = json.loads(self.rfile.read(int(lengths[0])))
            except (ValueError, OSError):
                self.send_error(400)
                return
            try:
                response = control.action(payload)
                code = 202
            except Exception:
                # Never echo configuration, subprocess diagnostics or request data.
                response = {'error': 'Action refused or could not be confirmed. Refresh process state; check readiness and ownership.'}
                code = 409
            body = json.dumps(response).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(path=None, *, port=8790, interval=5., timeout=2.):
    if not 1 <= port <= 65535:
        raise ValueError('Dashboard port must be between 1 and 65535')
    from symphony_lifecycle import Control
    control = Control(path)
    monitor = Monitor(path, interval=interval, timeout=timeout, control=control)
    try:
        httpd = server(monitor, port, control)
    except OSError:
        raise ValueError('Cannot bind dashboard port; choose another --port. No service was changed.') from None
    monitor.start()
    print(f'Symphony monitor: http://127.0.0.1:{port} (explicit Start/Stop controls; opening this dashboard never activates workers)', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        monitor.close()


def add_parsers(actions):
    parser = actions.add_parser('dashboard', help='machine-wide dashboard with explicit Start/Stop; opening it starts no workers')
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
    parser.add_argument('--confirm-stopped', action='store_true', help='attest the original launcher and all workers are stopped; enable Start without activation')
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
        import symphony_lifecycle as lifecycle
        import symphony_project
        if args.confirm_stopped:
            config = symphony_project.load(args.project_dir)
            expected = f"http://127.0.0.1:{config['dashboard_port']}" if config['dashboard_port'] is not None else None
            if address is not None:
                address = registry.endpoint(address)
            if address != expected:
                raise ValueError('Stopped registration must use the configured endpoint; reconcile configuration first')
            lifecycle.confirm_stopped(config)
        else:
            try:
                config = symphony_project.load(args.project_dir)
            except symphony_project.Error:
                config = None
            if config is not None:
                lifecycle.register_external(config)
        registry.register(str(args.project_dir), address, args.name, path=args.registry,
                          mode='configured' if args.confirm_stopped else 'external')
        print('Registered monitoring metadata; no process or workflow changed.')
    return 0


def dispatch(args):
    try:
        return _dispatch(args)
    except ValueError as exc:
        import install
        raise install.InstallError(str(exc)) from None
