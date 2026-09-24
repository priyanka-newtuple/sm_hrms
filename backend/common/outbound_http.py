"""Shared SSRF guard for outbound HTTP calls to caller-supplied URLs.

Any module that dials a URL supplied by a tenant (connector base URLs, remote
MCP server addresses) must route the target through :func:`resolve_safe_target`
first. The guard rejects non-HTTP schemes, refuses hosts that resolve into
private/loopback/link-local space, and pins the request to the IP it validated
so a second DNS lookup cannot swap in a different address (DNS rebinding).

A deployment whose outbound calls must reach a co-located service on an internal
address names that address in :data:`ALLOWED_INTERNAL_IPS_ENV`. That narrows the
private-address check to everything *except* the listed blocks and leaves the rest
of the guard — scheme check, resolution, IP pinning — fully in force.

Callers must also disable redirects on the client they send with: a 3xx would
otherwise bounce the request to a host this guard never saw.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from common.logger import logger

SCHEME_HTTP = "http"
SCHEME_HTTPS = "https"
ALLOWED_URL_SCHEMES = (SCHEME_HTTP, SCHEME_HTTPS)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

# Internal addresses this deployment is allowed to reach, as a comma-separated list of
# IPs or CIDR blocks: "10.252.5.4/32, 172.18.0.0/16". A bare IP means that address
# alone. Unset — the default everywhere — keeps every internal address blocked.
#
# Prefer a CIDR for container networks: Docker assigns service IPs dynamically, so a
# bare 172.18.0.3 stops matching the first time the container is recreated.
#
# This is deliberately an allowlist and not an on/off switch. Listing an address
# exempts *that* address from the private-space check and nothing else: every other
# internal address stays blocked, and allowlisted hosts are still resolved and still
# pinned to the validated IP, so DNS rebinding is defeated on them too. The addresses
# describe the network the process runs in, so they are deployment configuration —
# read from the environment, never from tenant-supplied data.
ALLOWED_INTERNAL_IPS_ENV = "OUTBOUND_HTTP_ALLOWED_INTERNAL_IPS"

# Never allowlistable, whatever an operator configures. 169.254.169.254 is the cloud
# metadata endpoint: anything that can reach it can read instance credentials, which is
# the single worst thing an SSRF can be pointed at. No co-located service is ever
# addressed on link-local, so refusing these entries costs nothing a caller needs.
_NEVER_ALLOWLISTED: tuple[IPNetwork, ...] = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
)


class SsrfError(Exception):
    """Raised when a target URL resolves to a disallowed address."""


@dataclass
class PinTarget:
    """A validated request target pinned to a specific resolved IP (defends DNS rebinding)."""

    request_url: str
    host_header: str | None
    sni_hostname: str | None


def resolve_safe_target(url: str, allow_private_hosts: bool = False) -> PinTarget:
    """Validate the host and pin the request to a safe resolved IP.

    Args:
        url: Fully-qualified target URL to validate.
        allow_private_hosts: When True, skip IP filtering and pinning entirely.
            Reserved for trusted internal callers and local development.

    Returns:
        The pinned request target to send with.

    Raises:
        SsrfError: If the scheme is unsupported, the host is missing or
            unresolvable, or any resolved address is in blocked space and not
            allowlisted through :data:`ALLOWED_INTERNAL_IPS_ENV`.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise SsrfError(f"unsupported URL scheme: {parsed.scheme or '(none)'}")
    host = parsed.hostname
    if not host:
        raise SsrfError("URL has no host")
    if allow_private_hosts:
        return PinTarget(request_url=url, host_header=None, sni_hostname=None)

    addresses = resolve_host_ips(host)
    for address in addresses:
        if is_blocked_ip(address):
            # The remedy is named because the bare message reads as a platform bug to
            # anyone deploying alongside a co-located service, when the fix is config.
            # Phrased as what an operator must do, not as an instruction to the caller:
            # on SaaS this message reaches a tenant who cannot set deployment env vars,
            # and telling them to edit one would just send them somewhere they can't go.
            raise SsrfError(
                f"host {host} resolves to a blocked address {address}; a trusted internal "
                f"service must be allowlisted by the deployment operator via "
                f"{ALLOWED_INTERNAL_IPS_ENV}"
            )
    safe_ip = addresses[0]
    literal = f"[{safe_ip}]" if safe_ip.version == 6 else str(safe_ip)
    netloc = f"{literal}:{parsed.port}" if parsed.port else literal
    host_header = f"{host}:{parsed.port}" if parsed.port else host
    return PinTarget(
        request_url=parsed._replace(netloc=netloc).geturl(),
        host_header=host_header,
        sni_hostname=host if parsed.scheme == SCHEME_HTTPS else None,
    )


def resolve_host_ips(host: str) -> list[IPAddress]:
    """Return every address a host resolves to.

    Args:
        host: Hostname or IP literal to resolve.

    Returns:
        The resolved addresses, in the order the resolver returned them.

    Raises:
        SsrfError: If the host cannot be resolved.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SsrfError(f"could not resolve host {host}: {exc}") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def is_blocked_ip(address: IPAddress) -> bool:
    """Return whether an address falls in space outbound calls must never reach.

    Args:
        address: Resolved address to classify.

    Returns:
        True when the address is private, loopback, link-local, reserved,
        multicast, or unspecified — unless the deployment has allowlisted it
        through :data:`ALLOWED_INTERNAL_IPS_ENV`.
    """
    if is_allowlisted_ip(address):
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def is_allowlisted_ip(address: IPAddress) -> bool:
    """Return whether the deployment has declared this internal address reachable.

    Args:
        address: Resolved address to look up.

    Returns:
        True when the address falls inside a block listed in
        :data:`ALLOWED_INTERNAL_IPS_ENV`.
    """
    return any(
        address.version == network.version and address in network
        for network in allowed_internal_networks()
    )


def allowed_internal_networks() -> tuple[IPNetwork, ...]:
    """Return the internal networks this deployment may reach.

    Returns:
        The parsed contents of :data:`ALLOWED_INTERNAL_IPS_ENV`, empty when unset.
    """
    return _parse_allowed_networks(os.environ.get(ALLOWED_INTERNAL_IPS_ENV, ""))


@lru_cache(maxsize=8)
def _parse_allowed_networks(raw: str) -> tuple[IPNetwork, ...]:
    """Parse the allowlist env value, discarding anything unusable.

    Every rejection path drops the entry rather than raising: a typo in deployment
    config must not take outbound calls down, and dropping fails closed — the address
    stays blocked, which is the safe direction to be wrong in.

    Cached on the raw string, not read once at import, so a changed environment
    produces a new key instead of a stale answer.

    Args:
        raw: Comma-separated IPs and CIDR blocks, as supplied by the operator.

    Returns:
        The usable networks, in the order they were listed.
    """
    networks: list[IPNetwork] = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        try:
            # strict=False so a host address carrying a prefix ("10.0.0.5/24") is read
            # as the block containing it rather than rejected outright.
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError as exc:
            logger.warning(f"{ALLOWED_INTERNAL_IPS_ENV}: ignoring entry {entry!r} — {exc}")
            continue
        if any(
            network.version == reserved.version and network.overlaps(reserved)
            for reserved in _NEVER_ALLOWLISTED
        ):
            logger.warning(
                f"{ALLOWED_INTERNAL_IPS_ENV}: refusing link-local entry {entry!r} — it would "
                f"expose the cloud metadata endpoint"
            )
            continue
        networks.append(network)
    if networks:
        listed = ", ".join(str(network) for network in networks)
        logger.warning(f"SSRF guard: outbound calls may reach internal networks {listed}")
    return tuple(networks)
