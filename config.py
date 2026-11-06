"""Configuration and environment settings for AI Deal & Lead Radar."""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("radar.config")

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

raw_admin_ids = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS: set[int] = set()
if raw_admin_ids:
    for item in raw_admin_ids.split(","):
        cleaned = item.strip()
        if cleaned.isdigit():
            ADMIN_IDS.add(int(cleaned))
        elif cleaned.startswith("-") and cleaned[1:].isdigit():
            ADMIN_IDS.add(int(cleaned))

GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY", "").strip() or None
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

DB_PATH: str = os.getenv("DB_PATH", "radar_state.db").strip()
EXPORT_DIR: str = os.getenv("EXPORT_DIR", "exports").strip()
CHECK_INTERVAL_SECONDS: int = int(
    os.getenv("CHECK_INTERVAL_SECONDS", os.getenv("POLL_INTERVAL_SECONDS", "300"))
)
POLL_INTERVAL_SECONDS: int = CHECK_INTERVAL_SECONDS
HTTP_TIMEOUT: float = float(os.getenv("HTTP_TIMEOUT", "15.0"))
DEFAULT_SCORE_THRESHOLD: int = int(
    os.getenv("DEFAULT_SCORE_THRESHOLD", os.getenv("MIN_ALERT_SCORE", "60"))
)
MIN_ALERT_SCORE: int = DEFAULT_SCORE_THRESHOLD

FORBIDDEN_EXTENSIONS: tuple[str, ...] = (
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".bin",
    ".scr",
    ".vbs",
    ".msi",
    ".dll",
    ".com",
    ".ps1",
    ".apk",
    ".elf",
)

FORBIDDEN_HOSTNAMES: set[str] = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "0",
    "127.1",
    "127.0.1",
}


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate a URL against SSRF attack vectors and dangerous protocols.

    Args:
        url: The candidate URL string.

    Returns:
        A tuple of (is_safe, error_reason).
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or invalid"

    trimmed = url.strip()
    if trimmed.startswith("internal://"):
        return True, "OK"

    try:
        parsed = urlparse(trimmed)
    except Exception as exc:
        return False, f"Malformed URL: {exc}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Forbidden URL scheme '{parsed.scheme}'. Only http and https are allowed."

    path_lower = parsed.path.lower()
    for ext in FORBIDDEN_EXTENSIONS:
        if path_lower.endswith(ext):
            return False, f"Forbidden file extension in target URL: {ext}"

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname in target URL"

    host_lower = hostname.lower()
    if host_lower in FORBIDDEN_HOSTNAMES:
        return False, f"Access to restricted hostname '{host_lower}' is forbidden"

    if host_lower.endswith((".localhost", ".local", ".internal", ".lan")):
        return False, f"Access to internal domain zone '{host_lower}' is forbidden"

    try:
        ip = ipaddress.ip_address(host_lower)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Access to private/reserved IP address '{ip}' is forbidden"
    except ValueError:
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                sockaddr = item[4]
                resolved_ip_str = sockaddr[0]
                resolved_ip = ipaddress.ip_address(resolved_ip_str)
                if (
                    resolved_ip.is_private
                    or resolved_ip.is_loopback
                    or resolved_ip.is_link_local
                    or resolved_ip.is_reserved
                    or resolved_ip.is_multicast
                ):
                    return (
                        False,
                        f"Domain '{hostname}' resolves to private/reserved IP '{resolved_ip}'",
                    )
        except socket.gaierror:
            return False, f"Could not resolve domain name '{hostname}'"
        except Exception as exc:
            return False, f"DNS resolution check failed: {exc}"

    return True, "OK"


def validate_config() -> None:
    """Validate mandatory application configuration variables."""
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is not configured in environment variables.")
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS is empty; no users will be authorized to access the bot.")
    if not GEMINI_API_KEY:
        logger.info(
            "GEMINI_API_KEY is not configured; system will use deterministic heuristic scoring."
        )
