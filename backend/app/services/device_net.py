"""Outbound-target hardening for device connections — SECURITY_REPORT.md
Revision 3 (2026-09-16 multi-vendor device pass).

`devices.ip_address` stopped being a Postgres `INET` in migration 0009 and is
now a free-text string that both `api` (POST /devices/{id}/test-connection)
and `worker` (the Hikvision adapters) concatenate into an outbound HTTP URL.
An unvalidated string there is not just "an IP or a hostname" — it can carry
a path, a query, a fragment or userinfo and take over the whole URL, and it
can point the request at loopback / link-local / cloud-metadata addresses.
These helpers constrain it to a bare host and keep the request off addresses
no attendance device ever legitimately lives on.

`worker/worker/adapters/_target.py` deliberately carries a small copy of the
same rules: `worker` is a separate service that shares no Python package with
`api` (BLUEPRINT.md Section 2.2), and it must re-check rather than trust the
values `api` hands it.
"""
import ipaddress
import re
import socket

# A bare host: IPv4/IPv6 literal or DNS name. No scheme, path, query,
# fragment, userinfo, port or whitespace — every one of those lets the caller
# rewrite the URL the adapter builds around it.
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                          r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")

# Hikvision Open Platform / Hik-Connect endpoints. `hikvision_cloud` devices
# put the *cloud API host* in ip_address, and that request carries the
# appKey/appSecret in its body — so unlike a LAN device address it must not be
# free-form, or repointing the row turns the credentials into an exfiltration
# primitive.
CLOUD_HOST_SUFFIXES = (
    "hik-connect.com",
    "ezvizlife.com",
    "ys7.com",
    "hikvision.com",
)


def validate_device_host(value: str) -> str:
    """Schema-level validator for `devices.ip_address`. Returns the cleaned
    host or raises ValueError."""
    host = (value or "").strip()
    if not host:
        raise ValueError("must not be empty")
    if len(host) > 253:
        raise ValueError("is too long")
    # IPv6 literals are accepted bare (no brackets) — the adapters build
    # http://{host}:{port}, and a bracketed literal would also smuggle
    # characters, so normalise on the bare form and reject the rest.
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(host):
        raise ValueError(
            "must be a bare IP address or hostname — no scheme, port, path, "
            "credentials or whitespace"
        )
    return host


def is_cloud_host(host: str) -> bool:
    h = host.strip().lower().rstrip(".")
    return any(h == suffix or h.endswith("." + suffix) for suffix in CLOUD_HOST_SUFFIXES)


def assert_cloud_host(host: str) -> None:
    if not is_cloud_host(host):
        raise ValueError(
            "a hikvision_cloud device's address must be a Hikvision Open "
            "Platform host (e.g. open.hik-connect.com)"
        )


def assert_safe_target(host: str) -> None:
    """Reject outbound targets no real attendance device lives on: loopback,
    link-local (incl. the 169.254.169.254 cloud-metadata endpoint), multicast,
    reserved and unspecified addresses. RFC1918/private ranges stay allowed —
    that is exactly where a LAN device sits."""
    validate_device_host(host)
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        # Unresolvable: let the connection attempt itself fail and report.
        return
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified:
            raise ValueError(f"address {addr} is not a permitted device address")
