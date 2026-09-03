"""Fetches an audio file from a director-supplied URL.

Runs server-side (not in the browser) to avoid CORS entirely, but that means
this code is a classic SSRF surface: a malicious link could point at an
internal/private address. _validate_host is a best-effort mitigation (it
doesn't close the DNS-rebinding gap between the check and the actual
connection), not a complete one - good enough for a low-traffic MVP behind
authenticated endpoints, not a substitute for network-level egress controls
in a higher-stakes deployment.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
from urllib.parse import parse_qs, urlparse

import requests

MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 60
CHUNK_SIZE = 256 * 1024

DRIVE_ID_PATTERNS = [
    re.compile(r"/d/([a-zA-Z0-9_-]{10,})"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]{10,})"),
]


class LinkFetchError(ValueError):
    pass


def _is_public_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_host(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise LinkFetchError(f"Could not resolve host: {hostname}") from exc
    if not infos:
        raise LinkFetchError(f"Could not resolve host: {hostname}")
    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            raise LinkFetchError(
                "That link points to a private/internal network address, which isn't allowed."
            )


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise LinkFetchError("Link must start with http:// or https://")
    if not parsed.hostname:
        raise LinkFetchError("That doesn't look like a valid URL.")
    _validate_host(parsed.hostname)
    return parsed.hostname


def _drive_file_id(url: str) -> str | None:
    parsed = urlparse(url)
    if "drive.google.com" not in parsed.netloc and "docs.google.com" not in parsed.netloc:
        return None
    for pattern in DRIVE_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def _resolve_download_url(url: str) -> str:
    file_id = _drive_file_id(url)
    if file_id:
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return url


def _extension_from_headers(response: requests.Response, fallback_path: str) -> str:
    content_disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename="?([^";]+)"?', content_disposition)
    if match:
        ext = os.path.splitext(match.group(1))[1]
        if ext:
            return ext

    ext = os.path.splitext(fallback_path)[1]
    if ext and len(ext) <= 6:
        return ext

    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    return {
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/webm": ".webm",
        "audio/aac": ".aac",
    }.get(content_type, ".audio")


def _drive_confirm_token(response: requests.Response) -> str | None:
    for name, value in response.cookies.items():
        if name.startswith("download_warning"):
            return value
    match = re.search(r'confirm=([0-9A-Za-z_-]+)', response.text[:200_000])
    return match.group(1) if match else None


def fetch_audio_from_url(url: str) -> tuple[bytes, str]:
    _validate_url(url)
    download_url = _resolve_download_url(url)
    is_drive = download_url != url

    session = requests.Session()
    response = session.get(download_url, stream=True, timeout=DOWNLOAD_TIMEOUT_S)

    if is_drive and response.headers.get("content-type", "").startswith("text/html"):
        token = _drive_confirm_token(response)
        if not token:
            raise LinkFetchError(
                "Couldn't fetch that Google Drive file automatically - it may be too large "
                "for Drive's direct-download link, or not shared with 'Anyone with the link'. "
                "Try downloading it and using the file upload option instead."
            )
        response = session.get(download_url, params={"confirm": token}, stream=True, timeout=DOWNLOAD_TIMEOUT_S)

    final_host = urlparse(response.url).hostname
    if final_host:
        _validate_host(final_host)

    if response.status_code >= 400:
        raise LinkFetchError(f"That link returned an error (HTTP {response.status_code}).")

    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
        raise LinkFetchError("That file is too large (max 300MB).")

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise LinkFetchError("That file is too large (max 300MB).")
        chunks.append(chunk)

    if total == 0:
        raise LinkFetchError("That link didn't return any file content.")

    data = b"".join(chunks)
    ext = _extension_from_headers(response, urlparse(url).path)
    return data, ext
