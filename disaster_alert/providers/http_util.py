"""HTTP helpers using urllib (no httpx)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any


def fetch_json(
    url: str,
    *,
    timeout_sec: float = 12.0,
    headers: dict[str, str] | None = None,
) -> Any:
    req_headers = {"Accept": "application/json", "User-Agent": "disaster-alert/0.1"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, headers=req_headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec, context=ctx) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc
    return json.loads(body)


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_sec: float = 12.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "disaster-alert/0.1",
    }
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec, context=ctx) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"POST failed for {url}: {exc.reason}") from exc
