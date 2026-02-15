from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    if raw.startswith("/downloads/"):
        return raw.split("?", 1)[0]

    if not raw.startswith(("http://", "https://")):
        return raw

    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw

    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    # Remove volatile tracking params while keeping stable query semantics.
    kept = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):
        key = (k or "").strip()
        if key.lower().startswith("utm_"):
            continue
        kept.append((key, v))
    query = urlencode(sorted(kept), doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def same_url(left: str, right: str) -> bool:
    return normalize_url(left) == normalize_url(right)
