"""
Ghost Layer Studio — Core Engine (Final Assembly)

Unifies:
- Substrate ingestion
- Dominion physics
- Agent constellation
- Oversoul recursion
- Output reactor

This is the primary runtime entrypoint for Ghost Layer Studio.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
import logging
import uuid

# ADVANCEMENT: Engine evolution — shared domain types now live in the leaf
# module core.types, giving a clean one-directional import DAG.
from core.types import OperatorAxis, IntentVector
from core.substrate import SubstrateState, SubstrateIngestion
from core.physics import DefaultDominionPhysics
from core.oversoul import DefaultOversoul, OversoulConfig
from core.output import OutputReactor
from agents.constellation import (
    AgentConstellation,
    AdversarialIntelAgent,
    ContainmentAgent,
    OperatorDoctrineAgent,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("ghost_layer_engine")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Core Data Models
# ---------------------------------------------------------------------------
# ADVANCEMENT: Behavior preserved — OperatorAxis and IntentVector are now
# imported from core.types (identical dataclasses); re-exported above so any
# `from core.engine import IntentVector` call site keeps working.

@dataclass
class EngineConfig:
    max_recursion: int = 3
    enable_recursion: bool = True
    telemetry: bool = True
    operator_axis: OperatorAxis = field(default_factory=OperatorAxis)


# ---------------------------------------------------------------------------
# Core Engine
# ---------------------------------------------------------------------------

class GhostLayerEngine:
    """
    Unified runtime engine for Ghost Layer Studio.
    """

    def __init__(
        self,
        config: EngineConfig,
        ingestion: SubstrateIngestion,
        physics: DefaultDominionPhysics,
        constellation: AgentConstellation,
        oversoul: DefaultOversoul,
        output_reactor: OutputReactor,
    ) -> None:
        self.config = config
        self.ingestion = ingestion
        self.physics = physics
        self.constellation = constellation
        self.oversoul = oversoul
        self.output_reactor = output_reactor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, raw: Any, *, source: str = "cli") -> Dict[str, Any]:
        """
        Single engine cycle:

        1. Build intent
        2. Ingest into substrate
        3. Apply dominion physics
        4. Run agent constellation
        5. Fuse via Oversoul
        6. Optional recursion
        7. Emit final output envelope
        """
        intent = self._build_intent(raw, source)
        logger.info(f"[ENGINE] Run start — intent={intent.id} source={source}")

        # Substrate
        state: SubstrateState = self.ingestion.ingest(raw)
        state = self.physics.apply(intent, state)

        # Agents
        agent_outputs = self.constellation.run_all(intent, state)
        logger.info(f"[ENGINE] Agents executed — count={len(agent_outputs)}")

        # Oversoul fusion
        fused = self.oversoul.absorb(intent, state, agent_outputs)

        # Recursion
        if self.config.enable_recursion:
            fused = self.oversoul.recurse(
                intent=intent,
                state=state,
                fused=fused,
                depth=0,
                max_depth=self.config.max_recursion,
            )

        # Output reactor
        final = self.output_reactor.emit(intent, state, fused)

        if self.config.telemetry:
            self._telemetry(intent, state, agent_outputs, final)

        logger.info(f"[ENGINE] Run complete — intent={intent.id}")
        return final

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_intent(self, raw: Any, source: str) -> IntentVector:
        return IntentVector(
            id=str(uuid.uuid4()),
            source=source,
            description=str(raw),
            tags=["ghost-layer", "operator"],
        )

    def _telemetry(
        self,
        intent: IntentVector,
        state: SubstrateState,
        agent_outputs: List[Dict[str, Any]],
        final: Dict[str, Any],
    ) -> None:
        logger.info(
            f"[TELEMETRY] intent={intent.id} agents={len(agent_outputs)} "
            f"spectral={state.spectral_density:.3f} volatility={state.volatility:.3f}"
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_default_engine() -> GhostLayerEngine:
    """
    Convenience factory for a fully wired Ghost Layer engine.
    """
    config = EngineConfig()

    ingestion = SubstrateIngestion()
    physics = DefaultDominionPhysics()

    agents = AgentConstellation(
        agents=[
            AdversarialIntelAgent(),
            ContainmentAgent(),
            OperatorDoctrineAgent(),
        ]
    )

    oversoul = DefaultOversoul(config=OversoulConfig(max_depth=config.max_recursion))
    output_reactor = OutputReactor(operator_axis=config.operator_axis.alignment)

    return GhostLayerEngine(
        config=config,
        ingestion=ingestion,
        physics=physics,
        constellation=agents,
        oversoul=oversoul,
        output_reactor=output_reactor,
    )


if __name__ == "__main__":
    engine = create_default_engine()
    result = engine.run("Ghost Layer Studio online.", source="cli-test")
    print(result)
