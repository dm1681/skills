"""Read-only adapter for Symphony be10a1b7's GET /api/v1/state."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import http.client
import json
import math
import re
import threading
import time
from urllib.parse import urlsplit

import symphony_registry as registry

METRICS = ('input_tokens', 'output_tokens', 'total_tokens', 'seconds_running')
EVENTS = {'session_started', 'turn_started', 'turn_completed', 'turn_failed', 'turn_cancelled',
          'token_usage', 'notification', 'tool_call', 'tool_result', 'session_failed',
          'session_completed', 'approval_required', 'item_started', 'item_completed'}


class Incompatible(ValueError):
    pass


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e18 else None


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.timestamp() if result.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value) else None


def issue_link(value):
    if not isinstance(value, str) or len(value) > 600:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme == 'https' and parsed.netloc == 'linear.app' and not parsed.query
                and not parsed.fragment and re.fullmatch(r'/[A-Za-z0-9_-]+/issue/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)?', parsed.path)):
            return value
    except ValueError:
        pass
    return None


def project_state(payload: dict) -> dict:
    if not isinstance(payload, dict) or 'error' in payload:
        raise Incompatible('State unavailable or unsupported API')
    generated = timestamp(payload.get('generated_at'))
    if generated is None:
        raise Incompatible('Missing valid source timestamp')
    rows = []
    counts = {}
    for source, status in (('running', 'active'), ('retrying', 'retrying')):
        values = payload.get(source)
        if not isinstance(values, list) or len(values) > 1000:
            raise Incompatible('Missing or unsupported session lists')
        seen = set()
        for value in values:
            if not isinstance(value, dict):
                raise Incompatible('Unsupported session entry')
            key = identifier(value.get('issue_id')) or identifier(value.get('issue_identifier'))
            if key is None:
                raise Incompatible('Session identity unavailable')
            if key in seen:
                continue
            seen.add(key)
            tokens = value.get('tokens')
            tokens = tokens if isinstance(tokens, dict) else {}
            event = value.get('last_event')
            rows.append({'key': source + ':' + key, 'issue': identifier(value.get('issue_identifier')),
                         'issue_url': issue_link(value.get('issue_url')), 'title': None,
                         'status': status, 'session_id': identifier(value.get('session_id')),
                         'started_at': timestamp(value.get('started_at')),
                         'last_event_at': timestamp(value.get('last_event_at')),
                         'activity': event if isinstance(event, str) and event in EVENTS else None,
                         'attempt': number(value.get('attempt')), 'due_at': timestamp(value.get('due_at')),
                         'tokens': {key: number(tokens.get(key)) for key in METRICS[:3]}})
        counts[source] = len(seen)
    totals = payload.get('codex_totals')
    totals = totals if isinstance(totals, dict) else {}
    return {'generated_at': generated, 'sessions': rows, 'counts': counts,
            'usage': {key: number(totals.get(key)) for key in METRICS}}


def fetch(address: str, timeout: float) -> dict:
    parsed = urlsplit(registry.endpoint(address))
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    transport = None
    # A wall-clock timer bounds slow trickles as well as idle socket timeouts.
    def abort():
        sock = transport or connection.sock
        if sock:
            import socket
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    timer = threading.Timer(timeout, abort)
    timer.daemon = True
    timer.start()
    try:
        connection.connect()
        transport = connection.sock
        connection.request('GET', '/api/v1/state', headers={'Accept': 'application/json'})
        response = connection.getresponse()
        if response.status != 200:  # Never follow redirects.
            raise OSError('Endpoint unavailable')
        if response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise Incompatible('Expected JSON state API')
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise Incompatible('State response too large')
        try:
            return project_state(json.loads(body))
        except (ValueError, UnicodeError):
            raise Incompatible('Malformed or unsupported state API') from None
    finally:
        timer.cancel()
        connection.close()


class Monitor:
    """One bounded poll loop per endpoint; browser requests only read snapshots."""
    def __init__(self, path=None, *, interval=5., timeout=2., clock=time.time, loader=fetch):
        if not 1 <= interval <= 300 or not .1 <= timeout <= 30:
            raise ValueError('Refresh must be 1–300 seconds; timeout must be 0.1–30 seconds')
        self.path, self.interval, self.timeout = path, interval, timeout
        self.clock, self.loader = clock, loader
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.records, self.workers = {}, {}
        self.registry_error = False
        self.thread = None

    def observe(self, item):
        try:
            state = self.loader(item['endpoint'], self.timeout)
            result = {'state': state, 'observed_at': self.clock(), 'error': None}
        except Incompatible:
            result = {'error': 'incompatible'}
        except (OSError, ValueError, http.client.HTTPException):
            result = {'error': 'unreachable'}
        with self.lock:
            previous = self.records.get(item['id'], {})
            self.records[item['id']] = {**previous, **result, 'checked_at': self.clock()}

    def _poll(self, item, stopped):
        while not self.stop_event.is_set() and not stopped.is_set():
            self.observe(item)
            if stopped.wait(self.interval):
                break

    def reconcile(self):
        try:
            entries = registry.read(self.path)
        except (OSError, ValueError):
            with self.lock:
                self.registry_error = True
            return
        with self.lock:
            self.registry_error = False
            self.entries = entries
        ids = {item['id'] for item in entries if item['endpoint']}
        for key in list(self.workers):
            if key not in ids:
                self.workers.pop(key)[0].set()
        for item in entries:
            if item['endpoint'] and item['id'] not in self.workers:
                stopped = threading.Event()
                thread = threading.Thread(target=self._poll, args=(item, stopped), daemon=True)
                self.workers[item['id']] = stopped, thread
                thread.start()

    def start(self):
        self.entries = []
        def loop():
            while not self.stop_event.is_set():
                self.reconcile()
                self.stop_event.wait(self.interval)
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(self.timeout + 1)
        workers = list(self.workers.values())
        for stopped, _ in workers:
            stopped.set()
        deadline = time.monotonic() + self.timeout + 1
        for _, thread in workers:
            thread.join(max(0, deadline - time.monotonic()))

    def snapshot(self):
        now = self.clock()
        with self.lock:
            entries = copy.deepcopy(getattr(self, 'entries', []))
            records = copy.deepcopy(self.records)
            registry_error = self.registry_error
        instances = []
        for item in entries:
            record = records.get(item['id'], {})
            state = record.get('state')
            health = 'disabled' if item['endpoint'] is None else record.get('error') or 'configured'
            current = False
            if state and not record.get('error'):
                age = max(now - state['generated_at'], now - record['observed_at'])
                current = age <= max(15, self.interval * 3 + self.timeout) and state['generated_at'] <= now + 30
                health = ('active' if state['counts']['running'] or state['counts']['retrying'] else 'idle') if current else 'stale'
            instances.append({**item, 'health': health, 'current': current,
                              'last_success': record.get('observed_at'), 'checked_at': record.get('checked_at'),
                              'source_time': state['generated_at'] if state else None,
                              'sessions': state['sessions'] if current else [],
                              'counts': state['counts'] if current else None,
                              'usage': state['usage'] if current else None})
        current = [item for item in instances if item['current']]
        usage = {}
        for key in METRICS:
            values = [item['usage'][key] for item in current if item['usage'][key] is not None]
            usage[key] = {'value': sum(values) if values else None, 'instances': len(values)}
        return {'observed_at': now, 'instances': instances, 'registry_error': registry_error,
                'coverage': {'current': len(current), 'registered': len(instances)},
                'counts': {key: sum(item['counts'][key] for item in current) for key in ('running', 'retrying')},
                'usage': usage}
