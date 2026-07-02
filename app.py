import base64
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
SRC_DIR = APP_DIR / "src"
CONFIG_DIR = APP_DIR / "config"
sys.path.insert(0, str(SRC_DIR))

from normalizer import (  # noqa: E402
    NormalizeOptions,
    build_docx_bytes,
    extract_sections,
    extract_text_from_doc_bytes,
    extract_text_from_docx_bytes,
    extract_text_from_pdf_bytes,
    normalize_text,
    parse_formacion_academica,
)
from report import (  # noqa: E402
    category_label,
    export_excel,
    export_word,
    results_to_dataframe,
    section_totals_dataframe,
)
from section_caps import section_effective_max  # noqa: E402
from category_equivalence import (  # noqa: E402
    build_equivalence_table,
    build_reference_cases_table,
    load_category_equivalence,
)
from compare import build_comparison_report, export_comparison_excel  # noqa: E402
from cvar_parser import audit_summary_rows, parse_cvar, structured_to_json  # noqa: E402
from grilla_parser import parse_grilla  # noqa: E402
from scorer import load_criteria, score_text  # noqa: E402

CRITERIA_PATH = str(CONFIG_DIR / "criteria.json")
GRILLA_MAPPING_PATH = str(CONFIG_DIR / "grilla_mapping.json")
EQUIVALENCE_PATH = str(CONFIG_DIR / "category_equivalence.json")
_ESCUDO_REMOTE_URL = (
    "https://raw.githubusercontent.com/claudiomlarrea/valorador_informes_finales/"
    "main/assets/escudo_uccuyo.png"
)

_UCCI_GLOBAL_CSS = """
<style>
:root {
    --ucc-green: #00664d;
    --ucc-green-dark: #00523e;
    --ucc-accent: #28a745;
    --ucc-page-bg: #E6E6E6;
    --ucc-sidebar-bg: #262730;
    --ucc-text: #262730;
    --ucc-heading-card: #2c3838;
    --ucc-lead-muted: #5f6b6f;
}
.stApp { background-color: var(--ucc-page-bg); }
header[data-testid="stHeader"] {
    background: var(--ucc-page-bg) !important;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
div[data-testid="stDecoration"] {
    height: 3px !important;
    background: linear-gradient(90deg, var(--ucc-green-dark) 0%, var(--ucc-green) 50%, var(--ucc-green-dark) 100%) !important;
}
.block-container {
    padding-top: 2rem !important;
}
section[data-testid="stSidebar"] { background-color: var(--ucc-sidebar-bg); }
.ucc-inst-header {
    background: var(--ucc-green);
    border-radius: 14px;
    padding: 1.25rem 1.65rem;
    margin-bottom: 1.35rem;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 1.35rem;
    flex-wrap: wrap;
}
.ucc-inst-escudo {
    width: 112px;
    max-width: 28vw;
    height: auto;
    flex-shrink: 0;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.1);
}
.ucc-inst-banner-text { flex: 1 1 240px; min-width: 0; }
.header-uccuyo h1.ucc-banner-heading,
.header-uccuyo h2.ucc-banner-heading,
.header-uccuyo h3.ucc-banner-heading {
    color: #ffffff !important;
    margin: 0;
    line-height: 1.2;
}
.header-uccuyo h1.ucc-banner-heading { font-size: clamp(1.35rem, 2.8vw, 1.95rem); font-weight: 700; }
.header-uccuyo h2.ucc-banner-heading { margin-top: 0.55rem !important; font-size: clamp(1rem, 2vw, 1.25rem); }
.header-uccuyo h3.ucc-banner-heading {
    margin-top: 0.35rem !important;
    font-size: clamp(0.85rem, 1.4vw, 1rem);
    color: rgba(255, 255, 255, 0.92) !important;
}
.ucc-intro-card {
    background: #ffffff;
    border-radius: 14px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.65rem;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.07), 0 1px 3px rgba(0, 0, 0, 0.04);
}
.ucc-intro-card h1.uc-card-main-title {
    color: var(--ucc-heading-card) !important;
    margin: 0 0 0.75rem 0 !important;
    font-size: clamp(1.3rem, 2.8vw, 1.85rem);
    font-weight: 700;
}
.ucc-intro-card p.uc-card-lead {
    color: var(--ucc-lead-muted) !important;
    margin: 0 !important;
    line-height: 1.6;
}
[data-testid="stBaseButton-primary"],
.stButton > button,
[data-testid="stDownloadButton"] button {
    background-color: var(--ucc-green) !important;
    color: #ffffff !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
</style>
"""


def _resolve_escudo_path() -> Optional[Path]:
    assets = APP_DIR / "assets"
    if not assets.is_dir():
        return None
    for name in ("escudo_uccuyo.png", "escudo_uccuyo.jpg", "escudo_uccuyo.jpeg"):
        path = assets / name
        if path.is_file():
            return path
    return None


def _escudo_src_for_banner() -> str:
    path = _resolve_escudo_path()
    if path is not None:
        ext = path.suffix.lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    return _ESCUDO_REMOTE_URL


def _guess_name(text: str) -> str:
    for line in text.splitlines()[:12]:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\s,.'-]{4,}$", line):
            if "UNIVERSIDAD" not in line and "CVar" not in line:
                return line
    return "Sin identificar"


def _scoring_sections(criteria: dict) -> list[str]:
    return [
        name
        for name, cfg in criteria.get("sections", {}).items()
        if float(cfg.get("max_points", 0)) > 0
    ]


def _load_text_from_upload(uploaded) -> tuple[str, str]:
    raw = uploaded.read()
    name = uploaded.name.lower()

    if name.endswith(".pdf"):
        raw_text = extract_text_from_pdf_bytes(raw)
        text = normalize_text(raw_text, opts=NormalizeOptions())
        return text, "pdf"

    if name.endswith(".docx"):
        raw_text = extract_text_from_docx_bytes(raw)
        text = normalize_text(raw_text, opts=NormalizeOptions())
        return text, "docx"

    if name.endswith(".doc"):
        raw_text = extract_text_from_doc_bytes(raw)
        text = normalize_text(raw_text, opts=NormalizeOptions())
        return text, "doc"

    if name.endswith(".txt"):
        return raw.decode("utf-8", errors="ignore"), "txt"

    raise ValueError("Formato no soportado. Usá PDF, DOC/DOCX (CVar CONICET) o TXT normalizado.")


def _render_header() -> None:
    st.markdown(_UCCI_GLOBAL_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="ucc-inst-header header-uccuyo">
<img class="ucc-inst-escudo" src="{_escudo_src_for_banner()}" alt="Universidad Católica de Cuyo" />
<div class="ucc-inst-banner-text">
<h1 class="ucc-banner-heading">Universidad Católica de Cuyo</h1>
<h2 class="ucc-banner-heading">Secretaría de Investigación</h2>
<h3 class="ucc-banner-heading">Consejo de Investigación</h3>
</div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<div class="ucc-intro-card">
<h1 class="uc-card-main-title">Categorizador de Investigadores — CVar UCCuyo</h1>
<p class="uc-card-lead">
Cargá el PDF o DOC del CVar (CONICET) o un TXT ya normalizado. El sistema analiza cada sección según el
Anexo VII, calcula puntajes por ítem, asigna la categoría de investigador y genera informes en pantalla,
Excel y Word.
</p>
</div>
""",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Categorizador de Investigadores — UCCuyo",
        layout="wide",
    )
    _render_header()

    criteria = load_criteria(CRITERIA_PATH)
    debug = st.checkbox("Modo depuración (vista previa y evidencias)", value=False)

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded = st.file_uploader(
            "Cargar CVar (PDF, DOC o TXT normalizado)",
            type=["pdf", "doc", "docx", "txt"],
        )
    with col_up2:
        grilla_upload = st.file_uploader(
            "Grilla manual de referencia (opcional, DOC/DOCX)",
            type=["doc", "docx"],
            help="Grilla UCCuyo ya valorada por el Consejo, para comparar categoría y ocurrencias.",
        )
    if not uploaded:
        st.info("Subí un PDF/DOC descargado de CONICET o un archivo __CVAR_CLEAN.txt para iniciar.")
        st.stop()

    try:
        text, source_type = _load_text_from_upload(uploaded)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if not text.strip():
        st.error("No se pudo extraer texto del archivo.")
        st.stop()

    docente = _guess_name(text)
    source_labels = {
        "pdf": "PDF normalizado",
        "doc": "DOC normalizado",
        "docx": "DOCX normalizado",
        "txt": "TXT",
    }
    st.success(f"Archivo cargado: **{uploaded.name}** ({source_labels.get(source_type, source_type)})")
    st.write(f"**Docente detectado:** {docente}")

    with st.spinner("Parseando CVar en estructura JSON..."):
        structured = parse_cvar(text, source_file=uploaded.name, docente=docente)

    st.markdown("---")
    st.subheader("Auditoría de extracción")
    audit_df = pd.DataFrame(audit_summary_rows(structured))
    st.dataframe(audit_df, use_container_width=True, hide_index=True)

    warnings = structured.get("audit", {}).get("warnings", [])
    if warnings:
        for w in warnings:
            st.warning(w)
    else:
        st.success("Sin alertas de extracción.")

    with st.expander("Ítems parseados por pestaña"):
        items = structured.get("items", {})
        section_labels = {
            "formacion_academica": ("Títulos académicos", "titulos"),
            "formacion_complementaria_cursos": ("Cursos / diplomaturas", None),
            "formacion_complementaria_idiomas": ("Idiomas", None),
            "antecedentes_cyt": ("Antecedentes en CyT", "entradas"),
            "formacion_rrhh": ("Formación de RRHH", "entradas"),
            "financiamiento_cyt": ("Financiamiento CyT", "entradas"),
            "evaluacion_gestion": ("Evaluación y gestión editorial", "entradas"),
            "extension": ("Actividades de extensión", "entradas"),
            "eventos_cyt": ("Participación en eventos", "entradas"),
            "actividades_profesionales": ("Actividades profesionales", "entradas"),
            "otros_antecedentes": ("Otros antecedentes CyT", "entradas"),
            "publicaciones_articulos": ("Publicaciones — artículos", None),
        }
        titulos = items.get("formacion_academica", {}).get("titulos", [])
        if titulos:
            st.markdown("**Títulos académicos**")
            st.dataframe(pd.DataFrame(titulos), use_container_width=True, hide_index=True)
        cursos = items.get("formacion_complementaria", {}).get("cursos", [])
        if cursos:
            st.markdown("**Cursos / diplomaturas**")
            st.dataframe(pd.DataFrame(cursos), use_container_width=True, hide_index=True)
        idiomas = items.get("formacion_complementaria", {}).get("idiomas", [])
        if idiomas:
            st.markdown("**Idiomas**")
            st.dataframe(pd.DataFrame(idiomas), use_container_width=True, hide_index=True)
        for key, (label, field) in section_labels.items():
            if key.startswith("formacion_complementaria") or key == "formacion_academica":
                continue
            if key == "publicaciones_articulos":
                arts = items.get("publicaciones", {}).get("articulos", [])
                if arts:
                    st.markdown(f"**{label}** ({len(arts)})")
                    st.dataframe(pd.DataFrame(arts).head(50), use_container_width=True, hide_index=True)
                continue
            block = items.get(key, {})
            rows = block.get(field or "entradas", []) if field else []
            if rows:
                st.markdown(f"**{label}** ({len(rows)})")
                st.dataframe(pd.DataFrame(rows).head(80), use_container_width=True, hide_index=True)

    if debug:
        with st.expander("Vista previa del texto (primeras 200 líneas)"):
            st.code("\n".join(text.splitlines()[:200]) or "(vacío)", language="text")
        with st.expander("JSON estructurado (vista previa)"):
            st.code(structured_to_json(structured)[:12000], language="json")

    with st.spinner("Calculando puntajes según Anexo VII..."):
        item_results, section_totals, total, category, categorias = score_text(
            text, criteria, structured=structured
        )

    desc_cat = categorias.get(category, {}).get("descripcion", "")
    df_items = results_to_dataframe(item_results, criteria=criteria)
    df_sec_tot = section_totals_dataframe(
        {k: v for k, v in section_totals.items() if k in _scoring_sections(criteria)}
    )

    st.markdown("---")
    st.subheader("Resultado de categorización")
    col1, col2, col3 = st.columns(3)
    col1.metric("Puntaje total", f"{total:.1f}")
    col2.metric("Categoría", category_label(category))
    col3.metric("Puntaje máximo teórico", "3550")
    if desc_cat:
        st.info(desc_cat)

    equiv_config = load_category_equivalence(EQUIVALENCE_PATH)
    with st.expander("Equivalencia de categorías: UCCuyo (grilla) vs Anexo VII", expanded=False):
        st.caption(
            "Misma denominación romana (I–VI), escalas distintas. "
            "El automático usa Anexo VII (máx. 3550 pts); la grilla UCCuyo la cierra el Consejo."
        )
        st.markdown("#### Tabla de categorías y umbrales")
        st.dataframe(build_equivalence_table(equiv_config), use_container_width=True, hide_index=True)
        st.markdown("#### Casos de referencia (validación interna)")
        st.dataframe(build_reference_cases_table(equiv_config), use_container_width=True, hide_index=True)
        grilla_note = equiv_config.get("grilla_uccuyo", {}).get("nota_escala", "")
        if grilla_note:
            st.info(grilla_note)

    st.markdown("---")
    st.subheader("Puntajes por sección")
    for section_name in _scoring_sections(criteria):
        cfg = criteria["sections"][section_name]
        sec_max = float(cfg.get("max_points", 0))
        sec_sub = float(section_totals.get(section_name, 0.0))
        st.markdown(f"### {section_name}")
        df_sec = df_items[df_items["Sección"] == section_name].copy()
        df_sec = df_sec.sort_values(["Puntaje (tope aplicado)", "Ocurrencias"], ascending=False)
        display_cols = ["Ítem", "Ocurrencias", "Puntaje (tope aplicado)", "Tope en sección"]
        if debug:
            display_cols.append("Evidencia (1er match)")
        st.dataframe(df_sec[display_cols], use_container_width=True, hide_index=True)
        item_topes_cfg = sum(
            float(it.get("max_points", 0)) for it in cfg.get("items", {}).values()
        )
        effective_max = section_effective_max(cfg)
        section_overflow = item_topes_cfg > sec_max + 0.5 and sec_sub >= sec_max - 0.5
        if section_overflow:
            st.caption(
                f"Cupo global de la sección: **{int(sec_max)} pts**. "
                "Cada ítem tiene un tope dentro de ese cupo (columna «Tope en sección»)."
            )
        elif item_topes_cfg > sec_max + 0.5:
            st.caption(
                f"Cupo global de la sección: **{int(sec_max)} pts**. "
                "Se aplican los topes por ítem del Anexo VII; el cupo global solo limita si el subtotal lo supera."
            )
        elif item_topes_cfg < sec_max - 0.5:
            st.caption(
                f"Tope Anexo VII: **{int(sec_max)} pts**. "
                f"Máximo alcanzable con los ítems del valorador: **{effective_max} pts**."
            )
        st.info(f"Subtotal: **{int(round(sec_sub))}** / máx **{effective_max}**")

    st.markdown("---")
    st.subheader("Resumen por sección")
    st.dataframe(df_sec_tot, use_container_width=True, hide_index=True)

    base_name = uploaded.name.rsplit(".", 1)[0].replace(" ", "_")

    if grilla_upload is not None:
        st.markdown("---")
        st.subheader("Comparación con grilla manual")
        try:
            grilla_parsed = parse_grilla(grilla_upload.read(), filename=grilla_upload.name)
            comparison = build_comparison_report(
                df_items,
                section_totals,
                total,
                category,
                grilla_parsed,
                criteria,
                GRILLA_MAPPING_PATH,
                structured=structured,
                equivalence_path=EQUIVALENCE_PATH,
            )
            cat_info = comparison["categoria"]
            if cat_info.get("¿Coincide nominal?") == "Sí":
                st.success(
                    f"Categoría coincidente: **{cat_info['Automático (Anexo VII)']}** "
                    f"({cat_info.get('Etiqueta manual', '')})"
                )
            elif cat_info.get("¿Coincide nominal?") == "No":
                st.error(
                    f"Discrepancia de categoría — Auto: **{cat_info['Automático (Anexo VII)']}** "
                    f"({cat_info.get('Etiqueta Anexo VII', '')}) | "
                    f"Grilla: **{cat_info['Manual (grilla UCCuyo)']}** "
                    f"({cat_info.get('Etiqueta manual', '')})"
                )
                if cat_info.get("Interpretación") and cat_info["Interpretación"] != "—":
                    st.warning(cat_info["Interpretación"])

            st.caption(
                "Las grillas UCCuyo usan una escala distinta al Anexo VII (3550 pts). "
                "Priorizá la **categoría nominal** y las **ocurrencias** anotadas en la grilla."
            )
            if grilla_parsed.get("meta", {}).get("docente"):
                st.write(f"**Docente en grilla:** {grilla_parsed['meta']['docente']}")

            st.markdown("#### Resumen total y categoría")
            st.dataframe(comparison["resumen"], use_container_width=True, hide_index=True)

            st.markdown("#### Bloques de la grilla vs Anexo VII")
            st.dataframe(comparison["secciones"], use_container_width=True, hide_index=True)

            if not comparison["anotaciones"].empty:
                st.markdown("#### Anotaciones del evaluador (conteo manual vs automático)")
                solo_diff = st.checkbox("Mostrar solo diferencias (Estado = Revisar)", value=False)
                ann_df = comparison["anotaciones"]
                if solo_diff:
                    ann_df = ann_df[ann_df["Estado"] == "Revisar"]
                st.dataframe(ann_df, use_container_width=True, hide_index=True)

            with st.expander("Ítems automáticos con puntaje (referencia para revisión)"):
                st.dataframe(comparison["items_auto"], use_container_width=True, hide_index=True)

            if debug and grilla_parsed.get("annotations"):
                with st.expander("Anotaciones extraídas de la grilla"):
                    st.dataframe(pd.DataFrame(grilla_parsed["annotations"]), use_container_width=True, hide_index=True)

            st.download_button(
                "Descargar comparación Excel",
                data=export_comparison_excel(comparison),
                file_name=f"{base_name}__COMPARACION_GRILLA.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"No se pudo comparar con la grilla: {exc}")

    st.markdown("---")
    st.subheader("Exportar resultados")

    if source_type in ("pdf", "doc", "docx"):
        sections = extract_sections(text)
        parsed_formacion = None
        if "FORMACIÓN ACADÉMICA" in sections:
            parsed_formacion = parse_formacion_academica(sections.get("FORMACIÓN ACADÉMICA", ""))
        docx_norm = build_docx_bytes(text, sections=sections, parsed_formacion=parsed_formacion)
        st.download_button(
            "Descargar TXT normalizado",
            data=text.encode("utf-8"),
            file_name=f"{base_name}__CVAR_CLEAN.txt",
            mime="text/plain; charset=utf-8",
            use_container_width=True,
        )
        st.download_button(
            "Descargar CVar estructurado (JSON)",
            data=structured_to_json(structured).encode("utf-8"),
            file_name=f"{base_name}__CVAR_STRUCTURED.json",
            mime="application/json",
            use_container_width=True,
        )
        st.download_button(
            "Descargar CVar estructurado (DOCX)",
            data=docx_norm,
            file_name=f"{base_name}__CVAR_CLEAN.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    st.download_button(
        "Descargar informe Excel",
        data=export_excel(df_items, df_sec_tot, total, category, criteria),
        file_name=f"{base_name}__PUNTAJE.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
    st.download_button(
        "Descargar informe Word",
        data=export_word(
            df_items,
            df_sec_tot,
            total,
            category,
            desc_cat,
            uploaded.name,
            criteria,
            include_evidence=debug,
        ),
        file_name=f"{base_name}__INFORME.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
