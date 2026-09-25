"""Linear app credentials and an authenticated loopback gateway for Symphony.

The gateway keeps expiring app tokens out of workers and renews without restarting
active work. It forwards only to Linear; it never falls back to personal auth.
"""
from __future__ import annotations

import argparse
import contextlib
import getpass
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPHQL = "https://api.linear.app/graphql"
TOKEN_URL = "https://api.linear.app/oauth/token"
DEFAULT_FILE = Path.home() / ".config/symphony/linear-app.json"
MAX_BODY = 2 * 1024 * 1024


class Error(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, data, headers):
    """Bounded, fixed-destination requests; never follow credentials to redirects."""
    req = urllib.request.Request(url, data=data, headers=headers)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        response = opener.open(req, timeout=25)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise Error("Linear response exceeds the gateway limit")
        return response.code, body


def read_credentials(path):
    path = Path(path)
    if path.parent.is_symlink():
        raise Error("Credential directory must not be a symlink")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Error("Credentials must be a user-owned regular file with mode 0600")
        value = json.loads(stream.read(16385))
    if not isinstance(value, dict) or any(not isinstance(value.get(k), str) or not value[k].strip()
                                          for k in ("client_id", "client_secret", "organization_id")):
        raise Error("Missing app credentials or expected workspace identity")
    return value


def save_credentials(path, organization_id):
    if not sys.stdin.isatty():
        raise Error("Run save in a terminal; never pass secrets through chat or command arguments")
    path = Path(path).expanduser()
    if path.parent.is_symlink():
        raise Error("Credential directory must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.parent.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Error("Credential directory must be user-owned with mode 0700")
    value = {"client_id": getpass.getpass("Linear OAuth client ID (hidden): ").strip(),
             "client_secret": getpass.getpass("Linear OAuth client secret (hidden): ").strip(),
             "organization_id": organization_id}
    if not all(value.values()):
        raise Error("All fields are required; nothing saved")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
    print("App credentials saved privately; existing credentials were not replaced.")


class AppClient:
    def __init__(self, path):
        self.path = Path(path)
        self.token = None
        self.deadline = 0
        self.actor = None
        self.lock = threading.Lock()

    def authenticate(self):
        credentials = read_credentials(self.path)
        form = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "read,write",
                                      "client_id": credentials["client_id"],
                                      "client_secret": credentials["client_secret"]}).encode()
        status, body = request(TOKEN_URL, form, {"Content-Type": "application/x-www-form-urlencoded"})
        if status != 200:
            raise Error("Linear app authentication failed; check client-credentials access")
        data = json.loads(body)
        token, lifetime = data.get("access_token"), data.get("expires_in")
        if (not isinstance(token, str) or not token or any(c.isspace() for c in token)
                or data.get("token_type", "").lower() != "bearer"
                or type(lifetime) not in (int, float) or lifetime <= 120):
            raise Error("Linear returned invalid app token metadata")
        status, body = request(GRAPHQL, json.dumps({"query": "{ viewer { id name app organization { id } } }"}).encode(),
                               {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        value = json.loads(body)
        actor = value.get("data", {}).get("viewer")
        if (status != 200 or value.get("errors") or not isinstance(actor, dict)
                or actor.get("app") is not True
                or actor.get("organization", {}).get("id") != credentials["organization_id"]):
            raise Error("Refusing a non-app identity or unexpected Linear workspace")
        if self.actor and actor["id"] != self.actor["id"]:
            raise Error("Linear app identity changed; explicit restart required")
        self.actor = actor
        self.token = token
        self.deadline = time.monotonic() + lifetime - 60

    def graphql(self, body):
        # Serialize refresh and requests; this is a low-volume local controller.
        with self.lock:
            if not self.token or time.monotonic() >= self.deadline:
                self.authenticate()
            for attempt in range(2):
                status, response = request(GRAPHQL, body, {"Content-Type": "application/json",
                                                          "Authorization": "Bearer " + self.token})
                if status != 401 or attempt:
                    return status, response
                self.authenticate()
        raise Error("Unreachable authentication retry")


@contextlib.contextmanager
def gateway(client):
    secret = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Neither request bodies nor headers belong in service logs.

        def do_POST(self):
            self.connection.settimeout(30)
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if (self.path != "/graphql" or self.headers.get("Host") != expected_host
                    or self.headers.get("Origin") or self.headers.get("Transfer-Encoding")
                    or not hmac.compare_digest(self.headers.get("Authorization", ""), secret)):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.send_error(413)
                    return
                body = self.rfile.read(length)
                value = json.loads(body)
                if not isinstance(value, dict) or not isinstance(value.get("query"), str):
                    self.send_error(400)
                    return
                status, response = client.graphql(body)
            except (OSError, ValueError, Error):
                status, response = 502, b'{"errors":[{"message":"Linear app gateway unavailable"}]}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/graphql", secret
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextlib.contextmanager
def app_environment(path):
    client = AppClient(path)
    client.authenticate()
    with gateway(client) as (endpoint, secret):
        values = {"LINEAR_API_KEY": secret, "SYMPHONY_LINEAR_ENDPOINT": endpoint,
                  "SYMPHONY_LINEAR_APP": "1"}
        previous = {key: os.environ.get(key) for key in values}
        os.environ.update(values)
        try:
            yield endpoint, client
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def check_project(project, path=DEFAULT_FILE):
    import symphony_project as symphony
    with app_environment(path):
        return symphony.check(Path(project).resolve())


def run(project, path, accept_preview):
    import symphony_project as symphony
    if not accept_preview:
        raise Error("Start requires --accept-preview")
    project = Path(project).resolve()
    with app_environment(path) as (endpoint, client):
        print(f"Linear app verified: {client.actor['name']} ({client.actor['id']})", flush=True)
        problems = symphony.check(project)
        if problems:
            raise Error("Not ready: " + "; ".join(problems))
        config = symphony.load(project)
        import symphony_registry
        try:
            symphony_registry.register_config(config)
        except (OSError, ValueError):
            print("Warning: monitoring registration unavailable; import this endpoint later with skills symphony register.", file=sys.stderr)
        workflow = (project / ".symphony/WORKFLOW.md").read_text()
        _, frontmatter, prompt = workflow.split("---", 2)
        document = json.loads(frontmatter)
        document["tracker"]["endpoint"] = endpoint
        document["tracker"]["api_key"] = "$LINEAR_API_KEY"
        prompt = "\n\nUse only Symphony's injected linear_graphql tool for Linear. " + \
                 "It authenticates as the Symphony app. Never use personal connectors, " + \
                 "credentials, browser sessions or alternate identities for Linear.\n" + prompt
        # App token is never in a file or subprocess. The short-lived local key
        # only authenticates this process's loopback gateway.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", prefix="app-workflow-",
                                         dir=project / ".symphony") as stream:
            stream.write("---\n" + json.dumps(document, indent=2) + "\n---" + prompt)
            stream.flush()
            child = subprocess.Popen([str(symphony.runtime_binary(config)), symphony.PREVIEW_FLAG, stream.name],
                                     start_new_session=True)
            def forward(signum, frame):
                if child.poll() is None:
                    os.killpg(child.pid, signum)
            previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGTERM, signal.SIGINT)}
            try:
                return child.wait()
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=30)
                for sig, handler in previous.items():
                    signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("save", "check", "run"))
    parser.add_argument("--credentials", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--organization-id")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--accept-preview", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "save":
            if not args.organization_id:
                raise Error("--organization-id is required")
            save_credentials(args.credentials, args.organization_id)
        elif args.action == "check":
            client = AppClient(args.credentials)
            client.authenticate()
            print(json.dumps(client.actor))
        else:
            return run(args.project_dir, args.credentials, args.accept_preview)
    except (Error, OSError, ValueError, KeyError):
        # Third-party errors can echo secrets; only a generic message reaches logs.
        print("Linear app setup failed. Check the private credential file, app grant and workspace access.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
