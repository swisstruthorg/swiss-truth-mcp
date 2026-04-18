"""
SSRF-Schutz — verhindert Webhook-Registrierung auf private/interne IP-Ranges.

Blockierte Bereiche:
- 127.0.0.0/8   (loopback)
- 10.0.0.0/8    (RFC 1918 private)
- 172.16.0.0/12 (RFC 1918 private)
- 192.168.0.0/16 (RFC 1918 private)
- 169.254.0.0/16 (link-local / AWS metadata)
- ::1/128        (IPv6 loopback)
- fc00::/7       (IPv6 unique local)
- 0.0.0.0/8     (This network)
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("0.0.0.0/8"),
]


def _is_private(host: str) -> bool:
    """Gibt True zurück wenn host auf eine private/interne IP-Adresse zeigt."""
    # Direkte IP-Adresse
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        pass

    # Hostname — per DNS auflösen (blockiert localhost-Aliase)
    try:
        resolved = socket.gethostbyname(host)
        addr = ipaddress.ip_address(resolved)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except (socket.gaierror, ValueError):
        # DNS-Fehler: im Zweifel ablehnen (fail-closed)
        return True


def validate_webhook_url(url: str) -> None:
    """
    Validiert eine Webhook-URL gegen SSRF-Patterns.
    Wirft ValueError wenn die URL auf eine private/interne Adresse zeigt.

    Args:
        url: Vollständige URL (z.B. 'https://example.com/webhook')

    Raises:
        ValueError: wenn die URL auf eine private IP-Range zeigt
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if not host:
        raise ValueError(f"Ungültige URL — kein Hostname: {url!r}")

    # Entferne IPv6-Klammern für direkte Adress-Erkennung
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    if _is_private(host):
        raise ValueError(
            f"Webhook-URL abgelehnt: {host!r} zeigt auf eine private/interne IP-Range. "
            "Nur öffentlich erreichbare URLs sind erlaubt."
        )
