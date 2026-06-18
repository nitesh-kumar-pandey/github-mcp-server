"""
schemas.py — Pydantic models for request / response validation.
"""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


# ---------------------------------------------------------------------------
# GitHub resource schemas
# ---------------------------------------------------------------------------

class RepoCreate(BaseModel):
    name: str = Field(..., description="Repository name")
    description: str = Field("", description="Short description")
    private: bool = Field(False, description="Whether the repo is private")
    auto_init: bool = Field(True, description="Initialise with a README")


class RepoInfo(BaseModel):
    id: int
    name: str
    full_name: str
    description: Optional[str]
    private: bool
    html_url: str
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    created_at: str
    updated_at: str


class IssueCreate(BaseModel):
    repo: str = Field(..., description="Repo name (owner/repo or just repo)")
    title: str = Field(..., description="Issue title")
    body: str = Field("", description="Issue body / description")
    labels: List[str] = Field(default_factory=list, description="Labels to apply")
    assignees: List[str] = Field(default_factory=list, description="GitHub usernames to assign")


class IssueInfo(BaseModel):
    number: int
    title: str
    body: Optional[str]
    state: str
    html_url: str
    user: str
    labels: List[str]
    created_at: str


class CommitInfo(BaseModel):
    sha: str
    message: str
    author: str
    date: str
    html_url: str


class PRCreate(BaseModel):
    repo: str = Field(..., description="Repo name (owner/repo or just repo)")
    title: str = Field(..., description="Pull request title")
    body: str = Field("", description="Pull request description")
    head: str = Field(..., description="Branch to merge FROM")
    base: str = Field("main", description="Branch to merge INTO")
    draft: bool = Field(False, description="Open as draft PR")


class PRInfo(BaseModel):
    number: int
    title: str
    body: Optional[str]
    state: str
    html_url: str
    head: str
    base: str
    user: str
    created_at: str


class SearchResult(BaseModel):
    total_count: int
    items: List[RepoInfo]


class FileContent(BaseModel):
    path: str
    content: str
    sha: str
    html_url: str
    size: int


class BranchInfo(BaseModel):
    name: str
    sha: str


# ---------------------------------------------------------------------------
# Auth / token schemas
# ---------------------------------------------------------------------------

class OAuthToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    scope: str = ""


class UserInfo(BaseModel):
    login: str
    id: int
    avatar_url: str
    html_url: str
    name: Optional[str]
    email: Optional[str]
    public_repos: int
    followers: int


# ---------------------------------------------------------------------------
# DB model schema
# ---------------------------------------------------------------------------

class TokenRecord(BaseModel):
    id: int
    github_login: str
    access_token: str
    scope: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
