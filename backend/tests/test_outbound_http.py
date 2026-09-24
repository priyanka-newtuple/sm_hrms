"""Tests for the shared SSRF guard used on caller-supplied outbound URLs.

The guard is the only thing standing between a tenant-supplied address and the
internal network, so each blocked class of address is asserted explicitly rather
than relying on the callers' tests to cover it indirectly.
"""

from __future__ import annotations

import ipaddress
import socket

import pytest

from common.outbound_http import (
    ALLOWED_INTERNAL_IPS_ENV,
    ALLOWED_URL_SCHEMES,
    PinTarget,
    SsrfError,
    _parse_allowed_networks,
    allowed_internal_networks,
    is_allowlisted_ip,
    is_blocked_ip,
    resolve_safe_target,
)


@pytest.fixture(autouse=True)
def _no_inherited_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from an empty allowlist.

    Both halves matter. conftest loads the repo-root .env with override=True, so a
    developer who allowlisted their own internal service would otherwise flip the
    blocked-address assertions green for the wrong reason. And the parse is cached, so
    without clearing it a value another test already parsed would leak across.
    """
    monkeypatch.delenv(ALLOWED_INTERNAL_IPS_ENV, raising=False)
    _parse_allowed_networks.cache_clear()


# region Scheme validation
@pytest.mark.parametrize("scheme", ALLOWED_URL_SCHEMES)
def test_http_and_https_are_allowed(scheme: str) -> None:
    target = resolve_safe_target(f"{scheme}://example.com/mcp", allow_private_hosts=True)
    assert isinstance(target, PinTarget)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/x",
        "redis://example.com:6379",
        "example.com/no-scheme",
    ],
)
def test_non_http_schemes_are_rejected(url: str) -> None:
    with pytest.raises(SsrfError) as excinfo:
        resolve_safe_target(url)
    assert "scheme" in str(excinfo.value)


def test_a_url_with_no_host_is_rejected() -> None:
    with pytest.raises(SsrfError) as excinfo:
        resolve_safe_target("http:///just-a-path")
    assert "no host" in str(excinfo.value)


# endregion Scheme validation


# region Address filtering
@pytest.mark.parametrize(
    ("address", "label"),
    [
        ("127.0.0.1", "loopback"),
        ("::1", "IPv6 loopback"),
        ("10.0.0.5", "private class A"),
        ("172.16.0.1", "private class B"),
        ("192.168.1.1", "private class C"),
        ("169.254.169.254", "link-local, the cloud metadata endpoint"),
        ("0.0.0.0", "unspecified"),
        ("224.0.0.1", "multicast"),
        ("fd00::1", "IPv6 unique local"),
    ],
)
def test_internal_addresses_are_blocked(address: str, label: str) -> None:
    assert is_blocked_ip(ipaddress.ip_address(address)) is True, label


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700::1111"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert is_blocked_ip(ipaddress.ip_address(address)) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:6379/mcp",
        "http://localhost:8001/mcp",
        "http://10.0.0.5/mcp",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_urls_resolving_to_internal_addresses_are_rejected(url: str) -> None:
    with pytest.raises(SsrfError) as excinfo:
        resolve_safe_target(url)
    assert "blocked address" in str(excinfo.value)


def test_an_unresolvable_host_is_rejected() -> None:
    with pytest.raises(SsrfError) as excinfo:
        resolve_safe_target("https://this-host-does-not-exist.invalid/mcp")
    assert "could not resolve" in str(excinfo.value)


# endregion Address filtering


# region IP pinning
def test_the_request_is_pinned_to_the_validated_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pinning is what defends against DNS rebinding between check and send."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [(socket.AF_INET, None, None, "", ("93.184.216.34", 0))],
    )

    target = resolve_safe_target("https://example.com/mcp")

    # The URL carries the IP, so a second DNS lookup cannot redirect the request...
    assert target.request_url == "https://93.184.216.34/mcp"
    # ...while Host and TLS SNI keep the hostname so certificate checks still pass.
    assert target.host_header == "example.com"
    assert target.sni_hostname == "example.com"


def test_a_port_is_preserved_when_pinning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [(socket.AF_INET, None, None, "", ("93.184.216.34", 0))],
    )

    target = resolve_safe_target("https://example.com:8443/mcp")

    assert target.request_url == "https://93.184.216.34:8443/mcp"
    assert target.host_header == "example.com:8443"


def test_an_ipv6_address_is_bracketed_when_pinning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            (socket.AF_INET6, None, None, "", ("2606:4700::1111", 0, 0, 0))
        ],
    )

    target = resolve_safe_target("https://example.com/mcp")

    assert target.request_url == "https://[2606:4700::1111]/mcp"


def test_plain_http_gets_no_sni_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    """SNI only applies to TLS, so an http target must not set it."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [(socket.AF_INET, None, None, "", ("93.184.216.34", 0))],
    )

    assert resolve_safe_target("http://example.com/mcp").sni_hostname is None


def test_one_blocked_address_rejects_the_host_even_if_others_are_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host resolving to both public and internal addresses must be refused.

    Accepting it would let an attacker win the race by having the resolver return
    the internal address on the request that actually gets sent.
    """
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            (socket.AF_INET, None, None, "", ("93.184.216.34", 0)),
            (socket.AF_INET, None, None, "", ("127.0.0.1", 0)),
        ],
    )

    with pytest.raises(SsrfError):
        resolve_safe_target("https://sneaky.example.com/mcp")


# endregion IP pinning


# region Escape hatch
def test_allow_private_hosts_skips_filtering_and_pinning() -> None:
    """Development-only bypass for pointing at a locally running MCP server."""
    target = resolve_safe_target("http://127.0.0.1:9000/mcp", allow_private_hosts=True)

    assert target.request_url == "http://127.0.0.1:9000/mcp"
    assert target.host_header is None
    assert target.sni_hostname is None


def test_the_bypass_still_enforces_the_scheme() -> None:
    with pytest.raises(SsrfError):
        resolve_safe_target("file:///etc/passwd", allow_private_hosts=True)


# endregion Escape hatch


# region Allowlist parsing
def _set_allowlist(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ALLOWED_INTERNAL_IPS_ENV, value)
    _parse_allowed_networks.cache_clear()


def test_an_unset_allowlist_is_empty() -> None:
    """The default on every existing deployment: nothing internal is reachable."""
    assert allowed_internal_networks() == ()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10.252.5.4", "10.252.5.4/32"),
        ("10.252.5.4/32", "10.252.5.4/32"),
        ("172.18.0.0/16", "172.18.0.0/16"),
        ("  172.18.0.0/16  ", "172.18.0.0/16"),
        ("fd00::/8", "fd00::/8"),
    ],
)
def test_a_single_entry_parses(monkeypatch: pytest.MonkeyPatch, value: str, expected: str) -> None:
    """A bare IP means that address alone; whitespace survives an env_file round-trip."""
    _set_allowlist(monkeypatch, value)

    assert [str(net) for net in allowed_internal_networks()] == [expected]


def test_several_entries_parse_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_allowlist(monkeypatch, "10.252.5.4/32, 172.18.0.0/16")

    assert [str(net) for net in allowed_internal_networks()] == [
        "10.252.5.4/32",
        "172.18.0.0/16",
    ]


def test_a_host_address_carrying_a_prefix_becomes_its_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """strict=False: "10.0.0.5/24" is a plausible thing to type and means 10.0.0.0/24."""
    _set_allowlist(monkeypatch, "10.0.0.5/24")

    assert [str(net) for net in allowed_internal_networks()] == ["10.0.0.0/24"]


@pytest.mark.parametrize("value", ["not-an-ip", "10.0.0.300", "10.0.0.0/33", "example.com"])
def test_an_unparseable_entry_is_dropped(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """A typo must not take outbound calls down, and dropping leaves the address blocked."""
    _set_allowlist(monkeypatch, value)

    assert allowed_internal_networks() == ()


def test_a_bad_entry_does_not_discard_the_good_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_allowlist(monkeypatch, "oops, 10.252.5.4/32, also-bad")

    assert [str(net) for net in allowed_internal_networks()] == ["10.252.5.4/32"]


@pytest.mark.parametrize("value", ["", "   ", ",", " , , "])
def test_a_blank_or_separator_only_value_yields_nothing(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _set_allowlist(monkeypatch, value)

    assert allowed_internal_networks() == ()


# endregion Allowlist parsing


# region Link-local is never allowlistable
@pytest.mark.parametrize(
    "value",
    [
        "169.254.169.254",
        "169.254.169.254/32",
        "169.254.0.0/16",
        "169.254.0.0/15",  # wider than link-local, so it would swallow the endpoint
        "fe80::/10",
    ],
)
def test_a_link_local_entry_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Allowlisting the cloud metadata endpoint would hand out instance credentials."""
    _set_allowlist(monkeypatch, value)

    assert allowed_internal_networks() == ()


def test_the_metadata_endpoint_stays_blocked_even_when_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_allowlist(monkeypatch, "169.254.169.254/32")

    assert is_blocked_ip(ipaddress.ip_address("169.254.169.254")) is True


def test_refusing_link_local_does_not_discard_legitimate_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_allowlist(monkeypatch, "169.254.169.254, 10.252.5.4/32")

    assert [str(net) for net in allowed_internal_networks()] == ["10.252.5.4/32"]


# endregion Link-local is never allowlistable


# region Allowlisted addresses pass the filter
def test_an_allowlisted_address_is_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_allowlist(monkeypatch, "10.252.5.4/32")

    assert is_allowlisted_ip(ipaddress.ip_address("10.252.5.4")) is True
    assert is_blocked_ip(ipaddress.ip_address("10.252.5.4")) is False


def test_an_address_inside_an_allowlisted_block_is_not_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Docker case: the container IP moves, so the subnet is what gets listed."""
    _set_allowlist(monkeypatch, "172.18.0.0/16")

    assert is_blocked_ip(ipaddress.ip_address("172.18.0.3")) is False
    assert is_blocked_ip(ipaddress.ip_address("172.18.9.99")) is False


@pytest.mark.parametrize("address", ["10.252.5.5", "10.0.0.5", "127.0.0.1", "192.168.1.1"])
def test_every_other_internal_address_stays_blocked(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    """The point of an allowlist over a switch: one exception, not a blanket opt-out."""
    _set_allowlist(monkeypatch, "10.252.5.4/32")

    assert is_blocked_ip(ipaddress.ip_address(address)) is True


def test_an_ipv4_entry_does_not_allowlist_ipv6(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cross-version containment raises rather than compares, so it is guarded."""
    _set_allowlist(monkeypatch, "10.252.5.4/32")

    assert is_allowlisted_ip(ipaddress.ip_address("fd00::1")) is False


def test_an_ipv6_entry_allowlists_an_ipv6_address(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_allowlist(monkeypatch, "fd00::/8")

    assert is_blocked_ip(ipaddress.ip_address("fd00::1")) is False


# endregion Allowlisted addresses pass the filter


# region Allowlisted targets are still pinned
def test_an_allowlisted_host_is_still_pinned_to_its_resolved_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason this is an allowlist and not a bypass.

    allow_private_hosts=True returns the URL untouched, leaving a window for DNS to
    return something else before the request is sent. Allowlisting keeps the guard's
    normal path, so the internal host is pinned exactly like a public one.
    """
    _set_allowlist(monkeypatch, "172.18.0.0/16")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [(socket.AF_INET, None, None, "", ("172.18.0.3", 0))],
    )

    target = resolve_safe_target("http://bot-api-service-dev:8000/v1/api")

    assert target.request_url == "http://172.18.0.3:8000/v1/api"
    assert target.host_header == "bot-api-service-dev:8000"


def test_a_host_resolving_outside_the_allowlist_is_still_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_allowlist(monkeypatch, "172.18.0.0/16")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [(socket.AF_INET, None, None, "", ("10.0.0.5", 0))],
    )

    with pytest.raises(SsrfError) as excinfo:
        resolve_safe_target("http://sneaky.internal/mcp")
    assert "blocked address" in str(excinfo.value)


def test_the_error_names_the_variable_that_fixes_it() -> None:
    """The ticket's complaint was that the bare message reads as a bug, not as config.

    Phrased for the operator rather than the caller: on SaaS this text surfaces to a
    tenant who has no way to set a deployment env var, so it must not read as an
    instruction to them.
    """
    with pytest.raises(SsrfError) as excinfo:
        resolve_safe_target("http://127.0.0.1:6379/mcp")
    message = str(excinfo.value)

    assert ALLOWED_INTERNAL_IPS_ENV in message
    assert "deployment operator" in message


def test_an_allowlisted_address_still_cannot_change_the_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_allowlist(monkeypatch, "127.0.0.0/8")

    with pytest.raises(SsrfError) as excinfo:
        resolve_safe_target("file://127.0.0.1/etc/passwd")
    assert "scheme" in str(excinfo.value)


# endregion Allowlisted targets are still pinned
