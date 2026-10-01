from __future__ import annotations

from typing import Any


def normalize_constraints(constraints: dict[str, Any]) -> dict[str, Any]:
    """Align raw constraint dicts with TripConstraints field names."""
    if not constraints:
        return {}

    data = dict(constraints)

    if data.get("destination") and not data.get("destinations"):
        dest = data.pop("destination")
        if dest:
            data["destinations"] = [dest] if isinstance(dest, str) else list(dest)

    if data.get("preferences") and not data.get("activity_preferences"):
        data["activity_preferences"] = data.pop("preferences")

    return data
