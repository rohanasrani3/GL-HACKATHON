"""Fetch a link that came out of a screenshot, safely.

Every URL here is attacker-controlled in principle: anyone can put a link on a poster, and
CLAUDE.md §4.1 says screenshot content is data, never instruction. So this module is the choke
point, and it is deliberately paranoid:

- only http/https
- DNS is resolved *before* connecting and every resolved address must be public, which blocks
  localhost, RFC1918, link-local and the cloud metadata endpoint (169.254.169.254) that a hosted
  deployment would otherwise expose
- redirects are followed one hop at a time and re-validated, so a public host cannot bounce us
  onto an internal one
- responses are capped and must be HTML or text

Nothing fetched here is ever treated as an instruction. It is page text used to decide "is this
a form?" and to show the user what a link is.
"""
import ipaddress
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

import httpx

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = 12.0
ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
USER_AGENT = "Mozilla/5.0 (compatible; Snapsort/1.0; +https://github.com/rohanasrani3/GL-HACKATHON)"


class UnsafeUrlError(ValueError):
    """The URL points somewhere we refuse to fetch from."""


@dataclass
class FetchedPage:
    url: str  # final URL after redirects
    html: str
    content_type: str
    title: Optional[str] = None


def _public_ip(host: str) -> None:
    """Resolve the host and refuse anything that isn't a public address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeUrlError(f"cannot resolve {host}") from e
    if not infos:
        raise UnsafeUrlError(f"cannot resolve {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local      # includes 169.254.169.254, the cloud metadata endpoint
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeUrlError(f"{host} resolves to non-public address {ip}")


def normalise(url: str) -> str:
    url = (url or "").strip().strip("<>\"'")
    if not url:
        raise UnsafeUrlError("empty url")
    if "://" not in url:
        # Careful: a bare "example.com/x" should become https, but "javascript:alert(1)" must be
        # refused, not turned into "https://javascript:alert(1)". Tell a scheme apart from a
        # host:port by the dot in the host and the digits in the port.
        head, _, tail = url.partition(":")
        if tail and "." not in head and not tail.split("/")[0].isdigit():
            raise UnsafeUrlError(f"unsupported scheme {head.lower()!r}")
        url = f"https://{url}"
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"unsupported scheme {parts.scheme!r}")
    if not parts.netloc:
        raise UnsafeUrlError("no host")
    return urlunparse(parts)


def check_safe(url: str) -> str:
    """Normalise and verify a single URL. Raises UnsafeUrlError if we must not fetch it."""
    url = normalise(url)
    host = urlparse(url).hostname
    if not host:
        raise UnsafeUrlError("no host")
    _public_ip(host)
    return url


async def fetch(url: str, timeout: float = TIMEOUT) -> Optional[FetchedPage]:
    """Fetch a page, revalidating every redirect hop. Returns None on any refusal or error."""
    try:
        current = check_safe(url)
    except UnsafeUrlError:
        return None

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                r = await client.get(current, headers=headers)
                if r.is_redirect:
                    location = r.headers.get("location")
                    if not location:
                        return None
                    # Re-validate: a public host must not be able to bounce us somewhere internal.
                    try:
                        current = check_safe(str(httpx.URL(current).join(location)))
                    except UnsafeUrlError:
                        return None
                    continue

                if r.status_code != 200:
                    return None
                ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and not any(ctype.startswith(t) for t in ALLOWED_TYPES):
                    return None
                body = r.content[:MAX_BYTES]
                try:
                    html = body.decode(r.encoding or "utf-8", errors="replace")
                except (LookupError, UnicodeDecodeError):
                    html = body.decode("utf-8", errors="replace")
                return FetchedPage(url=str(r.url), html=html, content_type=ctype or "text/html")
    except httpx.HTTPError:
        return None
    return None
