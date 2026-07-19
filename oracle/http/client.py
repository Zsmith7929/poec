import time
from typing import Any
from urllib.parse import urlparse

import httpx


class ComplianceError(Exception):
    """Raised when a request targets a host outside the allowlist."""


class HttpClient:
    def __init__(
        self,
        user_agent: str,
        allowed_hosts: set[str],
        max_retries: int = 4,
        timeout: float = 20.0,
    ) -> None:
        self._allowed = allowed_hosts
        self._max_retries = max_retries
        self._client = httpx.Client(headers={"User-Agent": user_agent}, timeout=timeout)

    def _check_host(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        if host not in self._allowed:
            raise ComplianceError(f"host not in allowlist: {host!r}")

    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        self._check_host(url)
        backoff = 1.0
        last_exc: Exception | None = None
        for _attempt in range(self._max_retries):
            resp = self._client.get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else backoff
                time.sleep(delay)
                backoff *= 2
                last_exc = httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                continue
            resp.raise_for_status()
            return resp.json()
        raise last_exc if last_exc else RuntimeError("request failed")

    def close(self) -> None:
        self._client.close()
