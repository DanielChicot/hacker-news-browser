"""Display helpers used by the templates."""

from urllib.parse import urlparse

HN_HOST = "news.ycombinator.com"
OWNER_HOSTS = {"github.com", "gitlab.com", "codeberg.org"}


def domain_of(url: str | None) -> str:
    if not url:
        return HN_HOST
    parsed = urlparse(url)
    host = parsed.netloc.removeprefix("www.")
    if host in OWNER_HOSTS:
        owner = parsed.path.strip("/").split("/")[0]
        if owner:
            return f"{host}/{owner}"
    return host


def age_label(created_at: int, now: int) -> str:
    seconds = max(now - created_at, 0)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def hn_item_url(story_id: int) -> str:
    return f"https://{HN_HOST}/item?id={story_id}"
