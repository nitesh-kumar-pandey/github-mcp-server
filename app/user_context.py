from contextvars import ContextVar

current_login: ContextVar[str | None] = ContextVar(
    "current_login",
    default=None,
)

def set_current_login(login: str):
    current_login.set(login)

def get_current_login() -> str | None:
    return current_login.get()