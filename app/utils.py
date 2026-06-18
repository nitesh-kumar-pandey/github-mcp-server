"""
utils.py — Shared helpers used across the application.
"""
from __future__ import annotations
import re
import json
from typing import Any


def resolve_full_name(repo: str, default_owner: str) -> tuple[str, str]:
    """
    Given a repo string that is either 'owner/repo' or just 'repo',
    return (owner, repo_name).

    Examples
    --------
    >>> resolve_full_name("alice/my-repo", "alice")
    ('alice', 'my-repo')
    >>> resolve_full_name("my-repo", "alice")
    ('alice', 'my-repo')
    """
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return owner.strip(), name.strip()
    return default_owner, repo.strip()


def sanitize_repo_name(name: str) -> str:
    """
    GitHub repo names may only contain alphanumerics, hyphens, underscores,
    and dots.  Spaces are replaced with hyphens; invalid chars are stripped.
    """
    name = name.strip().replace(" ", "-")
    name = re.sub(r"[^A-Za-z0-9._-]", "", name)
    return name or "unnamed-repo"


def truncate(text: str, max_len: int = 120) -> str:
    """Return text truncated to max_len characters with an ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def pretty_json(obj: Any) -> str:
    """Serialise an object to indented JSON string."""
    return json.dumps(obj, indent=2, default=str)


def github_headers(token: str) -> dict[str, str]:
    """Standard headers for GitHub REST API v3 requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-mcp-server/1.0",
    }


def raise_for_github(response: Any) -> None:
    """
    Raise a descriptive RuntimeError when the GitHub API returns an error
    status code, including the error message from the JSON body.
    """
    if response.status_code >= 400:
        try:
            detail = response.json().get("message", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(
            f"GitHub API error {response.status_code}: {detail}"
        )
