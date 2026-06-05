"""
Equivalencia e interpretación entre categorías Anexo VII y grilla UCCuyo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from report import category_label


def load_category_equivalence(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_equivalence_table(config: Dict[str, Any]) -> pd.DataFrame:
    anexo = config.get("anexo_vii", {})
    grilla = config.get("grilla_uccuyo", {})
    rows: List[Dict[str, Any]] = []
    for cat in config.get("categorias", []):
        umbral_grilla = cat.get("grilla_umbral_orientativo")
        rows.append(
            {
                "Categoría": cat["code"],
                "Denominación": cat["label"],
                "Mín. Anexo VII": cat.get("anexo_min_points", 0),
                "Escala Anexo VII": f"0–{anexo.get('max_points', 3550)}",
                "Umbral orientativo grilla UCCuyo": (
                    umbral_grilla if umbral_grilla is not None else "— (Consejo)"
                ),
                "Escala grilla UCCuyo": f"0–{grilla.get('max_points_orientativo', 600)} (orientativo)",
                "Descripción Anexo VII": cat.get("descripcion_anexo", ""),
            }
        )
    return pd.DataFrame(rows)


def build_reference_cases_table(config: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for caso in config.get("casos_referencia", []):
        rows.append(
            {
                "Caso": caso.get("docente", caso.get("id", "")),
                "Grilla UCCuyo (total)": caso.get("grilla_total", "—"),
                "Categoría grilla": caso.get("grilla_categoria", "—"),
                "Anexo VII auto (total)": caso.get("anexo_total", "—"),
                "Categoría Anexo VII": caso.get("anexo_categoria", "—"),
                "¿Coincide?": "Sí" if caso.get("coincide") else "No",
                "Nota": caso.get("nota", ""),
            }
        )
    return pd.DataFrame(rows)


def _category_rank(code: str) -> int:
    order = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}
    return order.get((code or "").upper(), 99)


def explain_category_discrepancy(
    auto_category: str,
    grilla_category: Optional[str],
    auto_total: Optional[float] = None,
    grilla_total: Optional[float] = None,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    if not grilla_category:
        return ""
    auto_u = (auto_category or "").upper()
    grilla_u = grilla_category.upper()
    if auto_u == grilla_u:
        for hint in (config or {}).get("discrepancia_hints", []):
            if hint.get("when") == "misma_categoria":
                return hint.get("texto", "Categorías coincidentes.")
        return "Categorías coincidentes en ambos sistemas."

    parts: List[str] = []
    if auto_total is not None:
        parts.append(f"Anexo VII automático: {auto_total:.0f} pts → {category_label(auto_u)}.")
    if grilla_total is not None:
        parts.append(f"Grilla UCCuyo: {grilla_total:.0f} pts → Categoría {grilla_u}.")

    if _category_rank(auto_u) > _category_rank(grilla_u):
        for hint in (config or {}).get("discrepancia_hints", []):
            if hint.get("when") == "auto_V_grilla_IV" and auto_u == "V" and grilla_u == "IV":
                parts.append(hint.get("texto", ""))
                break
        else:
            parts.append(
                "La grilla UCCuyo puede asignar una categoría superior cuando el perfil "
                "destaca docencia, gestión u otros bloques no dominantes en el Anexo VII."
            )
    else:
        parts.append(
            "El Anexo VII automático ubica en una categoría más alta que la grilla manual; "
            "revisar ocurrencias ítem por ítem."
        )

    for hint in (config or {}).get("discrepancia_hints", []):
        if hint.get("when") == "anexo_menor_que_grilla":
            parts.append(hint.get("texto", ""))
            break

    return " ".join(p for p in parts if p)


def enrich_category_comparison(
    auto_category: str,
    grilla: Optional[Dict[str, Any]] = None,
    auto_total: Optional[float] = None,
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    if config_path and Path(config_path).exists():
        config = load_category_equivalence(config_path)

    manual = (grilla or {}).get("category_manual") or ""
    manual_u = manual.upper() if manual else ""
    auto_u = (auto_category or "").upper()
    match = manual_u == auto_u if manual_u else None

    grilla_total = (grilla or {}).get("total_manual")
    interpretation = explain_category_discrepancy(
        auto_u,
        manual_u or None,
        auto_total=auto_total,
        grilla_total=grilla_total,
        config=config,
    )

    row = {
        "Automático (Anexo VII)": auto_u,
        "Etiqueta Anexo VII": category_label(auto_u).split("—", 1)[-1].strip(),
        "Manual (grilla UCCuyo)": manual_u or "—",
        "Etiqueta manual": (grilla or {}).get("category_label_manual", ""),
        "¿Coincide nominal?": "Sí" if match else ("No" if match is False else "—"),
        "Puntaje Anexo VII": round(auto_total, 1) if auto_total is not None else "—",
        "Puntaje grilla UCCuyo": grilla_total if grilla_total is not None else "—",
        "Interpretación": interpretation or "—",
    }
    return row


def category_from_total(total: float, config: Dict[str, Any], scale: str = "anexo_vii") -> str:
    cats = sorted(
        config.get("categorias", []),
        key=lambda c: c.get("anexo_min_points", 0) if scale == "anexo_vii" else c.get("grilla_umbral_orientativo", 0) or 0,
        reverse=True,
    )
    for cat in cats:
        if scale == "anexo_vii":
            threshold = cat.get("anexo_min_points", 0)
        else:
            threshold = cat.get("grilla_umbral_orientativo")
            if threshold is None:
                continue
        if total >= threshold:
            return cat["code"]
    return "VI"
