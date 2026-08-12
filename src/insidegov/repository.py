from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock

from .models import WorldState
from .serde import world_from_dict


class WorldRepository:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("INSIDEGOV_DATA_DIR", ".insidegov/worlds"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()

    def save(self, world: WorldState) -> None:
        target = self.root / f"{world.id}.json"
        temporary = target.with_suffix(".tmp")
        with self.lock:
            temporary.write_text(json.dumps(world.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(target)

    def save_snapshot(self, world: WorldState) -> Path:
        """Persist an immutable quarter snapshot beside the current world file."""
        snapshot_root = self.root / "snapshots" / world.id
        snapshot_root.mkdir(parents=True, exist_ok=True)
        target = snapshot_root / f"q{world.quarter:02d}.json"
        temporary = target.with_suffix(".tmp")
        with self.lock:
            temporary.write_text(
                json.dumps(world.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(target)
        return target

    def load_snapshot(self, world_id: str, quarter: int) -> WorldState | None:
        target = self.root / "snapshots" / world_id / f"q{quarter:02d}.json"
        if not target.exists():
            return None
        with self.lock:
            return world_from_dict(json.loads(target.read_text(encoding="utf-8")))

    def snapshot_quarters(self, world_id: str) -> list[int]:
        root = self.root / "snapshots" / world_id
        return sorted(int(path.stem[1:]) for path in root.glob("q*.json"))

    def load(self, world_id: str) -> WorldState | None:
        target = self.root / f"{world_id}.json"
        if not target.exists():
            return None
        with self.lock:
            return world_from_dict(json.loads(target.read_text(encoding="utf-8")))

    def list(self) -> list[dict]:
        results = []
        for target in sorted(self.root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True):
            raw = json.loads(target.read_text(encoding="utf-8"))
            results.append({key: raw.get(key) for key in ["id", "name", "quarter", "phase", "parent_id", "policy_mode", "model_name"]})
        return results
