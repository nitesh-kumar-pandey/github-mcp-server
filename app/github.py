"""
github.py — Thin wrapper around the GitHub REST API v3.
All methods accept a token string so they are stateless and easy to test.
Includes expanded tool coverage: Actions, Releases, Organizations, Code Search, Discussions. (P12)
"""
from __future__ import annotations
from typing import Any
import requests

from app.utils import github_headers, raise_for_github, resolve_full_name, sanitize_repo_name
from app.schemas import (
    RepoCreate, RepoInfo, IssueCreate, IssueInfo,
    CommitInfo, PRCreate, PRInfo, SearchResult, UserInfo,
)

GITHUB_API = "https://api.github.com"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def get_authenticated_user(token: str) -> UserInfo:
    r = requests.get(f"{GITHUB_API}/user", headers=github_headers(token), timeout=10)
    raise_for_github(r)
    d = r.json()
    return UserInfo(
        login=d["login"],
        id=d["id"],
        avatar_url=d["avatar_url"],
        html_url=d["html_url"],
        name=d.get("name"),
        email=d.get("email"),
        public_repos=d.get("public_repos", 0),
        followers=d.get("followers", 0),
    )


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------

def create_repository(token: str, payload: RepoCreate) -> RepoInfo:
    body: dict[str, Any] = {
        "name": sanitize_repo_name(payload.name),
        "description": payload.description,
        "private": payload.private,
        "auto_init": payload.auto_init,
    }
    r = requests.post(f"{GITHUB_API}/user/repos", json=body, headers=github_headers(token), timeout=15)
    raise_for_github(r)
    return _parse_repo(r.json())


def get_repository(token: str, owner: str, repo: str) -> RepoInfo:
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=github_headers(token), timeout=10)
    raise_for_github(r)
    return _parse_repo(r.json())


def list_user_repos(token: str, visibility: str = "all", sort: str = "updated", per_page: int = 30) -> list[RepoInfo]:
    params = {"visibility": visibility, "sort": sort, "per_page": per_page}
    r = requests.get(f"{GITHUB_API}/user/repos", headers=github_headers(token), params=params, timeout=15)
    raise_for_github(r)
    return [_parse_repo(d) for d in r.json()]


def search_repositories(token: str, query: str, per_page: int = 10) -> SearchResult:
    params = {"q": query, "per_page": per_page}
    r = requests.get(f"{GITHUB_API}/search/repositories", headers=github_headers(token), params=params, timeout=15)
    raise_for_github(r)
    d = r.json()
    return SearchResult(
        total_count=d["total_count"],
        items=[_parse_repo(item) for item in d["items"]],
    )


def delete_repository(token: str, owner: str, repo: str) -> None:
    r = requests.delete(f"{GITHUB_API}/repos/{owner}/{repo}", headers=github_headers(token), timeout=15)
    raise_for_github(r)


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

def create_issue(token: str, owner: str, repo: str, payload: IssueCreate) -> IssueInfo:
    body: dict[str, Any] = {
        "title": payload.title,
        "body": payload.body,
        "labels": payload.labels,
        "assignees": payload.assignees,
    }
    r = requests.post(f"{GITHUB_API}/repos/{owner}/{repo}/issues", json=body, headers=github_headers(token), timeout=15)
    raise_for_github(r)
    return _parse_issue(r.json())


def list_issues(token: str, owner: str, repo: str, state: str = "open", per_page: int = 20) -> list[IssueInfo]:
    params = {"state": state, "per_page": per_page}
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/issues", headers=github_headers(token), params=params, timeout=15)
    raise_for_github(r)
    return [_parse_issue(d) for d in r.json() if "pull_request" not in d]


def close_issue(token: str, owner: str, repo: str, issue_number: int) -> IssueInfo:
    r = requests.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}",
        json={"state": "closed"},
        headers=github_headers(token),
        timeout=15,
    )
    raise_for_github(r)
    return _parse_issue(r.json())


# ---------------------------------------------------------------------------
# Commits
# ---------------------------------------------------------------------------

def list_commits(token: str, owner: str, repo: str, per_page: int = 10) -> list[CommitInfo]:
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits",
        headers=github_headers(token),
        params={"per_page": per_page},
        timeout=15,
    )
    raise_for_github(r)
    return [_parse_commit(d) for d in r.json()]


# ---------------------------------------------------------------------------
# Pull Requests
# ---------------------------------------------------------------------------

def create_pull_request(token: str, owner: str, repo: str, payload: PRCreate) -> PRInfo:
    body: dict[str, Any] = {
        "title": payload.title,
        "body": payload.body,
        "head": payload.head,
        "base": payload.base,
        "draft": payload.draft,
    }
    r = requests.post(f"{GITHUB_API}/repos/{owner}/{repo}/pulls", json=body, headers=github_headers(token), timeout=15)
    raise_for_github(r)
    return _parse_pr(r.json())


def list_pull_requests(token: str, owner: str, repo: str, state: str = "open", per_page: int = 20) -> list[PRInfo]:
    params = {"state": state, "per_page": per_page}
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls", headers=github_headers(token), params=params, timeout=15)
    raise_for_github(r)
    return [_parse_pr(d) for d in r.json()]


# ---------------------------------------------------------------------------
# File / Contents API
# ---------------------------------------------------------------------------

def read_file(token: str, owner: str, repo: str, path: str, ref: str = "main") -> dict:
    import base64
    params = {"ref": ref}
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", headers=github_headers(token), params=params, timeout=10)
    raise_for_github(r)
    d = r.json()
    content = base64.b64decode(d["content"]).decode("utf-8", errors="replace")
    return {"path": d["path"], "content": content, "sha": d["sha"], "html_url": d["html_url"], "size": d["size"]}


def upload_file(token: str, owner: str, repo: str, path: str, content: str, message: str, branch: str = "main") -> dict:
    import base64
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    sha = None
    try:
        existing = read_file(token, owner, repo, path, ref=branch)
        sha = existing["sha"]
    except RuntimeError:
        pass
    body: dict = {"message": message, "content": encoded, "branch": branch}
    if sha:
        body["sha"] = sha
    r = requests.put(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", json=body, headers=github_headers(token), timeout=15)
    raise_for_github(r)
    d = r.json()
    action = "updated" if sha else "created"
    return {"action": action, "path": path, "html_url": d["content"]["html_url"], "commit_sha": d["commit"]["sha"][:7]}


def delete_file(token: str, owner: str, repo: str, path: str, message: str, branch: str = "main") -> dict:
    existing = read_file(token, owner, repo, path, ref=branch)
    body = {"message": message, "sha": existing["sha"], "branch": branch}
    r = requests.delete(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", json=body, headers=github_headers(token), timeout=15)
    raise_for_github(r)
    return {"action": "deleted", "path": path, "commit_sha": r.json()["commit"]["sha"][:7]}


def push_folder(token: str, owner: str, repo: str, files: dict[str, str], message: str, branch: str = "main") -> dict:
    import base64
    ref_r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{branch}", headers=github_headers(token), timeout=10)
    raise_for_github(ref_r)
    base_commit_sha = ref_r.json()["object"]["sha"]
    commit_r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/git/commits/{base_commit_sha}", headers=github_headers(token), timeout=10)
    raise_for_github(commit_r)
    base_tree_sha = commit_r.json()["tree"]["sha"]
    tree_items = []
    for file_path, file_content in files.items():
        blob_r = requests.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/blobs",
            json={"content": file_content, "encoding": "utf-8"},
            headers=github_headers(token),
            timeout=15,
        )
        raise_for_github(blob_r)
        tree_items.append({"path": file_path, "mode": "100644", "type": "blob", "sha": blob_r.json()["sha"]})
    tree_r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees",
        json={"base_tree": base_tree_sha, "tree": tree_items},
        headers=github_headers(token),
        timeout=15,
    )
    raise_for_github(tree_r)
    new_tree_sha = tree_r.json()["sha"]
    new_commit_r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/commits",
        json={"message": message, "tree": new_tree_sha, "parents": [base_commit_sha]},
        headers=github_headers(token),
        timeout=15,
    )
    raise_for_github(new_commit_r)
    new_commit_sha = new_commit_r.json()["sha"]
    update_r = requests.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs/heads/{branch}",
        json={"sha": new_commit_sha},
        headers=github_headers(token),
        timeout=15,
    )
    raise_for_github(update_r)
    return {"action": "pushed", "files_pushed": len(files), "branch": branch, "commit_sha": new_commit_sha[:7]}


# ---------------------------------------------------------------------------
# Branch API
# ---------------------------------------------------------------------------

def create_branch(token: str, owner: str, repo: str, branch: str, from_branch: str = "main") -> dict:
    ref_r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{from_branch}", headers=github_headers(token), timeout=10)
    raise_for_github(ref_r)
    sha = ref_r.json()["object"]["sha"]
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
        json={"ref": f"refs/heads/{branch}", "sha": sha},
        headers=github_headers(token),
        timeout=15,
    )
    raise_for_github(r)
    return {"action": "created", "branch": branch, "from": from_branch, "sha": sha[:7]}


def list_branches(token: str, owner: str, repo: str) -> list[dict]:
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/branches", headers=github_headers(token), timeout=10)
    raise_for_github(r)
    return [{"name": b["name"], "sha": b["commit"]["sha"][:7]} for b in r.json()]


# ---------------------------------------------------------------------------
# GitHub Actions  (P12)
# ---------------------------------------------------------------------------

def list_workflows(token: str, owner: str, repo: str) -> list[dict]:
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows", headers=github_headers(token), timeout=15)
    raise_for_github(r)
    return [{"id": w["id"], "name": w["name"], "state": w["state"], "path": w["path"]} for w in r.json().get("workflows", [])]


def run_workflow(token: str, owner: str, repo: str, workflow_id: str, ref: str = "main", inputs: dict | None = None) -> dict:
    body: dict = {"ref": ref}
    if inputs:
        body["inputs"] = inputs
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
        json=body,
        headers=github_headers(token),
        timeout=15,
    )
    raise_for_github(r)
    return {"action": "dispatched", "workflow_id": workflow_id, "ref": ref}


def list_workflow_runs(token: str, owner: str, repo: str, workflow_id: str | None = None, per_page: int = 10) -> list[dict]:
    if workflow_id:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
    else:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs"
    r = requests.get(url, headers=github_headers(token), params={"per_page": per_page}, timeout=15)
    raise_for_github(r)
    runs = r.json().get("workflow_runs", [])
    return [{"id": run["id"], "name": run["name"], "status": run["status"], "conclusion": run["conclusion"], "created_at": run["created_at"], "html_url": run["html_url"]} for run in runs]


# ---------------------------------------------------------------------------
# Releases  (P12)
# ---------------------------------------------------------------------------

def list_releases(token: str, owner: str, repo: str, per_page: int = 10) -> list[dict]:
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/releases", headers=github_headers(token), params={"per_page": per_page}, timeout=15)
    raise_for_github(r)
    return [{"id": rel["id"], "tag_name": rel["tag_name"], "name": rel["name"], "draft": rel["draft"], "prerelease": rel["prerelease"], "html_url": rel["html_url"], "created_at": rel["created_at"]} for rel in r.json()]


def create_release(token: str, owner: str, repo: str, tag_name: str, name: str, body: str = "", draft: bool = False, prerelease: bool = False) -> dict:
    payload = {"tag_name": tag_name, "name": name, "body": body, "draft": draft, "prerelease": prerelease}
    r = requests.post(f"{GITHUB_API}/repos/{owner}/{repo}/releases", json=payload, headers=github_headers(token), timeout=15)
    raise_for_github(r)
    d = r.json()
    return {"id": d["id"], "tag_name": d["tag_name"], "name": d["name"], "html_url": d["html_url"]}


# ---------------------------------------------------------------------------
# Code Search  (P12)
# ---------------------------------------------------------------------------

def search_code(token: str, query: str, per_page: int = 10) -> dict:
    params = {"q": query, "per_page": per_page}
    r = requests.get(f"{GITHUB_API}/search/code", headers=github_headers(token), params=params, timeout=15)
    raise_for_github(r)
    d = r.json()
    return {
        "total_count": d["total_count"],
        "items": [{"path": item["path"], "repo": item["repository"]["full_name"], "html_url": item["html_url"]} for item in d.get("items", [])],
    }


# ---------------------------------------------------------------------------
# Organizations  (P12)
# ---------------------------------------------------------------------------

def list_org_repos(token: str, org: str, per_page: int = 30) -> list[dict]:
    r = requests.get(f"{GITHUB_API}/orgs/{org}/repos", headers=github_headers(token), params={"per_page": per_page}, timeout=15)
    raise_for_github(r)
    return [{"name": repo["name"], "full_name": repo["full_name"], "private": repo["private"], "html_url": repo["html_url"], "description": repo.get("description")} for repo in r.json()]


def list_org_members(token: str, org: str) -> list[dict]:
    r = requests.get(f"{GITHUB_API}/orgs/{org}/members", headers=github_headers(token), timeout=15)
    raise_for_github(r)
    return [{"login": m["login"], "html_url": m["html_url"]} for m in r.json()]


# ---------------------------------------------------------------------------
# Discussions  (P12)
# ---------------------------------------------------------------------------

def list_discussions(token: str, owner: str, repo: str) -> list[dict]:
    """List repository discussions via GraphQL."""
    query = """
    query($owner: String!, $repo: String!, $first: Int!) {
      repository(owner: $owner, name: $repo) {
        discussions(first: $first) {
          nodes {
            id
            title
            url
            createdAt
            author { login }
            category { name }
          }
        }
      }
    }
    """
    payload = {"query": query, "variables": {"owner": owner, "repo": repo, "first": 20}}
    r = requests.post(
        "https://api.github.com/graphql",
        json=payload,
        headers=github_headers(token),
        timeout=15,
    )
    raise_for_github(r)
    nodes = r.json().get("data", {}).get("repository", {}).get("discussions", {}).get("nodes", [])
    return [{"id": n["id"], "title": n["title"], "url": n["url"], "author": n["author"]["login"], "category": n["category"]["name"], "created_at": n["createdAt"]} for n in nodes]


# ---------------------------------------------------------------------------
# Private parsers
# ---------------------------------------------------------------------------

def _parse_repo(d: dict) -> RepoInfo:
    return RepoInfo(
        id=d["id"],
        name=d["name"],
        full_name=d["full_name"],
        description=d.get("description"),
        private=d["private"],
        html_url=d["html_url"],
        stargazers_count=d.get("stargazers_count", 0),
        forks_count=d.get("forks_count", 0),
        open_issues_count=d.get("open_issues_count", 0),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


def _parse_issue(d: dict) -> IssueInfo:
    return IssueInfo(
        number=d["number"],
        title=d["title"],
        body=d.get("body"),
        state=d["state"],
        html_url=d["html_url"],
        user=d["user"]["login"],
        labels=[lbl["name"] for lbl in d.get("labels", [])],
        created_at=d["created_at"],
    )


def _parse_commit(d: dict) -> CommitInfo:
    commit = d["commit"]
    return CommitInfo(
        sha=d["sha"][:7],
        message=commit["message"].split("\n")[0],
        author=commit["author"]["name"],
        date=commit["author"]["date"],
        html_url=d["html_url"],
    )


def _parse_pr(d: dict) -> PRInfo:
    return PRInfo(
        number=d["number"],
        title=d["title"],
        body=d.get("body"),
        state=d["state"],
        html_url=d["html_url"],
        head=d["head"]["ref"],
        base=d["base"]["ref"],
        user=d["user"]["login"],
        created_at=d["created_at"],
    )
