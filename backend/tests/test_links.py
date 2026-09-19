"""Link fetching guards.

Every URL here came out of a screenshot, so it is attacker-controlled: anyone can print a link
on a poster. These tests pin the rules that stop that becoming SSRF against the backend.
"""
import socket

import pytest

from snapsort.links import UnsafeUrlError, check_safe, normalise


def _resolves_to(monkeypatch, ip: str):
    """Pretend DNS returns `ip` for any host, so these tests never touch the network."""
    def fake(host, *_a, **_kw):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.mark.parametrize("ip", [
    "127.0.0.1",        # loopback
    "10.0.0.5",         # RFC1918
    "172.16.4.2",       # RFC1918
    "192.168.1.10",     # RFC1918
    "169.254.169.254",  # cloud metadata endpoint - the one that actually matters in production
    "0.0.0.0",
    "::1",
    "fd00::1",          # unique local
])
def test_private_addresses_are_refused(monkeypatch, ip):
    _resolves_to(monkeypatch, ip)
    with pytest.raises(UnsafeUrlError):
        check_safe("https://totally-innocent.example.com/register")


def test_public_address_is_allowed(monkeypatch):
    _resolves_to(monkeypatch, "93.184.216.34")
    assert check_safe("https://example.com/register") == "https://example.com/register"


def test_unresolvable_host_is_refused(monkeypatch):
    def boom(*_a, **_kw):
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(UnsafeUrlError):
        check_safe("https://does-not-exist.example")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "javascript:alert(1)",
    "gopher://example.com",
])
def test_non_http_schemes_are_refused(url):
    with pytest.raises(UnsafeUrlError):
        normalise(url)


def test_bare_host_is_upgraded_to_https():
    assert normalise("forms.gle/abc").startswith("https://")


def test_empty_url_is_refused():
    with pytest.raises(UnsafeUrlError):
        normalise("   ")


def test_surrounding_punctuation_is_stripped():
    """OCR often hands back a URL wrapped in quotes or angle brackets."""
    assert normalise("<https://example.com/a>") == "https://example.com/a"
