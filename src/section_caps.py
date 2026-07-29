from typing import Any, Dict, List, Optional


def _floor_to_multiple_of_5(value: float) -> int:
    return int(value // 5) * 5


def item_has_cap(item_cfg: Dict[str, Any]) -> bool:
    """max_points < 0 ⇒ sin tope de ítem (sólo aplica el máx. del apartado)."""
    return float(item_cfg.get("max_points", 0)) >= 0


def capped_item_max_sum(section_cfg: Dict[str, Any]) -> float:
    return sum(
        float(it.get("max_points", 0))
        for it in section_cfg.get("items", {}).values()
        if item_has_cap(it)
    )


def allocate_section_item_caps(
    section_cfg: Dict[str, Any], item_names: List[str]
) -> Dict[str, Optional[int]]:
    """Reparte el tope de sección entre ítems con tope (múltiplos de 5).

    Ítems con max_points < 0 quedan sin tope de ítem (None) y no entran al
    reparto; el máx. del apartado sigue limitando el subtotal.
    """
    sec_max = int(round(float(section_cfg.get("max_points", 0))))
    items_cfg = section_cfg.get("items", {})
    weights: Dict[str, float] = {}
    caps: Dict[str, Optional[int]] = {}
    for name in item_names:
        item = items_cfg.get(name, {})
        raw = float(item.get("max_points", 0))
        if raw < 0:
            caps[name] = None
            weights[name] = 0.0
        else:
            weights[name] = raw
            caps[name] = int(raw)

    scoring_names = [name for name in item_names if weights[name] > 0]
    total = sum(weights[name] for name in scoring_names)
    if total <= sec_max or total <= 0:
        return caps

    raw_shares = {name: weights[name] / total * sec_max for name in scoring_names}
    share_caps = {name: _floor_to_multiple_of_5(raw_shares[name]) for name in scoring_names}
    remainder = sec_max - sum(share_caps.values())
    if remainder > 0:
        order = sorted(
            scoring_names,
            key=lambda n: (raw_shares[n] - share_caps[n], weights[n]),
            reverse=True,
        )
        for i in range(remainder // 5):
            share_caps[order[i % len(order)]] += 5
    for name in scoring_names:
        caps[name] = share_caps[name]
    return caps


def section_effective_max(section_cfg: Dict[str, Any]) -> int:
    """Máximo puntuable: tope de sección (ítems sin tope usan ese cupo)."""
    return int(round(float(section_cfg.get("max_points", 0))))


def section_uses_shared_pool(section_cfg: Dict[str, Any]) -> bool:
    sec_max = float(section_cfg.get("max_points", 0))
    item_sum = capped_item_max_sum(section_cfg)
    return item_sum > sec_max + 1e-9
