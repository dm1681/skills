"""Machine-local monitoring metadata; registration never activates a process."""
from __future__ import annotations

import contextlib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

MAX_INSTANCES = 64


def endpoint(value: str) -> str:
    """Canonical numeric loopback origin: no DNS, credentials, paths or redirects."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if host == 'localhost':
            host = '127.0.0.1'
        address = ipaddress.ip_address(host)
        port = parsed.port
        if (parsed.scheme != 'http' or not address.is_loopback or
                (address.version == 6 and str(address) != '::1') or port is None
                or not 1 <= port <= 65535 or parsed.username is not None
                or parsed.password is not None or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment or any(c.isspace() for c in value)):
            raise ValueError
        host = f'[{address}]' if address.version == 6 else str(address)
        return f'http://{host}:{port}'
    except (TypeError, ValueError):
        raise ValueError('Endpoint must be an HTTP loopback origin with an explicit port') from None


def registry_path() -> Path:
    return Path(os.environ.get('SKILLS_SYMPHONY_REGISTRY', str(Path.home() / '.dm1681-symphony.json'))).expanduser().absolute()


def entry(project: str, address: str | None, name: str | None = None) -> dict:
    project = str(Path(project).expanduser().resolve())
    address = endpoint(address) if address is not None else None
    label = name or Path(project).name
    if not isinstance(label, str) or not 1 <= len(label) <= 120 or any(ord(c) < 32 for c in label):
        raise ValueError('Project display name must be 1–120 printable characters')
    # The endpoint identifies an instance; disabled projects have a path identity.
    identity = hashlib.sha256((address or 'disabled:' + project).encode()).hexdigest()[:24]
    return {'id': identity, 'project_path': project, 'name': label, 'endpoint': address}


def read(path: Path | None = None) -> list[dict]:
    path = path or registry_path()
    if not path.exists():
        return []
    try:
        if path.stat().st_size > 131072:
            raise ValueError
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema') != 1 or not isinstance(data.get('instances'), list) or len(data['instances']) > MAX_INSTANCES:
            raise ValueError
        result = {}
        for raw in data['instances']:
            item = entry(raw['project_path'], raw['endpoint'], raw['name'])
            mode = raw.get('mode', 'external')
            if mode not in ('external', 'configured'):
                raise ValueError
            item['mode'] = mode
            result.setdefault(item['id'], item)
        return list(result.values())
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError('Invalid Symphony registry; repair or select another registry file') from None


@contextlib.contextmanager
def locked(path: Path):
    if os.name != 'posix':
        raise ValueError('Symphony monitoring currently supports Linux/WSL only')
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path) + '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def register(project: str, address: str | None, name: str | None = None, *, path: Path | None = None, mode='external') -> dict:
    item = entry(project, address, name)
    if mode not in ('external', 'configured'):
        raise ValueError('Invalid registration mode')
    item['mode'] = mode
    path = path or registry_path()
    with locked(path):
        entries = read(path)
        # Same endpoint is idempotent. Same project may intentionally have multiple instances.
        entries = [old for old in entries if old['id'] != item['id'] and not
                   (old['project_path'] == item['project_path'] and old['endpoint'] is None)]
        entries.append(item)
        if len(entries) > MAX_INSTANCES:
            raise ValueError('Registry supports at most 64 instances')
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'schema': 1, 'instances': entries}, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return item


def register_config(config: dict, *, managed=False) -> dict:
    port = config['dashboard_port']
    return register(config['project_dir'], f'http://127.0.0.1:{port}' if port is not None else None,
                    mode='configured' if managed else 'external')
