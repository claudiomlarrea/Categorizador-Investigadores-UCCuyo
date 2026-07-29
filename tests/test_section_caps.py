import json
from pathlib import Path

import pytest

from section_caps import (
    allocate_section_item_caps,
    capped_item_max_sum,
    section_uses_shared_pool,
)

CRITERIA_PATH = Path(__file__).resolve().parents[1] / "config" / "criteria.json"


@pytest.fixture(scope="module")
def criteria():
    with open(CRITERIA_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_allocated_caps_are_multiples_of_five(criteria):
    for sec_name, cfg in criteria["sections"].items():
        sec_max = int(cfg["max_points"])
        if sec_max <= 0:
            continue
        names = list(cfg.get("items", {}).keys())
        caps = allocate_section_item_caps(cfg, names)
        if section_uses_shared_pool(cfg):
            shared_sum = sum(v for v in caps.values() if v is not None)
            assert shared_sum == sec_max
        for name, cap in caps.items():
            if cap is None:
                assert float(cfg["items"][name].get("max_points", 0)) < 0
            elif cap > 0:
                assert cap % 5 == 0, f"{sec_name} / {name}: {cap}"


def test_direct_item_caps_are_multiples_of_five(criteria):
    for sec_name, cfg in criteria["sections"].items():
        if section_uses_shared_pool(cfg):
            continue
        sec_max = int(cfg["max_points"])
        items = cfg.get("items", {})
        cap_sum = capped_item_max_sum(cfg)
        if sec_max > 0 and cap_sum > 0:
            assert cap_sum == sec_max or cap_sum < sec_max
        for item_name, item in items.items():
            cap = int(item.get("max_points", 0))
            if cap > 0:
                assert cap % 5 == 0, f"{sec_name} / {item_name}: {cap}"
            if cap < 0:
                assert item_name in names_expected_uncapped(criteria)


def names_expected_uncapped(criteria):
    out = set()
    for cfg in criteria["sections"].values():
        for name, item in cfg.get("items", {}).items():
            if float(item.get("max_points", 0)) < 0:
                out.add(name)
    return out


def test_key_titles_are_uncapped(criteria):
    forma = criteria["sections"]["Formación académica y complementaria"]["items"]
    for name in (
        "Doctorado (finalizado)",
        "Maestría (finalizada)",
        "Especialización (finalizada)",
        "Título de grado (finalizado)",
    ):
        assert float(forma[name]["max_points"]) < 0

    prod = criteria["sections"]["Producción científica"]["items"]
    for name, item in prod.items():
        assert float(item["max_points"]) < 0, name
