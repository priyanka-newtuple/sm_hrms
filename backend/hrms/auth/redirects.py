"""Safe post-login redirects — only same-origin relative paths."""

from urllib.parse import urlparse


def safe_next_path(raw: str | None) -> str | None:
    if not raw:
        return None
    path = raw.strip()
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return None
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        return None
    return path
