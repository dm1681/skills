"""Linux repository lifecycle. systemd owns the cgroup; browsers own no processes.

Only named transient units created here are controllable. ExitType=cgroup keeps
ownership after the main process exits, including descendants that call setsid.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

import symphony_project as project
import symphony_registry as registry

class LaunchFailed(project.Error):
    pass


PREFIX = 'skills-symphony-'
PROPERTIES = ('LoadState', 'ActiveState', 'SubState', 'Description', 'Transient',
              'InvocationID', 'ExitType', 'KillMode', 'Restart', 'SendSIGKILL',
              'TimeoutStopUSec', 'Result', 'ControlGroup', 'MainPID')


def repository_identity(config):
    """Explicit canonical source, or common Git directory for local-only projects.

repository_host maps an SSH alias to its real source host. Never infer that
mapping from a repository basename or from DNS / user SSH configuration.
"""
    url = config.get('repo_url', '')
    host_override = config.get('repository_host', '')
    if host_override and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]*', host_override):
        raise project.Error('repository_host must be a canonical source hostname')
    if url and not url.startswith(('/', './', '../', 'file:')):
        if '://' not in url:
            match = re.fullmatch(r'(?:[A-Za-z0-9_-]+@)?([A-Za-z0-9.-]+):(.+)', url)
            if not match:
                raise project.Error('Repository URL is not a supported source identity')
            host, path = match.groups()
            scheme = 'ssh'
        else:
            parsed = urlsplit(url)
            if (parsed.scheme not in ('https', 'ssh') or not parsed.hostname or
                    parsed.password or parsed.query or parsed.fragment or
                    parsed.port is not None or (parsed.scheme == 'https' and parsed.username)):
                raise project.Error('Source identity requires HTTPS/SSH without credentials, query or port')
            host, path, scheme = parsed.hostname, parsed.path.lstrip('/'), parsed.scheme
        if host_override and scheme != 'ssh' and host_override.casefold() != host.casefold():
            raise project.Error('repository_host must match the HTTPS source host')
        host = host_override or ('github.com' if config.get('github_repo') else host)
        path = path.removesuffix('.git')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', path) or any(p in ('.', '..') for p in path.split('/')):
            raise project.Error('Source repository path is invalid')
        path = path.casefold() if host.casefold() == 'github.com' else path
        source = host.casefold() + '/' + path
    else:
        # Local paths share Git's common directory across worktrees and symlinks.
        root = Path(config['project_dir']).resolve()
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise project.Error('Local-only identity requires a Git repository')
        source = 'local:' + str(Path(result.stdout.strip()).resolve())
    return hashlib.sha256(source.encode()).hexdigest()


def state_root():
    # Test overrides must be shared by all launchers; unit identity never uses it.
    return Path(os.environ.get('SKILLS_SYMPHONY_STATE', str(Path.home() / '.local/state/dm1681-symphony'))).resolve()


def state_path(key):
    if not re.fullmatch('[a-f0-9]{64}', key):
        raise project.Error('Invalid repository identity')
    return state_root() / (key + '.json')


def read(key):
    path = state_path(key)
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 16384:
        raise project.Error('Invalid lifecycle record; controls disabled')
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, OSError):
        raise project.Error('Invalid lifecycle record; controls disabled') from None


def write(key, data):
    path = state_path(key)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=key + '.')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def unit(key):
    state_path(key)  # Validate before constructing arguments.
    return PREFIX + key + '.service'


class Manager:
    """Small systemd adapter; tests substitute a deterministic process manager."""
    def show(self, key):
        try:
            result = subprocess.run(['systemctl', '--user', 'show', unit(key),
                                     '--property=' + ','.join(PROPERTIES)], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            raise project.Error('User service manager unavailable; systemd 250+ user session is required') from None
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if values.get('LoadState') == 'not-found':
            return {}
        if result.returncode or not values.get('ActiveState'):
            raise project.Error('User service manager unavailable; verify the Linux user session')
        return values

    def launch(self, key, config, env):
        # No secrets in argv, unit Environment properties, registry, or journal.
        command = ['systemd-run', '--user', '--quiet', '--pipe', '--wait', '--collect',
                   '--unit=' + unit(key), '--description=Skills Symphony ' + key,
                   '--property=Type=exec', '--property=ExitType=cgroup',
                   '--property=KillMode=control-group', '--property=Restart=no',
                   '--property=SendSIGKILL=no', '--property=TimeoutStopSec=infinity',
                   '--property=TimeoutStartSec=300', '--property=UMask=0077',
                   '--property=WorkingDirectory=' + config['project_dir'],
                   sys.executable, str(Path(__file__).resolve()), key, config['project_dir'], str(state_root())]
        try:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            raise project.Error('Cannot execute systemd-run; no instance started') from None
        # communicate/reap independently of the HTTP request or CLI lifetime.
        payload = (json.dumps(dict(env)) + '\n').encode()
        delivered = threading.Event()
        def relay():
            try:
                proc.stdin.write(payload)
                proc.stdin.close()
                delivered.set()
                proc.wait()
            except (OSError, ValueError):
                pass
        threading.Thread(target=relay, daemon=True).start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            observed = self.show(key)
            if observed.get('InvocationID') and delivered.wait(.05):
                return
            if proc.poll() is not None:
                if not busy(observed):
                    raise LaunchFailed('Service start failed; verify systemd 250+ and runtime readiness')
                break
            time.sleep(.05)
        # Unit creation may still be pending. Caller retains an unresolved claim.
        raise project.Error('Service start could not be confirmed; launch remains reserved for reconciliation')

    def stop(self, key):
        try:
            result = subprocess.run(['systemctl', '--user', 'stop', '--no-block', unit(key)],
                                    capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            raise project.Error('Stop request could not be confirmed; repository remains reserved') from None
        if result.returncode:
            raise project.Error('Service manager refused Stop; repository remains reserved')


def owned(key, record, observed):
    return bool(record.get('invocation') and observed.get('InvocationID') == record['invocation'] and
                observed.get('Description') == 'Skills Symphony ' + key and observed.get('Transient') == 'yes' and
                all(observed.get(k) == v for k, v in {'ExitType': 'cgroup', 'KillMode': 'control-group',
                                                     'Restart': 'no', 'SendSIGKILL': 'no',
                                                     'TimeoutStopUSec': 'infinity'}.items()))


def busy(observed):
    return bool(observed) and observed.get('ActiveState') not in ('inactive', 'failed')


def port_available(config):
    port = config['dashboard_port']
    if port is not None:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                raise project.Error('Configured instance port is occupied; no service was rebound') from None


def describe(config, *, manager=None, health=None):
    manager = manager or Manager()
    key = repository_identity(config)
    record, observed = read(key), manager.show(key)
    state, start, stop = 'stopped', True, False
    error = record.get('error')
    if busy(observed):
        start = False
        stop = owned(key, record, observed)
        if not stop:
            state, error = 'unknown', 'Unmanaged or unverified service; use its original owner to stop it before registering as stopped'
        elif observed['ActiveState'] == 'deactivating':
            state = 'stopping'
            if time.time() - record.get('stop_at', time.time()) > 30:
                error = 'Shutdown exceeds 30 seconds; still reserved, with no forced termination'
        elif record.get('phase') == 'failed' or observed.get('MainPID') == '0':
            state, error = 'failed', error or 'Main process exited; owned descendants still reserve this repository'
        elif record.get('phase') == 'starting':
            state = 'starting'
        else:
            state = 'running/active' if health == 'active' else 'running/idle' if health == 'idle' else 'running/unknown'
    elif record.get('external') or record.get('phase') == 'launching':
        state, start = 'unknown', False
        error = 'Unmanaged or unresolved launch; endpoint failure does not prove exit. Reconcile with the original owner.'
    elif (observed.get('ActiveState') == 'failed' or record.get('phase') == 'failed' or
          (record.get('phase') in ('running', 'starting') and not record.get('stop_at'))):
        state = 'failed'
        error = error or 'Runtime exited unsuccessfully; recheck readiness before starting'
    return {'invocation': record.get('invocation'), 'repository_id': key, 'state': state, 'can_start': start, 'can_stop': stop,
            'error': error, 'readiness': record.get('readiness', 'Not checked; every Start rechecks readiness')}


def register_external(config):
    key = repository_identity(config)
    with registry.locked(state_path(key)):
        value = read(key)
        value['external'] = True
        write(key, value)


def confirm_stopped(config, *, manager=None):
    """Explicit operator attestation for legacy imports, never called by the UI."""
    key = repository_identity(config)
    with registry.locked(state_path(key)):
        if busy((manager or Manager()).show(key)):
            raise project.Error('Service still owns this repository; cannot mark it stopped')
        port_available(config)
        write(key, {'phase': 'stopped'})


def check_service_wrapper():
    """A legacy Restart=always wrapper must not undo an intentional Stop."""
    if not os.environ.get('INVOCATION_ID'):
        return
    try:
        groups = Path('/proc/self/cgroup').read_text().splitlines()
        services = [part for line in groups for part in line.split('/') if part.endswith('.service') and not part.startswith('user@')]
        if not services:
            raise project.Error('Cannot verify calling service wrapper; launch from a terminal or the dashboard')
        result = subprocess.run(['systemctl', '--user', 'show', services[-1], '--property=Restart,InvocationID'],
                                capture_output=True, text=True, timeout=5)
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if result.returncode or values.get('Restart') != 'no' or values.get('InvocationID') != os.environ['INVOCATION_ID']:
            raise project.Error('Service wrapper must have Restart=no; automatic restart could undo an explicit Stop')
    except (OSError, subprocess.TimeoutExpired):
        raise project.Error('Cannot verify calling service wrapper; no instance started') from None


def reconcile_imports(config, *, path=None):
    key = repository_identity(config)
    for item in registry.read(path):
        if item.get('mode') != 'external':
            continue
        matches = item['project_path'] == config['project_dir']
        if not matches:
            try:
                matches = repository_identity(project.load(Path(item['project_path']))) == key
            except (project.Error, OSError, ValueError):
                pass
        if matches:
            register_external(config)


def start(config, *, accept_preview=False, manager=None):
    if not accept_preview:
        raise project.Error('Start requires explicit engineering-preview acknowledgment and authorizes eligible issue dispatch')
    manager = manager or Manager()
    key = repository_identity(config)
    with registry.locked(state_path(key)):
        status = describe(config, manager=manager)
        if not status['can_start']:
            raise project.Error('Repository already reserved: ' + status['state'])
        try:
            port_available(config)
        except project.Error as exc:
            write(key, {'phase': 'failed', 'readiness': 'Start preflight failed', 'error': str(exc)})
            raise
        # The service runs readiness after atomic unit creation, before exec.
        write(key, {'phase': 'launching', 'readiness': 'Pending readiness checks', 'error': None})
        try:
            manager.launch(key, config, os.environ)
        except LaunchFailed:
            value = read(key)
            if value.get('phase') != 'failed':
                value.update(phase='failed', error='Service creation failed; verify systemd 250+ user-session support')
                write(key, value)
            raise
    return key


def stop(config, *, invocation, manager=None):
    manager = manager or Manager()
    key = repository_identity(config)
    with registry.locked(state_path(key)):
        value, observed = read(key), manager.show(key)
        if not busy(observed) or not owned(key, value, observed) or invocation != value.get('invocation'):
            raise project.Error('Instance changed or ownership is unverified; refresh before Stop')
        manager.stop(key)
        value['stop_at'] = time.time()
        write(key, value)


def service(key, directory, root):
    """Private managed entry point: receives environment over an anonymous pipe."""
    os.environ['SKILLS_SYMPHONY_STATE'] = root
    invocation = os.environ.get('INVOCATION_ID', '')
    # Only the service manager may enter this path; direct callers cannot bypass
    # the ownership check and run an unreserved runtime.
    observed = Manager().show(key)
    cgroup = next((line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')), None)
    if (not invocation or observed.get('InvocationID') != invocation or
            observed.get('Description') != 'Skills Symphony ' + key or observed.get('ControlGroup') != cgroup):
        return 2
    value = {'phase': 'starting', 'invocation': invocation, 'error': None, 'readiness': 'Checking readiness'}
    write(key, value)
    port_fd = None
    try:
        payload = sys.stdin.buffer.readline(1_048_577)
        if len(payload) > 1_048_576 or not payload.endswith(b'\n'):
            raise project.Error('Runtime environment handoff failed')
        env = json.loads(payload)
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise project.Error('Runtime environment handoff failed')
        os.environ.clear()
        os.environ.update(env)
        os.environ['SKILLS_SYMPHONY_STATE'] = root
        config = project.load(Path(directory))
        if repository_identity(config) != key:
            raise project.Error('Repository identity changed; launch refused')
        problems = project.check(Path(directory))
        if problems:
            # Known readiness diagnostics are actionable. Strip inherited secrets.
            message = 'Not ready: ' + '; '.join(problems)
            for name, secret in env.items():
                if re.search('KEY|TOKEN|SECRET|PASSWORD', name, re.I) and secret:
                    message = message.replace(secret, '[redacted]')
            raise project.Error(message[:2000])
        if project.load(Path(directory)) != config:
            raise project.Error('Configuration changed during readiness; launch refused')
        import fcntl
        port = config['dashboard_port']
        port_fd = None
        if port is not None:
            port_fd = os.open(state_root() / f'port-{port}.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(port_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(port_fd)
                raise project.Error('Configured instance port is reserved by another supported launch') from None
        port_available(config)
        value.update(phase='running', readiness='Passed before this launch')
        write(key, value)
        binary = project.runtime_binary(config)
        child = subprocess.Popen([str(binary), project.PREVIEW_FLAG, str(Path(directory) / '.symphony/WORKFLOW.md')])
        code = child.wait()
        value.update(phase='stopped' if code == 0 else 'failed', error=None if code == 0 else 'Runtime exited unsuccessfully')
        write(key, value)
        if port_fd is not None:
            os.close(port_fd)
        return 0 if code == 0 else 2
    except project.Error as exc:
        value.update(phase='failed', readiness='Failed', error=str(exc))
    except (OSError, ValueError, TypeError):
        value.update(phase='failed', readiness='Failed', error='Process start failed; verify configuration and executable access')
    write(key, value)
    if port_fd is not None:
        os.close(port_fd)
    return 2


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(2)
    raise SystemExit(service(*sys.argv[1:]))


class Control:
    """Background observations and fresh, server-side command validation."""
    def __init__(self, path=None, *, manager=None):
        self.path = path
        self.manager = manager or Manager()
        self.records = {}
        self.lock = threading.Lock()

    def observe(self, item):
        try:
            config = project.load(Path(item['project_path']))
            status = describe(config, manager=self.manager)
            if item.get('mode', 'external') == 'external' and not status['can_stop']:
                status.update(state='unknown', can_start=False,
                              error='Unmanaged import. Stop with the original launcher, then register with --confirm-stopped.')
        except (project.Error, OSError, ValueError, subprocess.TimeoutExpired):
            status = {'state': 'unknown', 'can_start': False, 'can_stop': False,
                      'readiness': 'Configuration or user service manager unavailable',
                      'error': 'Run skills symphony check for configuration; verify systemctl --user access.'}
        with self.lock:
            self.records[item['id']] = status

    def snapshot(self, item):
        with self.lock:
            status = dict(self.records.get(item['id'], {'state': 'unknown', 'can_start': False,
                                                       'can_stop': False, 'readiness': 'Observing process ownership'}))
        if status['state'].startswith('running/'):
            status['state'] = 'running/active' if item['health'] == 'active' else 'running/idle' if item['health'] == 'idle' else 'running/unknown'
        return status

    def action(self, data):
        if not isinstance(data, dict) or set(data) != {'id', 'repository_id', 'action', 'acknowledge', 'invocation'}:
            raise project.Error('Invalid lifecycle request fields')
        if not isinstance(data['id'], str) or not re.fullmatch('[a-f0-9]{24}', data['id']):
            raise project.Error('Invalid registry identifier')
        if data['action'] not in ('start', 'stop') or data['acknowledge'] is not True:
            raise project.Error('Explicit action acknowledgment is required')
        matches = [item for item in registry.read(self.path) if item['id'] == data['id']]
        if len(matches) != 1:
            raise project.Error('Registration changed; refresh before acting')
        item = matches[0]
        config = project.load(Path(item['project_path']))
        if repository_identity(config) != data['repository_id']:
            raise project.Error('Repository configuration changed; refresh before acting')
        if data['action'] == 'start':
            reconcile_imports(config, path=self.path)
            start(config, accept_preview=True, manager=self.manager)
        else:
            stop(config, invocation=data['invocation'], manager=self.manager)
        self.observe(item)
        return {'accepted': True}
