import io
from typing import Any, Dict, List, Optional

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

CATEGORY_LABELS = {
    "I": "Investigador Superior",
    "II": "Investigador Principal",
    "III": "Investigador Independiente",
    "IV": "Investigador Adjunto",
    "V": "Investigador Asistente",
    "VI": "Becario de Iniciación",
}


def category_label(code: str) -> str:
    name = CATEGORY_LABELS.get(code, "")
    return f"Categoría {code} — {name}" if name else f"Categoría {code}"


def allocate_section_display_caps(
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


def results_to_dataframe(item_results, criteria: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    display_caps: Dict[tuple, float] = {}
    if criteria:
        sections = criteria.get("sections", {})
        by_section: Dict[str, List[str]] = {}
        for r in item_results:
            if r.item not in by_section.setdefault(r.section, []):
                by_section[r.section].append(r.item)
        for sec_name, names in by_section.items():
            cfg = sections.get(sec_name, {})
            for item_name, cap in allocate_section_display_caps(cfg, names).items():
                display_caps[(sec_name, item_name)] = cap

    rows = []
    for r in item_results:
        tope = display_caps.get((r.section, r.item), r.item_max_points)
        rows.append(
            {
                "Sección": r.section,
                "Ítem": r.item,
                "Ocurrencias": r.count,
                "Puntos unitarios": r.unit_points,
                "Puntaje bruto": r.raw_points,
                "Tope en sección": tope if criteria else r.item_max_points,
                "Puntaje (tope aplicado)": int(r.capped_item_points),
                "Evidencia (1er match)": r.evidence,
            }
        )
    return pd.DataFrame(rows)


def section_totals_dataframe(section_totals: Dict[str, float]) -> pd.DataFrame:
    df = pd.DataFrame([{"Sección": k, "Subtotal": v} for k, v in section_totals.items()])
    return df.sort_values("Subtotal", ascending=False)


def export_excel(
    df_items: pd.DataFrame,
    df_sec_tot: pd.DataFrame,
    total: float,
    category: str,
    criteria: Dict[str, Any],
) -> bytes:
    excel_out = io.BytesIO()
    with pd.ExcelWriter(excel_out, engine="xlsxwriter") as writer:
        for section_name in criteria.get("sections", {}).keys():
            df_s = df_items[df_items["Sección"] == section_name].copy()
            if df_s.empty:
                continue
            df_s.to_excel(writer, sheet_name=section_name[:31], index=False)

        resumen = df_sec_tot.copy()
        resumen.loc[len(resumen)] = ["TOTAL", total]
        resumen.loc[len(resumen)] = ["CATEGORÍA", category_label(category)]
        resumen.to_excel(writer, sheet_name="RESUMEN", index=False)

    excel_out.seek(0)
    return excel_out.getvalue()


def export_word(
    df_items: pd.DataFrame,
    df_sec_tot: pd.DataFrame,
    total: float,
    category: str,
    cat_desc: str,
    filename: str,
    criteria: Dict[str, Any],
    include_evidence: bool = False,
) -> bytes:
    doc = Document()
    title = doc.add_paragraph("Universidad Católica de Cuyo")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle = doc.add_paragraph("Secretaría de Investigación — Categorización de Investigadores")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("Informe de valoración de CVar (Anexo VII)").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")
    doc.add_paragraph(f"Archivo evaluado: {filename}")
    doc.add_paragraph(f"Puntaje total: {total:.1f}")
    doc.add_paragraph(f"Categoría alcanzada: {category_label(category)}")
    if cat_desc:
        doc.add_paragraph(cat_desc)

    doc.add_paragraph("")
    doc.add_heading("Totales por sección", level=2)
    for _, row in df_sec_tot.iterrows():
        doc.add_paragraph(f"- {row['Sección']}: {float(row['Subtotal']):.1f}")

    scoring_sections = [
        name
        for name, cfg in criteria.get("sections", {}).items()
        if float(cfg.get("max_points", 0)) > 0
    ]

    for section_name in scoring_sections:
        doc.add_heading(section_name, level=2)
        df_s = df_items[df_items["Sección"] == section_name].copy()
        cols = ["Ítem", "Ocurrencias", "Puntaje (tope aplicado)", "Tope en sección"]
        if include_evidence:
            cols.append("Evidencia (1er match)")

        if df_s.empty:
            doc.add_paragraph("Sin ítems detectados.")
            continue

        tbl = doc.add_table(rows=1, cols=len(cols))
        hdr = tbl.rows[0].cells
        for i, col in enumerate(cols):
            hdr[i].text = col

        for _, r in df_s.iterrows():
            cells = tbl.add_row().cells
            for i, col in enumerate(cols):
                cells[i].text = str(r.get(col, ""))

        sec_rows = df_sec_tot[df_sec_tot["Sección"] == section_name]
        if not sec_rows.empty:
            doc.add_paragraph(f"Subtotal sección: {float(sec_rows['Subtotal'].values[0]):.1f}")

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()
