"""
user_context.py — Request-scoped GitHub login, set by middleware before tool
execution so tools don't need an explicit `login` parameter on every call.
"""
from contextvars import ContextVar

current_login: ContextVar[str | None] = ContextVar("current_login", default=None)


def set_current_login(login: str | None) -> None:
    current_login.set(login)


def get_current_login() -> str | None:
    return current_login.get()


def clear_current_login() -> None:
    current_login.set(None)
