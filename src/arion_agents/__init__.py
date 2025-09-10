"""arion_agents package.

Initial scaffolding for LLM-powered agents. Extend as features land.
"""

__all__ = [
    "hello",
]


def hello(name: str = "world") -> str:
    return f"Hello, {name}!"
