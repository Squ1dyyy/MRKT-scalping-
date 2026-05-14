import logging
from typing import Any, Dict, Optional

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import HTTPError, Timeout
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from transport.errors import AuthError, ServerError, NetworkError
from transport.rate_limit import TokenBucket

if False:
    from pool.account import AccountConfig


_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_DEFAULT_TIMEOUT = 30


def _build_headers(auth_token: str, user_agent: Optional[str] = None) -> Dict[str, str]:
    ua = user_agent or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
    return {
        "authority": "api.tgmrkt.io",
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru,en;q=0.9",
        "authorization": auth_token,
        "content-type": "application/json",
        "cookie": f"access_token={auth_token}",
        "origin": "https://cdn.tgmrkt.io",
        "referer": "https://cdn.tgmrkt.io/",
        "user-agent": ua,
    }


class MarketClient:
    """Long-lived HTTP client for a single MRKT account.

    Creates one AsyncSession per account and keeps it alive for the
    whole process. Applies per-account rate-limiting and exponential
    backoff on transient errors (429 / 5xx / Timeout).
    """

    def __init__(self, cfg: "AccountConfig") -> None:
        self.cfg = cfg
        self._headers = _build_headers(cfg.auth_token, cfg.user_agent)
        self._rate_limiter = TokenBucket(cfg.rate_limit_rps)
        self._session: Optional[AsyncSession] = None
        self._log = logging.getLogger(f"mrkt.client.{cfg.name}")

    async def start(self) -> None:
        proxies = {"https": cfg_proxy} if (cfg_proxy := self.cfg.proxy) else None
        self._session = AsyncSession(
            impersonate=self.cfg.cf_impersonate,
            proxies=proxies,
            timeout=_DEFAULT_TIMEOUT,
        )
        self._log.info("Client started (proxy=%s)", self.cfg.proxy or "none")

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            self._log.info("Client closed")

    async def get(self, url: str, **kwargs: Any) -> Any:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Any:
        return await self._request("POST", url, **kwargs)


    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        assert self._session is not None, "Client not started. Call await client.start() first."

        await self._rate_limiter.acquire()

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((ServerError, Timeout, NetworkError, OSError)),
            stop=stop_after_attempt(5),
            wait=wait_exponential_jitter(initial=1, max=30),
            before_sleep=before_sleep_log(self._log, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                resp = await self._session.request(
                    method,
                    url,
                    headers=self._headers,
                    **kwargs,
                )
                if resp.status_code == 401:
                    raise AuthError(f"[{self.cfg.name}] 401 Unauthorized on {url}")
                if resp.status_code in _RETRYABLE_STATUS:
                    raise ServerError(
                        f"[{self.cfg.name}] HTTP {resp.status_code} on {url}",
                        status_code=resp.status_code,
                    )
                try:
                    resp.raise_for_status()
                except HTTPError as exc:
                    raise NetworkError(str(exc)) from exc

                self._log.debug(
                    "%s %s → %d",
                    method,
                    url,
                    resp.status_code,
                    extra={"account": self.cfg.name, "endpoint": url, "status": resp.status_code},
                )
                return resp.json()
