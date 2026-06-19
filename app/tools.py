"""
tools.py — FastMCP tool definitions.
Each tool is a plain Python function decorated with @mcp.tool().
Includes richer descriptions, P3 session-based identity, P12 new tools. (P13)
"""
from __future__ import annotations
from typing import Optional
import json
import time

from fastmcp import FastMCP

from app.config import get_settings
from app.auth import resolve_token
from app.schemas import RepoCreate, IssueCreate, PRCreate
import app.github as gh
from app.utils import resolve_full_name, pretty_json
from app.database import get_db, log_tool_call

settings = get_settings()
mcp = FastMCP(settings.mcp_server_name)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _owner_and_token(repo: str) -> tuple[str, str, str]:
    """Return (token, owner, repo_name)."""
    token = resolve_token()
    user = gh.get_authenticated_user(token)
    owner, repo_name = resolve_full_name(repo, user.login)
    return token, owner, repo_name


def _audit(login: str, tool: str, params: dict, summary: str, start_time: float = 0, success: bool = True) -> None:
    try:
        execution_ms = int((time.time() - start_time) * 1000) if start_time else 0
        with get_db() as db:
            log_tool_call(db, login or "anonymous", tool, json.dumps(params), summary, execution_ms, success)
    except Exception:
        pass  # never crash tools due to audit failure


# ---------------------------------------------------------------------------
# Repository Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def create_repository(
    name: str,
    description: str = "",
    private: bool = False,
) -> str:
    """
    Create a new GitHub repository for the authenticated user.

    Args:
        name: Repository name (e.g. 'my-project'). Will be sanitized automatically.
        description: Short description shown on GitHub.
        private: Set to true to create a private repository.

    Example: create_repository("my-api", "FastAPI backend", private=True)
    """
    t = time.time()
    token = resolve_token()
    payload = RepoCreate(name=name, description=description, private=private)
    repo = gh.create_repository(token, payload)
    _audit("", "create_repository", {"name": name}, f"Created {repo.full_name}", t)
    return pretty_json({"status": "created", "repo": repo.full_name, "url": repo.html_url, "private": repo.private})


@mcp.tool()
def get_repository(repo: str) -> str:
    """
    Get details about a GitHub repository including stars, forks, open issues, and dates.

    Args:
        repo: 'owner/repo' or just 'repo' (uses your login as owner).

    Example: get_repository("octocat/Hello-World")
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    info = gh.get_repository(token, owner, repo_name)
    _audit("", "get_repository", {"repo": repo}, info.full_name, t)
    return pretty_json(info.model_dump())


@mcp.tool()
def list_my_repositories(
    visibility: str = "all",
    sort: str = "updated",
) -> str:
    """
    List repositories belonging to the authenticated user.

    Args:
        visibility: Filter by 'all', 'public', or 'private'.
        sort: Sort by 'created', 'updated', 'pushed', or 'full_name'.
    """
    t = time.time()
    token = resolve_token()
    repos = gh.list_user_repos(token, visibility=visibility, sort=sort)
    _audit("", "list_my_repositories", {"visibility": visibility}, f"{len(repos)} repos", t)
    return pretty_json([{"name": r.name, "url": r.html_url, "private": r.private, "stars": r.stargazers_count} for r in repos])


@mcp.tool()
def search_repositories(query: str) -> str:
    """
    Search GitHub repositories by keyword, topic, language, or advanced query syntax.

    Args:
        query: GitHub search query. Examples: 'LangGraph', 'topic:machine-learning language:python',
               'stars:>1000 language:rust', 'user:torvalds'
    """
    t = time.time()
    token = resolve_token()
    result = gh.search_repositories(token, query)
    _audit("", "search_repositories", {"query": query}, f"{result.total_count} results", t)
    return pretty_json({"total_count": result.total_count, "items": [{"name": r.full_name, "url": r.html_url, "stars": r.stargazers_count, "description": r.description} for r in result.items]})


@mcp.tool()
def delete_repository(repo: str) -> str:
    """
    ⚠️ PERMANENTLY delete a GitHub repository. This action CANNOT be undone.
    All code, issues, PRs, and history will be lost.

    Args:
        repo: 'owner/repo' or just 'repo' (uses your login as owner).
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    gh.delete_repository(token, owner, repo_name)
    _audit("", "delete_repository", {"repo": repo}, f"Deleted {owner}/{repo_name}", t)
    return pretty_json({"status": "deleted", "repo": f"{owner}/{repo_name}"})


# ---------------------------------------------------------------------------
# Issue Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def create_issue(
    repo: str,
    title: str,
    body: str = "",
    labels: str = "",
    assignees: str = "",
) -> str:
    """
    Create a new issue in a GitHub repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        title: Issue title.
        body: Issue description (supports Markdown).
        labels: Comma-separated label names, e.g. 'bug,help wanted'.
        assignees: Comma-separated GitHub usernames to assign.

    Example: create_issue("my-repo", "Login button broken", "Steps to reproduce...", "bug")
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    label_list = [l.strip() for l in labels.split(",") if l.strip()]
    assignee_list = [a.strip() for a in assignees.split(",") if a.strip()]
    payload = IssueCreate(repo=repo, title=title, body=body, labels=label_list, assignees=assignee_list)
    issue = gh.create_issue(token, owner, repo_name, payload)
    _audit("", "create_issue", {"repo": repo, "title": title}, f"#{issue.number}", t)
    return pretty_json({"status": "created", "number": issue.number, "url": issue.html_url})


@mcp.tool()
def list_issues(repo: str, state: str = "open") -> str:
    """
    List issues in a GitHub repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        state: Filter by 'open', 'closed', or 'all'.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    issues = gh.list_issues(token, owner, repo_name, state=state)
    _audit("", "list_issues", {"repo": repo, "state": state}, f"{len(issues)} issues", t)
    return pretty_json([{"number": i.number, "title": i.title, "state": i.state, "url": i.html_url, "labels": i.labels} for i in issues])


@mcp.tool()
def close_issue(repo: str, issue_number: int) -> str:
    """
    Close an open issue by its number.

    Args:
        repo: 'owner/repo' or just 'repo'.
        issue_number: The issue number (shown in the URL and issue list).
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    issue = gh.close_issue(token, owner, repo_name, issue_number)
    _audit("", "close_issue", {"repo": repo, "issue": issue_number}, "closed", t)
    return pretty_json({"status": "closed", "number": issue.number, "url": issue.html_url})


# ---------------------------------------------------------------------------
# Commit Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_commits(repo: str, limit: int = 10) -> str:
    """
    Show the latest commits from a GitHub repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        limit: Number of commits to return (1–100). Default: 10.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    commits = gh.list_commits(token, owner, repo_name, per_page=min(limit, 100))
    _audit("", "list_commits", {"repo": repo}, f"{len(commits)} commits", t)
    return pretty_json([{"sha": c.sha, "message": c.message, "author": c.author, "date": c.date, "url": c.html_url} for c in commits])


# ---------------------------------------------------------------------------
# Pull Request Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def create_pull_request(
    repo: str,
    title: str,
    head: str,
    base: str = "main",
    body: str = "",
    draft: bool = False,
) -> str:
    """
    Create a pull request to merge one branch into another.

    Args:
        repo: 'owner/repo' or just 'repo'.
        title: PR title.
        head: Source branch to merge FROM (e.g. 'feature/login').
        base: Target branch to merge INTO (default: 'main').
        body: PR description (supports Markdown).
        draft: Open as draft PR if true.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    payload = PRCreate(repo=repo, title=title, body=body, head=head, base=base, draft=draft)
    pr = gh.create_pull_request(token, owner, repo_name, payload)
    _audit("", "create_pull_request", {"repo": repo, "head": head, "base": base}, f"#{pr.number}", t)
    return pretty_json({"status": "created", "number": pr.number, "url": pr.html_url, "head": pr.head, "base": pr.base})


@mcp.tool()
def list_pull_requests(repo: str, state: str = "open") -> str:
    """
    List pull requests in a repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        state: Filter by 'open', 'closed', or 'all'.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    prs = gh.list_pull_requests(token, owner, repo_name, state=state)
    _audit("", "list_pull_requests", {"repo": repo, "state": state}, f"{len(prs)} PRs", t)
    return pretty_json([{"number": p.number, "title": p.title, "state": p.state, "head": p.head, "base": p.base, "url": p.html_url} for p in prs])


# ---------------------------------------------------------------------------
# File / Content Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def read_file(repo: str, path: str, branch: str = "main") -> str:
    """
    Read the contents of a file from a GitHub repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        path: File path inside repo, e.g. 'src/index.py' or 'README.md'.
        branch: Branch to read from (default: main).
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    result = gh.read_file(token, owner, repo_name, path, ref=branch)
    _audit("", "read_file", {"repo": repo, "path": path}, f"{result['size']} bytes", t)
    return pretty_json(result)


@mcp.tool()
def upload_file(
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
) -> str:
    """
    Create or update a single file in a GitHub repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        path: Destination path in repo, e.g. 'src/hello.py'.
        content: Full UTF-8 text content of the file.
        message: Git commit message, e.g. 'Add hello.py'.
        branch: Target branch (default: main).
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    result = gh.upload_file(token, owner, repo_name, path, content, message, branch)
    _audit("", "upload_file", {"repo": repo, "path": path}, result["action"], t)
    return pretty_json(result)


@mcp.tool()
def delete_file(
    repo: str,
    path: str,
    message: str,
    branch: str = "main",
) -> str:
    """
    Delete a file from a GitHub repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        path: Path of file to delete, e.g. 'old/file.txt'.
        message: Git commit message, e.g. 'Remove old file'.
        branch: Branch to delete from (default: main).
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    result = gh.delete_file(token, owner, repo_name, path, message, branch)
    _audit("", "delete_file", {"repo": repo, "path": path}, "deleted", t)
    return pretty_json(result)


@mcp.tool()
def push_folder(
    repo: str,
    files: str,
    message: str,
    branch: str = "main",
) -> str:
    """
    Push multiple files to a GitHub repository in a single atomic commit using the Git Tree API.

    Args:
        repo: 'owner/repo' or just 'repo'.
        files: JSON object mapping file paths to their content.
               e.g. '{"src/main.py": "print(\\"hello\\")", "README.md": "# Project"}'
        message: Git commit message.
        branch: Target branch (default: main).

    Example: push_folder("my-repo", '{"index.html": "<h1>Hello</h1>"}', "Initial commit")
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    try:
        files_dict = json.loads(files)
    except json.JSONDecodeError as e:
        return pretty_json({"error": f"Invalid JSON for files parameter: {e}"})
    if not isinstance(files_dict, dict):
        return pretty_json({"error": "files must be a JSON object mapping paths to content"})
    result = gh.push_folder(token, owner, repo_name, files_dict, message, branch)
    _audit("", "push_folder", {"repo": repo, "file_count": len(files_dict)}, f"{len(files_dict)} files pushed", t)
    return pretty_json(result)


# ---------------------------------------------------------------------------
# Branch Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def create_branch(
    repo: str,
    branch: str,
    from_branch: str = "main",
) -> str:
    """
    Create a new branch in a GitHub repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        branch: Name of the new branch, e.g. 'feature/login'.
        from_branch: Source branch to branch off (default: main).
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    result = gh.create_branch(token, owner, repo_name, branch, from_branch)
    _audit("", "create_branch", {"repo": repo, "branch": branch}, "created", t)
    return pretty_json(result)


@mcp.tool()
def list_branches(repo: str) -> str:
    """
    List all branches in a GitHub repository with their latest commit SHA.

    Args:
        repo: 'owner/repo' or just 'repo'.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    branches = gh.list_branches(token, owner, repo_name)
    _audit("", "list_branches", {"repo": repo}, f"{len(branches)} branches", t)
    return pretty_json(branches)


# ---------------------------------------------------------------------------
# GitHub Actions Tools  (P12)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_workflows(repo: str) -> str:
    """
    List all GitHub Actions workflows defined in a repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    workflows = gh.list_workflows(token, owner, repo_name)
    _audit("", "list_workflows", {"repo": repo}, f"{len(workflows)} workflows", t)
    return pretty_json(workflows)


@mcp.tool()
def run_workflow(
    repo: str,
    workflow_id: str,
    ref: str = "main",
    inputs: str = "{}",
) -> str:
    """
    Manually trigger a GitHub Actions workflow dispatch event.

    Args:
        repo: 'owner/repo' or just 'repo'.
        workflow_id: Workflow filename (e.g. 'deploy.yml') or numeric ID.
        ref: Branch or tag to run the workflow on (default: main).
        inputs: JSON object of workflow inputs, e.g. '{"env": "staging"}'.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    try:
        inputs_dict = json.loads(inputs) if inputs else {}
    except json.JSONDecodeError:
        inputs_dict = {}
    result = gh.run_workflow(token, owner, repo_name, workflow_id, ref, inputs_dict)
    _audit("", "run_workflow", {"repo": repo, "workflow": workflow_id}, "dispatched", t)
    return pretty_json(result)


@mcp.tool()
def workflow_status(
    repo: str,
    workflow_id: str = "",
    limit: int = 5,
) -> str:
    """
    Get recent workflow run statuses for a repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
        workflow_id: Optional workflow filename to filter (e.g. 'ci.yml'). Omit for all workflows.
        limit: Number of runs to return (default: 5).
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    runs = gh.list_workflow_runs(token, owner, repo_name, workflow_id or None, per_page=limit)
    _audit("", "workflow_status", {"repo": repo}, f"{len(runs)} runs", t)
    return pretty_json(runs)


# ---------------------------------------------------------------------------
# Release Tools  (P12)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_releases(repo: str) -> str:
    """
    List GitHub releases for a repository.

    Args:
        repo: 'owner/repo' or just 'repo'.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    releases = gh.list_releases(token, owner, repo_name)
    _audit("", "list_releases", {"repo": repo}, f"{len(releases)} releases", t)
    return pretty_json(releases)


@mcp.tool()
def create_release(
    repo: str,
    tag_name: str,
    name: str,
    body: str = "",
    draft: bool = False,
    prerelease: bool = False,
) -> str:
    """
    Create a new GitHub release (and tag).

    Args:
        repo: 'owner/repo' or just 'repo'.
        tag_name: Git tag for the release, e.g. 'v1.2.0'.
        name: Human-readable release title, e.g. 'Version 1.2.0'.
        body: Release notes (supports Markdown).
        draft: Create as a draft (not published) if true.
        prerelease: Mark as a pre-release if true.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    result = gh.create_release(token, owner, repo_name, tag_name, name, body, draft, prerelease)
    _audit("", "create_release", {"repo": repo, "tag": tag_name}, result["html_url"], t)
    return pretty_json(result)


# ---------------------------------------------------------------------------
# Code Search Tool  (P12)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_code(query: str) -> str:
    """
    Search code across GitHub repositories.

    Args:
        query: Code search query. Examples: 'addClass in:file language:js',
               'octocat repo:github/linguist', 'filename:config.yml'.

    Note: GitHub rate-limits unauthenticated code search heavily.
    """
    t = time.time()
    token = resolve_token()
    result = gh.search_code(token, query)
    _audit("", "search_code", {"query": query}, f"{result['total_count']} results", t)
    return pretty_json(result)


# ---------------------------------------------------------------------------
# Organization Tools  (P12)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_org_repos(org: str) -> str:
    """
    List public repositories in a GitHub organization.

    Args:
        org: GitHub organization name, e.g. 'microsoft' or 'facebook'.
    """
    t = time.time()
    token = resolve_token()
    repos = gh.list_org_repos(token, org)
    _audit("", "list_org_repos", {"org": org}, f"{len(repos)} repos", t)
    return pretty_json(repos)


@mcp.tool()
def list_org_members(org: str) -> str:
    """
    List public members of a GitHub organization.

    Args:
        org: GitHub organization name.
    """
    t = time.time()
    token = resolve_token()
    members = gh.list_org_members(token, org)
    _audit("", "list_org_members", {"org": org}, f"{len(members)} members", t)
    return pretty_json(members)


# ---------------------------------------------------------------------------
# Discussions Tool  (P12)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_discussions(repo: str) -> str:
    """
    List GitHub Discussions in a repository (requires Discussions to be enabled).

    Args:
        repo: 'owner/repo' or just 'repo'.
    """
    t = time.time()
    token, owner, repo_name = _owner_and_token(repo)
    discussions = gh.list_discussions(token, owner, repo_name)
    _audit("", "list_discussions", {"repo": repo}, f"{len(discussions)} discussions", t)
    return pretty_json(discussions)


# ---------------------------------------------------------------------------
# Auth / User Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def whoami() -> str:
    """
    Return profile information about the currently authenticated GitHub user.
    """
    token = resolve_token()
    user = gh.get_authenticated_user(token)
    return pretty_json(user.model_dump())