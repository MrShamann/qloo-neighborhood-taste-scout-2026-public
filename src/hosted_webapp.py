"""Original zero-provider-call hosting preflight for Qloo contest-only site.

This is an INGRESS ADAPTER, not a published app or authenticated Qloo demo.
The external HTTPS reverse proxy must preserve the exact Host header.
Public real Qloo calls are deliberately prohibited until a separate
verified per-provider quota/cost and credential delivery design is approved.
"""
from __future__ import annotations

import argparse
import re
import os
import ipaddress
from http.server import ThreadingHTTPServer

from .webapp import DemoHandler

_DOMAIN = re.compile(
    r"^(?=.{4,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


def validate_public_host(hostname: str) -> str:
    if not isinstance(hostname, str) or hostname != hostname.lower():
        raise ValueError("public hostname must be lowercase ASCII")
    if not hostname.isascii() or not _DOMAIN.fullmatch(hostname):
        raise ValueError("public hostname must be an exact DNS name")
    if hostname.endswith((".localhost", ".local", ".internal", ".invalid")):
        raise ValueError("not a public DNS hostname")
    if ".." in hostname or "@" in hostname or ":" in hostname or "/" in hostname:
        raise ValueError("hostname may not carry credentials or port")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("numeric IP addresses are not permitted as public hostnames")
    return hostname


class HostedDemoHandler(DemoHandler):
    """Only synthetic source replay is exposed by this explicitly separate ingress."""

    def do_GET(self):
        # A provider-free liveness check for free-tier hosting.  No secrets,
        # visitor data, or Qloo quota state are returned to load balancers.
        if self.path == "/healthz":
            if not self._allowed_host():
                self._json(403, {"error": "INVALID_PUBLIC_HOST"})
                return
            self._json(200, {"service": "qloo-taste-scout", "status": "ready",
                             "public_real_provider": False})
            return
        super().do_GET()

    def _allowed_host(self):
        return self.headers.get("Host", "") == self.server.public_hostname

    def _allowed_origin(self, origin: str) -> bool:
        # Public ingress never permits null/missing Origin, nor a forged proxy header.
        return origin == "https://" + self.server.public_hostname

    def _provider_ready(self) -> bool:
        # No browser-visible live toggle, even when a shell accidentally carries a key.
        return False

    def _allow_live(self) -> bool:
        # Protect sponsor event quota against unbounded public traffic.
        return False


def hosted_server(hostname: str, port: int, listen: str = "127.0.0.1") -> ThreadingHTTPServer:
    hostname = validate_public_host(hostname)
    if type(port) is not int or not (1024 <= port <= 65535):
        raise ValueError("port must be 1024..65535")
    if listen not in ("127.0.0.1", "0.0.0.0"):
        raise ValueError("unexpected bind interface")
    if listen != "127.0.0.1" and (
        os.environ.get("QLOO_PUBLIC_DEPLOY_APPROVED") != "YES"
        or os.environ.get("QLOO_FREE_HOSTING_BILLING_VERIFIED") != "YES"
    ):
        raise ValueError("public listener is disabled without exact release and free-hosting gates")
    server = ThreadingHTTPServer((listen, port), HostedDemoHandler)
    server.public_hostname = hostname
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description="Private Qloo HTTPS ingress compatibility preflight")
    parser.add_argument("--hostname", default=os.environ.get("QLOO_PUBLIC_HOSTNAME"),
                        required=False)
    parser.add_argument("--port", type=int, default=os.environ.get("PORT","8879"))
    parser.add_argument("--listen", default="127.0.0.1", choices=("127.0.0.1", "0.0.0.0"))
    args = parser.parse_args()
    try:
        server = hosted_server(args.hostname, args.port, args.listen)
    except ValueError as exc:
        parser.error(str(exc))
    with server:
        print("QLOO_HOSTED_SYNTHETIC_ONLY=TRUE", flush=True)
        print("QLOO_HOSTED_REAL_API_CALLS=DISABLED", flush=True)
        print("HOSTED_PUBLIC_RELEASE=NOT_ESTABLISHED_BY_RUNNING_THIS_PROCESS", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
