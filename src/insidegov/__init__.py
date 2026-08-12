"""InsideGov multi-agent policy laboratory."""

from .cases import create_hefei_nio_world
from .engine import SimulationEngine
from .negotiation_engine import NegotiationEngine
from .scenarios import create_full_lifecycle_world, create_negotiation_world, create_talent_world
from .talent_engine import TalentSimulationEngine

__all__ = [
    "NegotiationEngine",
    "SimulationEngine",
    "TalentSimulationEngine",
    "create_full_lifecycle_world",
    "create_hefei_nio_world",
    "create_negotiation_world",
    "create_talent_world",
]
__version__ = "0.5.0"
