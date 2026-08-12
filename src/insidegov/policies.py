from __future__ import annotations

from abc import ABC, abstractmethod

from .models import CityState, FirmState, PolicyPackage, WorldState


class DecisionPolicy(ABC):
    """Replaceable cognition layer. It proposes actions but never mutates the world."""

    @abstractmethod
    def create_offer(self, city: CityState, firm: FirmState, world: WorldState) -> PolicyPackage:
        raise NotImplementedError


class DeterministicPolicy(DecisionPolicy):
    """Transparent baseline policy for reproducible experiments and offline demos."""

    def create_offer(self, city: CityState, firm: FirmState, world: WorldState) -> PolicyPackage:
        competition = max(0, world.quarter - 1) * 1.8
        short_term_pressure = (16 - city.leadership_term_remaining) * 0.42
        affordability = max(0.35, 1 - city.fiscal_pressure)
        base = 10 + short_term_pressure + competition
        subsidy = min(city.available_budget * 0.16, base * affordability)
        equity = min(city.available_budget * 0.22, (9 + city.supply_chain * 0.11) * affordability)
        return PolicyPackage(
            city_id=city.id,
            subsidy=round(subsidy, 2),
            equity=round(equity, 2),
            land_discount=round(min(0.52, 0.18 + city.industrial_land / 3000), 3),
            credit_support=round(min(34.0, 12 + city.administrative_capacity * 0.12), 2),
            approval_speed=round(city.administrative_capacity / 100, 3),
            talent_support=round(city.talent_pool / 100, 3),
            conditions={"investment": 150.0, "jobs": 2200.0, "progress": 0.55},
        )

