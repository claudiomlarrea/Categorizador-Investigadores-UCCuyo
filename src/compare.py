"""
Comparación entre puntaje automático (Anexo VII) y grilla manual UCCuyo.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from category_equivalence import enrich_category_comparison, load_category_equivalence
from grilla_parser import load_grilla_mapping


def _sum_anexo_sections(section_totals: Dict[str, float], names: List[str]) -> float:
    return sum(float(section_totals.get(n, 0.0)) for n in names)


def _match_auto_items(
    df_items: pd.DataFrame,
    section_keywords: List[str],
    item_keywords: List[str],
) -> pd.DataFrame:
    if df_items.empty:
        return df_items
    mask = pd.Series(False, index=df_items.index)
    for sk in section_keywords:
        mask |= df_items["Sección"].str.lower().str.contains(sk.lower(), na=False)
    sub = df_items[mask].copy()
    if not item_keywords:
        return sub
    imask = pd.Series(False, index=sub.index)
    for ik in item_keywords:
        imask |= sub["Ítem"].str.lower().str.contains(ik.lower(), na=False)
    return sub[imask]


def compare_category(
    auto_category: str,
    grilla: Dict[str, Any],
    *,
    auto_total: Optional[float] = None,
    equivalence_path: Optional[str] = None,
) -> Dict[str, Any]:
    return enrich_category_comparison(
        auto_category,
        grilla,
        auto_total=auto_total,
        config_path=equivalence_path,
    )


def compare_sections(
    section_totals: Dict[str, float],
    grilla: Dict[str, Any],
    mapping: Dict[str, Any],
    threshold: float = 10.0,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    manual_sections = grilla.get("section_scores", {})

    for entry in mapping.get("grilla_sections", []):
        key = entry["grilla_key"]
        label = entry["grilla_labels"][0].title()
        manual_score = manual_sections.get(key)
        auto_score = _sum_anexo_sections(section_totals, entry.get("anexo_sections", []))

        diff = None
        estado = "—"
        if manual_score is not None:
            diff = round(auto_score - manual_score, 1)
            estado = "OK (escalas distintas)" if abs(diff) <= threshold else "Revisar mapeo/escala"

        rows.append(
            {
                "Bloque grilla": label,
                "Puntaje manual (grilla UCCuyo)": manual_score if manual_score is not None else "—",
                "Puntaje auto (Anexo VII)": round(auto_score, 1),
                "Diferencia": diff if diff is not None else "—",
                "Secciones Anexo VII sumadas": ", ".join(entry.get("anexo_sections", [])),
                "Estado": estado,
            }
        )
    return pd.DataFrame(rows)


def _annotation_manual_count(text: str, rule: Dict[str, Any]) -> Optional[int]:
    if rule.get("fixed_count") is not None:
        if re.search(rule["pattern"], text, re.I):
            return int(rule["fixed_count"])
        return 0
    m = re.search(rule["pattern"], text, re.I)
    if not m:
        return 0
    for g in m.groups():
        if g is not None and str(g).isdigit():
            return int(g)
    if rule.get("presence_count") is not None:
        return int(rule["presence_count"])
    return 0


def _structured_count(
    rule_id: str,
    structured: Optional[Dict[str, Any]],
    *,
    grilla: Optional[Dict[str, Any]] = None,
    rule: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    if not structured:
        return None
    counts = structured.get("counts", {})
    items = structured.get("items", {})
    if rule_id == "cursos":
        cursos = items.get("formacion_complementaria", {}).get("cursos", [])
        if cursos:
            return len(cursos)
        return int(counts.get("cursos_con_horas", 0)) + int(counts.get("cursos_sin_horas", 0))
    if rule_id == "proyecto_auxiliar":
        fin = counts.get("financiamiento", {})
        ann_text = ""
        if grilla:
            ann_text = "\n".join(a["texto"] for a in grilla.get("annotations", []))
        if rule and ann_text and re.search(rule["pattern"], ann_text, re.I) and re.search(r"finalizad", ann_text, re.I):
            return int(fin.get("investigador_proyecto_finalizado", 0))
        return int(fin.get("investigador_proyecto", 0))
    if rule_id == "evento_organizadora":
        ev = items.get("eventos_cyt", {}).get("counts", {})
        return int(ev.get("organizador", counts.get("eventos_organizador", 0)))
    if rule_id == "evento_asistente":
        ev = items.get("eventos_cyt", {}).get("counts", {})
        return int(ev.get("asistente", counts.get("eventos_asistente", 0)))
    if rule_id == "evento_expositora":
        ev = items.get("eventos_cyt", {}).get("counts", {})
        ap = items.get("actividades_profesionales", {}).get("counts", {})
        return int(ev.get("expositora", counts.get("eventos_expositora", 0))) + int(
            ap.get("expositora", counts.get("actividades_expositora", 0))
        )
    if rule_id == "gestion_asistente":
        ant = items.get("antecedentes_cyt", {}).get("entradas", [])
        return sum(
            1
            for e in ant
            if e.get("rol") == "gestion" and re.search(r"\basistente\b", e.get("texto", ""), re.I)
        )
    return None


def compare_annotations(
    df_items: pd.DataFrame,
    grilla: Dict[str, Any],
    mapping: Dict[str, Any],
    structured: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    full_text = "\n".join(a["texto"] for a in grilla.get("annotations", []))

    for rule in mapping.get("annotation_rules", []):
        manual_count = _annotation_manual_count(full_text, rule)
        if manual_count is None:
            continue

        auto_df = _match_auto_items(
            df_items,
            rule.get("anexo_section_keywords", []),
            rule.get("anexo_item_keywords", []),
        )
        auto_count = int(auto_df["Ocurrencias"].sum()) if not auto_df.empty else 0
        struct_count = _structured_count(rule["id"], structured, grilla=grilla, rule=rule)
        if struct_count is not None and struct_count > 0:
            auto_count = struct_count
        elif struct_count is not None and auto_count == 0:
            auto_count = struct_count
        auto_points = float(auto_df["Puntaje (tope aplicado)"].sum()) if not auto_df.empty else 0.0
        manual_points = None
        for ann in grilla.get("annotations", []):
            if re.search(rule["pattern"], ann["texto"], re.I):
                manual_points = ann.get("puntos_manuales")
                break

        diff = auto_count - manual_count
        rows.append(
            {
                "Regla": rule["id"],
                "Descripción grilla": rule["pattern"][:60],
                "Ocurrencias manual": manual_count,
                "Ocurrencias auto": auto_count,
                "Δ ocurrencias": diff,
                "Puntos manual (anotado)": manual_points if manual_points is not None else "—",
                "Puntos auto (Anexo VII)": round(auto_points, 1),
                "Estado": "OK" if diff == 0 else ("Revisar" if abs(diff) >= 1 else "Cercano"),
                "Ítems auto relacionados": ", ".join(auto_df["Ítem"].head(3).tolist()) if not auto_df.empty else "—",
            }
        )

    return pd.DataFrame(rows)


def compare_items_detail(
    df_items: pd.DataFrame,
    grilla: Dict[str, Any],
    criteria: Dict[str, Any],
    min_points: float = 0.0,
) -> pd.DataFrame:
    """Ítems Anexo VII con puntaje > 0 vs anotaciones de la grilla (referencia textual)."""
    rows: List[Dict[str, Any]] = []
    ann_text = "\n".join(a["texto"].lower() for a in grilla.get("annotations", []))

    scoring_sections = [
        n for n, cfg in criteria.get("sections", {}).items() if float(cfg.get("max_points", 0)) > 0
    ]

    for _, r in df_items.iterrows():
        if r["Sección"] not in scoring_sections:
            continue
        pts = float(r["Puntaje (tope aplicado)"])
        if pts <= min_points and int(r["Ocurrencias"]) == 0:
            continue

        item_l = r["Ítem"].lower()
        hint = ""
        for ann in grilla.get("annotations", []):
            t = ann["texto"].lower()
            if any(w in t for w in item_l.split()[:3] if len(w) > 4):
                hint = ann["texto"][:120]
                break

        rows.append(
            {
                "Sección Anexo VII": r["Sección"],
                "Ítem": r["Ítem"],
                "Ocurrencias auto": int(r["Ocurrencias"]),
                "Puntaje auto": pts,
                "Anotación grilla relacionada": hint or "—",
                "Nota": "Comparar ocurrencias con detalle en grilla manual",
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Puntaje auto", "Ocurrencias auto"], ascending=False)
    return df


def compare_totals(
    auto_total: float,
    auto_category: str,
    grilla: Dict[str, Any],
) -> pd.DataFrame:
    manual_total = grilla.get("total_manual")
    return pd.DataFrame(
        [
            {
                "Concepto": "Puntaje total",
                "Automático (Anexo VII)": round(auto_total, 1),
                "Manual (grilla UCCuyo)": manual_total if manual_total is not None else "—",
                "Nota": "Las grillas UCCuyo usan otra escala; comparar categoría y ocurrencias.",
            },
            {
                "Concepto": "Categoría",
                "Automático (Anexo VII)": auto_category,
                "Manual (grilla UCCuyo)": grilla.get("category_manual") or "—",
                "Nota": grilla.get("category_label_manual", ""),
            },
        ]
    )


def build_comparison_report(
    df_items: pd.DataFrame,
    section_totals: Dict[str, float],
    auto_total: float,
    auto_category: str,
    grilla: Dict[str, Any],
    criteria: Dict[str, Any],
    mapping_path: str,
    structured: Optional[Dict[str, Any]] = None,
    equivalence_path: Optional[str] = None,
) -> Dict[str, Any]:
    mapping = load_grilla_mapping(mapping_path)
    equiv_config = {}
    if equivalence_path and Path(equivalence_path).exists():
        equiv_config = load_category_equivalence(equivalence_path)
    return {
        "resumen": compare_totals(auto_total, auto_category, grilla),
        "categoria": compare_category(
            auto_category,
            grilla,
            auto_total=auto_total,
            equivalence_path=equivalence_path,
        ),
        "secciones": compare_sections(section_totals, grilla, mapping),
        "anotaciones": compare_annotations(df_items, grilla, mapping, structured=structured),
        "items_auto": compare_items_detail(df_items, grilla, criteria),
        "grilla_meta": grilla.get("meta", {}),
        "equivalence_config": equiv_config,
    }


def export_comparison_excel(report: Dict[str, Any]) -> bytes:
    from category_equivalence import build_equivalence_table, build_reference_cases_table

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        report["resumen"].to_excel(writer, sheet_name="Resumen", index=False)
        pd.DataFrame([report["categoria"]]).to_excel(writer, sheet_name="Categoría", index=False)
        equiv = report.get("equivalence_config") or {}
        if equiv:
            build_equivalence_table(equiv).to_excel(writer, sheet_name="Equivalencia", index=False)
            build_reference_cases_table(equiv).to_excel(writer, sheet_name="Casos referencia", index=False)
        report["secciones"].to_excel(writer, sheet_name="Secciones", index=False)
        if not report["anotaciones"].empty:
            report["anotaciones"].to_excel(writer, sheet_name="Anotaciones", index=False)
        if not report["items_auto"].empty:
            report["items_auto"].to_excel(writer, sheet_name="Ítems automático", index=False)
    out.seek(0)
    return out.getvalue()
