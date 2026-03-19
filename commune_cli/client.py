"""CommuneClient — thin httpx wrapper with API key or x402 wallet auth.

Auth modes:
  1. API key: Authorization: Bearer comm_...
  2. x402 wallet: pay-per-call with USDC (handles 402 responses automatically)

Raises:
  httpx.ConnectError / httpx.TimeoutException — caller wraps with network_error()
  All non-2xx responses — caller checks response.is_success and calls api_error()
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from .state import AppState

DEFAULT_TIMEOUT = 30.0


class CommuneClient:
    """HTTP client for the Commune API.

    Usage:
        client = CommuneClient.from_state(state)
        r = client.get("/v1/domains")
        if not r.is_success:
            api_error(r, json_output=state.should_json())
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        wallet_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.wallet_key = wallet_key
        self.timeout = timeout
        self._x402_client: Any = None

    @classmethod
    def from_state(cls, state: AppState) -> "CommuneClient":
        return cls(
            base_url=state.base_url,
            api_key=state.api_key,
            wallet_key=state.wallet_key,
            timeout=DEFAULT_TIMEOUT,
        )

    def _get_x402_client(self) -> Any:
        """Lazily initialize x402 client from wallet key."""
        if self._x402_client is not None:
            return self._x402_client
        if not self.wallet_key:
            return None
        try:
            from x402 import x402Client
            from x402.mechanisms.evm.exact import ExactEvmScheme
            from eth_account import Account

            key = self.wallet_key if self.wallet_key.startswith("0x") else f"0x{self.wallet_key}"
            signer = Account.from_key(key)
            self._x402_client = x402Client()
            self._x402_client.register("eip155:*", ExactEvmScheme(signer=signer))
            return self._x402_client
        except ImportError:
            import sys
            print(
                "Warning: --wallet-key is set but x402 dependencies are missing.\n"
                "  Install them: pip install x402[evm] eth_account",
                file=sys.stderr,
            )
            return None

    def _base_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "commune-cli/0.1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _url(self, path: str) -> str:
        return self.base_url + path

    def _handle_402(
        self,
        resp: httpx.Response,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Handle 402 Payment Required by signing an x402 payment and retrying."""
        x402 = self._get_x402_client()
        if x402 is None:
            return resp  # No wallet — return the 402 as-is

        try:
            body = resp.json()
        except Exception:
            return resp

        accepts = body.get("accepts", [])
        if not accepts:
            return resp

        try:
            payment_payload = x402.create_payment_payload(accepts)
        except Exception:
            return resp

        headers = dict(kwargs.pop("headers", self._base_headers()))
        headers["PAYMENT-SIGNATURE"] = payment_payload

        with httpx.Client(timeout=self.timeout) as client:
            return client.request(method, self._url(path), headers=headers, **kwargs)

    def _req(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[Any] = None,
        data: Optional[bytes] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        headers = self._base_headers()
        if extra_headers:
            headers.update(extra_headers)
        if data is not None:
            headers.pop("Content-Type", None)

        if params:
            params = {k: v for k, v in params.items() if v is not None}

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.request(
                method,
                self._url(path),
                headers=headers,
                params=params or None,
                json=json,
                content=data,
            )

        # Auto-pay with x402 if we get a 402 and have a wallet configured
        if resp.status_code == 402 and self.wallet_key:
            resp = self._handle_402(resp, method, path, params=params, json=json, content=data)

        return resp

    def get(self, path: str, *, params: Optional[dict[str, Any]] = None) -> httpx.Response:
        return self._req("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        json: Optional[Any] = None,
        data: Optional[bytes] = None,
        extra_headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        return self._req("POST", path, json=json, data=data, extra_headers=extra_headers, params=params)

    def patch(self, path: str, *, json: Optional[Any] = None) -> httpx.Response:
        return self._req("PATCH", path, json=json)

    def delete(self, path: str, *, params: Optional[dict[str, Any]] = None) -> httpx.Response:
        return self._req("DELETE", path, params=params)

    def put(self, path: str, *, json: Optional[Any] = None) -> httpx.Response:
        return self._req("PUT", path, json=json)
