"""InsideGov multi-agent policy laboratory."""

from .engine import SimulationEngine
from .scenarios import create_full_lifecycle_world

__all__ = ["SimulationEngine", "create_full_lifecycle_world"]
__version__ = "0.1.0"

