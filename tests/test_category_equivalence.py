"""Tests de equivalencia UCCuyo vs Anexo VII."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from category_equivalence import (  # noqa: E402
    build_equivalence_table,
    build_reference_cases_table,
    enrich_category_comparison,
    explain_category_discrepancy,
    load_category_equivalence,
)

EQUIV_PATH = str(ROOT / "config" / "category_equivalence.json")


@pytest.fixture(scope="module")
def config():
    return load_category_equivalence(EQUIV_PATH)


def test_equivalence_table_has_six_categories(config):
    df = build_equivalence_table(config)
    assert len(df) == 6
    assert set(df["Categoría"]) == {"I", "II", "III", "IV", "V", "VI"}


def test_reference_cases_include_cali(config):
    df = build_reference_cases_table(config)
    assert not df.empty
    cali = df[df["Caso"].str.contains("Cali", case=False, na=False)]
    assert len(cali) == 1
    assert cali.iloc[0]["¿Coincide?"] == "No"


def test_cali_discrepancy_explanation(config):
    text = explain_category_discrepancy("V", "IV", auto_total=285, grilla_total=496, config=config)
    assert "285" in text
    assert "496" in text
    assert "IV" in text or "Adjunto" in text


def test_enrich_category_comparison_cali(config):
    grilla = {"category_manual": "IV", "category_label_manual": "ADJUNTO", "total_manual": 496.0}
    row = enrich_category_comparison("V", grilla, auto_total=285.0, config_path=EQUIV_PATH)
    assert row["¿Coincide nominal?"] == "No"
    assert row["Interpretación"] != "—"
