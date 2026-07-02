from typing import Any, Dict, List


def allocate_section_item_caps(
    section_cfg: Dict[str, Any], item_names: List[str]
) -> Dict[str, int]:
    """Reparte el tope de sección entre ítems (enteros) cuando los topes parciales lo superan."""
    sec_max = int(round(float(section_cfg.get("max_points", 0))))
    items_cfg = section_cfg.get("items", {})
    weights = {
        name: float(items_cfg.get(name, {}).get("max_points", 0)) for name in item_names
    }
    total = sum(weights.values())
    if total <= sec_max or total <= 0:
        return {name: int(weights[name]) for name in item_names}

    raw_shares = {name: weights[name] / total * sec_max for name in item_names}
    caps = {name: int(raw_shares[name]) for name in item_names}
    remainder = sec_max - sum(caps.values())
    if remainder > 0:
        order = sorted(
            item_names,
            key=lambda n: (raw_shares[n] - caps[n], weights[n]),
            reverse=True,
        )
        for i in range(remainder):
            caps[order[i % len(order)]] += 1
    return caps


def section_effective_max(section_cfg: Dict[str, Any]) -> int:
    """Máximo puntuable: tope de sección o suma de topes por ítem si es menor."""
    sec_max = int(round(float(section_cfg.get("max_points", 0))))
    item_sum = sum(
        float(it.get("max_points", 0)) for it in section_cfg.get("items", {}).values()
    )
    if 0 < item_sum < sec_max:
        return int(item_sum)
    return sec_max
