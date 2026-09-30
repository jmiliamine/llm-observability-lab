"""Tiny HTTP helper for the e2e tests.

URLs like http://prometheus.localhost:8080 are routed by the cluster Gateway on the Host
header. Browsers resolve *.localhost to 127.0.0.1 by themselves, Windows' resolver does not,
so we connect to 127.0.0.1 and send the original Host header — exactly what DNS + the
Gateway do, without editing the hosts file (which needs admin rights).
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any

import pytest


def request(url: str, data: dict | None = None, timeout: float = 10) -> Any:
    parts = urllib.parse.urlsplit(url)
    headers = {"Content-Type": "application/json"}
    target = url
    if parts.hostname and parts.hostname.endswith(".localhost"):
        headers["Host"] = parts.netloc
        target = urllib.parse.urlunsplit(parts._replace(netloc=f"127.0.0.1:{parts.port or 80}"))
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(target, data=body, headers=headers, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw) if raw else None
    except ValueError:                  # health endpoints answer plain text ("ready")
        return raw.decode("utf-8", "replace")


def unavailable(reason: str) -> None:
    """Skip when the infrastructure is simply not running; fail when the task said it must be
    (OBSLAB_REQUIRE_STACK=1), so a green `task test:k8s` always means the checks really ran."""
    if os.environ.get("OBSLAB_REQUIRE_STACK") == "1":
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def is_up(url: str) -> bool:
    try:
        request(url, timeout=3)
        return True
    except Exception:
        return False


def wait_up(url: str, timeout: float = 60) -> bool:
    """Poll a readiness URL. Right after `docker compose up`, Tempo answers 503 for ~15 s
    ("waiting for 15s after being ready") although its container is already healthy."""
    end = time.time() + timeout
    while True:
        if is_up(url):
            return True
        if time.time() > end:
            return False
        time.sleep(3)
