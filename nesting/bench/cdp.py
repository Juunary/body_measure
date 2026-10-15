"""Minimal Chrome DevTools Protocol driver for headless Chrome and Electron apps.

Only what the benchmark needs: launch a Chromium-based executable with remote
debugging, find a page target, evaluate JavaScript (optionally awaiting a
promise), and kill the whole process tree afterwards.
"""
import json
import socket
import subprocess
import time
import urllib.request

from websockets.sync.client import connect


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Process:
    def __init__(self, exe, args, port, env=None, cwd=None, log_path=None):
        self.port = port
        self.log = open(log_path, 'w', encoding='utf-8', errors='replace') if log_path else subprocess.DEVNULL
        self.proc = subprocess.Popen([str(exe), f'--remote-debugging-port={port}', *args],
                                     stdout=self.log, stderr=subprocess.STDOUT, env=env, cwd=cwd)

    def targets(self):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json/list', timeout=5) as r:
            return json.load(r)

    def wait_target(self, predicate, timeout=60.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                for t in self.targets():
                    if t.get('type') == 'page' and predicate(t):
                        return t
            except OSError:
                pass
            time.sleep(0.25)
        raise TimeoutError('no matching DevTools target')

    def close(self):
        if self.proc.poll() is None:
            subprocess.run(['taskkill', '/PID', str(self.proc.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        if self.log is not subprocess.DEVNULL:
            self.log.close()


class Page:
    def __init__(self, target):
        # no keepalive pings: a busy browser process must not drop the session; our own timeouts decide
        self.ws = connect(target['webSocketDebuggerUrl'], max_size=None, open_timeout=30, ping_interval=None)
        self.next_id = 0

    def send(self, method, params=None, timeout=60.0):
        self.next_id += 1
        mid = self.next_id
        self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f'{method} timed out')
            message = json.loads(self.ws.recv(timeout=remaining))
            if message.get('id') == mid:
                if 'error' in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get('result', {})

    def evaluate(self, expression, await_promise=False, timeout=60.0):
        result = self.send('Runtime.evaluate', {'expression': expression, 'awaitPromise': await_promise,
                                                'returnByValue': True}, timeout)
        if 'exceptionDetails' in result:
            details = result['exceptionDetails']
            exception = details.get('exception', {})
            text = exception.get('description') or exception.get('value') or details.get('text')
            raise RuntimeError(f'JavaScript error: {text}')
        return result.get('result', {}).get('value')

    def wait_for(self, expression, timeout=60.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.evaluate(expression, timeout=10):
                    return True
            except (RuntimeError, TimeoutError):
                pass
            time.sleep(0.25)
        raise TimeoutError(f'condition never became true: {expression}')

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
