"""Route table for the API server."""

from typing import Callable

Routes: dict[tuple[str, str], Callable] = {}


def route(method: str, path: str):
    def register(fn: Callable) -> Callable:
        Routes[(method.upper(), path)] = fn
        return fn

    return register


def resolve(method: str, path: str) -> Callable | None:
    return Routes.get((method.upper(), path))
