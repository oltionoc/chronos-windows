"""Outbound-target guard for the HTTP device adapters — SECURITY_REPORT.md
Revision 3.

`worker` receives `ip_address` from `api`'s /internal/devices and pastes it
into a URL. `api` validates that column on write (backend/app/schemas.py
DeviceHost), but `worker` is a separate service that must not depend on the
caller having done so: rows written before that validation existed are still
handed over as-is. This is a deliberate small duplicate of
backend/app/services/device_net.py — the two services share no Python
package (BLUEPRINT.md Section 2.2).
"""
import ipaddress
import re
import socket

_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                          r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")

CLOUD_HOST_SUFFIXES = ("hik-connect.com", "ezvizlife.com", "ys7.com", "hikvision.com")


def safe_host(value: str) -> str:
    """Returns a bare IP/hostname or raises. Rejects anything that could
    rewrite the URL built around it (scheme, path, query, fragment, userinfo,
    embedded port, whitespace) and any address an attendance device never
    legitimately has (loopback, link-local incl. 169.254.169.254 metadata,
    multicast, reserved)."""
    host = (value or "").strip()
    if not host:
        raise ValueError("device has no address")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _HOSTNAME_RE.match(host):
            raise ValueError(f"device address is not a bare host: {host!r}")
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        # Unresolvable: nothing to connect to anyway. Let the request itself
        # fail so the operator sees the real transport error, and so a
        # transient DNS outage doesn't look like a security rejection.
        # Matches backend/app/services/device_net.py.
        return host
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified:
            raise ValueError(f"device address {host!r} resolves to a forbidden address {addr}")
    return host


def safe_port(value) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError(f"device port out of range: {port}")
    return port


def safe_cloud_host(value: str) -> str:
    """Stricter still for hikvision_cloud: that request carries the Open
    Platform appKey/appSecret in its body, so the destination is pinned to
    Hikvision's own platform rather than any host the device row names."""
    host = safe_host(value)
    h = host.lower().rstrip(".")
    if not any(h == s or h.endswith("." + s) for s in CLOUD_HOST_SUFFIXES):
        raise ValueError(
            f"hikvision_cloud device address {host!r} is not a Hikvision Open Platform host"
        )
    return host
