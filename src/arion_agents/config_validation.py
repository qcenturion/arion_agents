"""Validation helpers for configuration edits.

These checks run before persisting configuration updates to ensure
networks remain runnable. They are intentionally lightweight so they can
be executed on every edit request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlmodel import Session, select

from .config_models import Agent, Network


@dataclass
class NetworkConstraintError(Exception):
    """Raised when a configuration edit would violate network constraints."""

    message: str

    def __str__(self) -> str:  # pragma: no cover - defensive, mirrors Exception
        return self.message


def _iter_agents(db: Session, network_id: int) -> Iterable[Agent]:
    statement = select(Agent).where(Agent.network_id == network_id)
    return db.exec(statement)


def validate_network_constraints(db: Session, network_id: int) -> None:
    """Validate invariants for the given network.

    Current rules:
      * If the network has any agents, at least one must allow RESPOND.
      * No more than one agent per network may be marked as the default.
    """

    agents = list(_iter_agents(db, network_id))
    if not agents:
        # Allow empty networks so teams can stage agents incrementally.
        return

    respond_capable = [agent for agent in agents if bool(agent.allow_respond)]
    if not respond_capable:
        raise NetworkConstraintError(
            "Network must include at least one agent that can RESPOND."
        )

    default_agents = [agent for agent in agents if bool(agent.is_default)]
    if len(default_agents) > 1:
        keys = ", ".join(sorted({agent.key for agent in default_agents}))
        raise NetworkConstraintError(
            f"Multiple default agents configured ({keys}); mark a single default agent."
        )

    # Validate force_respond settings
    network = db.get(Network, network_id)
    if network and network.additional_data:
        force_respond = network.additional_data.get("force_respond")
        force_respond_agent = network.additional_data.get("force_respond_agent")
        if force_respond:
            if not force_respond_agent:
                raise NetworkConstraintError(
                    "If force_respond is enabled, force_respond_agent must be set."
                )
            agent_keys = {agent.key for agent in agents}
            if force_respond_agent not in agent_keys:
                raise NetworkConstraintError(
                    f"force_respond_agent '{force_respond_agent}' is not a valid agent in this network."
                )
