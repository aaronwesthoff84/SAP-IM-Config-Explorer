from __future__ import annotations


def select_dispatch_candidates(
    ordered_items: list[dict],
    active_items: list[dict],
    maximum_active: int = 2,
) -> list[dict]:
    available = max(0, maximum_active - len(active_items))
    selected: list[dict] = []
    active_areas = {item.get("primary_area", "unknown") for item in active_items}
    for item in ordered_items:
        if len(selected) >= available:
            break
        area = item.get("primary_area", "unknown")
        if not item.get("eligible", False):
            continue
        if area == "unknown" and (active_items or selected):
            continue
        if area in active_areas:
            continue
        selected.append(item)
        active_areas.add(area)
    return selected
