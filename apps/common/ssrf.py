from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

from django.conf import settings

from apps.common.exceptions import SsrfError

BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}
ALLOWED_SCHEMES = {"http", "https"}


def _assert_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise SsrfError("Адрес не является публичным")


def validate_public_http_url(url: str, allowlist: list[str] | None = None) -> str:
    """Проверяет схему, имя и все адреса DNS. Не выполняет запрос."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SsrfError("Разрешены только схемы http и https")
    if parsed.username or parsed.password:
        raise SsrfError("URL с учётными данными запрещён")
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise SsrfError("Не указан хост")
    if host in BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise SsrfError("Хост запрещён")
    try:
        _assert_public_ip(ipaddress.ip_address(host))
    except ValueError:
        pass
    allowed = [item.strip().lower() for item in (allowlist if allowlist is not None else settings.URL_ALLOWLIST) if item]
    if allowed and host not in allowed:
        raise SsrfError("Хост вне списка разрешённых источников")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SsrfError("Не удалось разрешить имя хоста") from exc
    if not infos:
        raise SsrfError("Имя хоста не разрешилось")
    for info in infos:
        _assert_public_ip(ipaddress.ip_address(info[4][0]))
    return parsed.geturl()


def validate_redirect_target(current_url: str, location: str, allowlist: list[str] | None = None) -> str:
    if not location:
        raise SsrfError("Пустой адрес перенаправления")
    target = urljoin(current_url, location)
    return validate_public_http_url(target, allowlist)
