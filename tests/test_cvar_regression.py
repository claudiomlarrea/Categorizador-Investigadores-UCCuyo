"""
Tests de regresión: parseo y scoring sobre CVars de referencia.
Ejecutar: pytest tests/ -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cvar_parser import parse_cvar  # noqa: E402
from normalizer import NormalizeOptions, extract_text_from_pdf_bytes, normalize_text  # noqa: E402
from scorer import load_criteria, score_text  # noqa: E402

FIXTURES = json.loads((Path(__file__).parent / "expected_counts.json").read_text(encoding="utf-8"))
CRITERIA = load_criteria(str(ROOT / "config" / "criteria.json"))


def _resolve_pdf(spec: dict) -> Path | None:
    candidates = [ROOT / spec["path"]]
    if spec.get("path_alt"):
        candidates.append(Path(spec["path_alt"]))
    env_key = f"CVAR_{spec.get('_key', '').upper()}_PDF"
    if env_key.strip("_"):
        import os

        if os.environ.get(env_key):
            candidates.insert(0, Path(os.environ[env_key]))
    for p in candidates:
        if p.exists():
            return p
    return None


def _analyze(pdf_path: Path) -> dict:
    text = normalize_text(extract_text_from_pdf_bytes(pdf_path.read_bytes()), opts=NormalizeOptions())
    structured = parse_cvar(text)
    _, _, total, category, _ = score_text(text, CRITERIA, structured=structured)
    counts = structured["counts"]
    fin = counts.get("financiamiento", {})
    ev = structured["items"]["eventos_cyt"].get("counts", {})
    pub = structured["items"]["publicaciones"].get("counts", {})
    return {
        "category": category,
        "total": total,
        "cursos": len(structured["items"]["formacion_complementaria"].get("cursos", [])),
        "articulos": pub.get("articulos_revista", 0),
        "articulos_doi": pub.get("articulos_doi", 0),
        "libros": pub.get("libros_isbn", 0),
        "capitulos": pub.get("capitulos_libro", 0),
        "trabajos_evento": pub.get("trabajos_evento_publicados", 0),
        "premios": ev.get("premios", 0),
        "eventos": ev.get("eventos", 0),
        "investigador_proyecto": fin.get("investigador_proyecto", 0),
        "gestion": counts.get("antecedentes_gestion", 0),
    }


def _collect_cases():
    cases = []
    for key, spec in FIXTURES["samples"].items():
        spec = dict(spec)
        spec["_key"] = key
        pdf = _resolve_pdf(spec)
        if pdf is None:
            if spec.get("required"):
                cases.append(pytest.param(key, spec, None, id=f"{key}-MISSING"))
            continue
        cases.append(pytest.param(key, spec, pdf, id=key))
    return cases


@pytest.mark.parametrize("key,spec,pdf_path", _collect_cases())
def test_cvar_regression(key, spec, pdf_path):
    if pdf_path is None:
        pytest.fail(f"PDF requerido no encontrado para '{key}': {spec.get('path')}")

    result = _analyze(pdf_path)

    assert result["category"] == spec["category"], f"{key}: categoría"
    assert spec["total_min"] <= result["total"] <= spec["total_max"], (
        f"{key}: total {result['total']} fuera de [{spec['total_min']}, {spec['total_max']}]"
    )

    for field in (
        "cursos",
        "articulos",
        "libros",
        "capitulos",
        "trabajos_evento",
        "premios",
        "eventos",
        "investigador_proyecto",
        "gestion",
    ):
        expected = spec[field]
        assert result[field] == expected, f"{key}: {field} esperado {expected}, obtuvo {result[field]}"

    if "articulos_doi" in spec:
        assert result["articulos_doi"] == spec["articulos_doi"], (
            f"{key}: articulos_doi esperado {spec['articulos_doi']}, obtuvo {result['articulos_doi']}"
        )
