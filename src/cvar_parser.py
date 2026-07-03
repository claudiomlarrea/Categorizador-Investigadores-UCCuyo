"""
Parser estructurado para CVars exportados por CONICET (PDF/DOC → texto limpio).

Flujo:
  texto normalizado → segmentación por pestañas → ítems tipados → JSON + auditoría
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

def _scorer():
    """Import diferido para evitar dependencia circular con scorer.py."""
    import sys
    from pathlib import Path

    try:
        import scorer as _sc
        return _sc
    except ModuleNotFoundError:
        src_dir = str(Path(__file__).resolve().parent)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        import scorer as _sc
        return _sc

try:
    from section_parsers import (  # noqa: E402
        aggregate_section_counts,
        parse_actividades_profesionales,
        parse_evaluacion_gestion,
        parse_eventos_cyt,
        parse_extension,
        parse_financiamiento,
        parse_formacion_rrhh,
        parse_otros_antecedentes,
        parse_publicaciones_extended,
    )
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from section_parsers import (  # noqa: E402
        aggregate_section_counts,
        parse_actividades_profesionales,
        parse_evaluacion_gestion,
        parse_eventos_cyt,
        parse_extension,
        parse_financiamiento,
        parse_formacion_rrhh,
        parse_otros_antecedentes,
        parse_publicaciones_extended,
    )

SCHEMA_VERSION = "1.1"

# Pestañas CONICET en orden típico de aparición (más específicas primero al matchear).
SECTION_DEFINITIONS: List[Tuple[str, str, str]] = [
    # (canonical_key, label_es, regex línea completa)
    ("datos_personales", "Datos personales", r"DATOS\s+PERSONALES"),
    (
        "formacion_academica",
        "Formación académica",
        r"FORMACI[ÓO]N\s+ACAD[ÉE]MICA(?:\s+Y\s+COMPLEMENTARIA)?",
    ),
    ("formacion_complementaria", "Formación complementaria", r"FORMACI[ÓO]N\s+COMPLEMENTARIA"),
    ("antecedentes_cyt", "Antecedentes en CyT", r"ANTECEDENTES\s+EN\s+CYT"),
    ("formacion_rrhh", "Formación de recursos humanos", r"FORMACI[ÓO]N\s+DE\s+RECURSOS\s+HUMANOS"),
    ("financiamiento_cyt", "Financiamiento CyT", r"FINANCIAMIENTO(?:\s+CYT|\s+CIENT[IÍ]FICO)?"),
    (
        "evaluacion_gestion",
        "Evaluación y gestión editorial",
        r"ACTIVIDADES\s+DE\s+EVALUACI[ÓO]N\s+Y\s+GESTI[ÓO]N\s+EDITORIAL|"
        r"INSTANCIAS\s+DE\s+EVALUACI[ÓO]N",
    ),
    ("extension", "Actividades de extensión", r"ACTIVIDADES\s+DE\s+EXTENSI[ÓO]N|EXTENSI[ÓO]N(?:\s+CYT)?"),
    ("actividades_profesionales", "Actividades profesionales", r"ACTIVIDADES\s+PROFESIONALES"),
    ("eventos_cyt", "Participación en eventos CyT", r"PARTICIPACI[ÓO]N\s+EN\s+EVENTOS(?:\s+CYT)?"),
    ("publicaciones", "Publicaciones", r"PUBLICACIONES|PRODUCCIONES\s+Y\s+SERVICIOS"),
    ("otros_antecedentes", "Otros antecedentes CyT", r"OTROS\s+ANTECEDENTES(?:\s+CYT)?"),
]

# Pestañas que pueden existir en CVar web pero no siempre aparecen en el PDF.
OPTIONAL_SECTIONS = [
    "datos_personales",
    "formacion_rrhh",
    "financiamiento_cyt",
    "evaluacion_gestion",
    "extension",
    "actividades_profesionales",
    "eventos_cyt",
    "publicaciones",
    "otros_antecedentes",
]

_RE_HEADER_LINE = re.compile(
    r"(?im)^\s*("
    + "|".join(f"(?:{pat})" for _, _, pat in SECTION_DEFINITIONS)
    + r")\s*$"
)

_RE_NOISE = re.compile(
    r"(?:CVar\s+ES\s+UNA|Fecha\s+de\s+generaci|MINISTERIO\s+DE\s+CIENCIA|^\s*\d{1,3}\s*$)",
    re.IGNORECASE,
)


@dataclass
class SectionSpan:
    key: str
    label: str
    header: str
    start: int
    end: int
    text: str


@dataclass
class AuditReport:
    sections_found: List[str] = field(default_factory=list)
    sections_missing: List[str] = field(default_factory=list)
    section_item_counts: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def _canonical_for_header(header_line: str) -> Tuple[str, str]:
    h = header_line.strip()
    for key, label, pat in SECTION_DEFINITIONS:
        if re.fullmatch(pat, h, flags=re.IGNORECASE):
            return key, label
    h_up = h.upper()
    for key, label, pat in SECTION_DEFINITIONS:
        if re.fullmatch(pat, h_up, flags=re.IGNORECASE):
            return key, label
    return "desconocido", h


def segment_sections(clean_text: str) -> List[SectionSpan]:
    """Corta el CVar en bloques por encabezados de pestaña (incluye sub-pestañas embebidas)."""
    text = _scorer()._norm_spaces(clean_text)
    if not text:
        return []

    matches = list(_RE_HEADER_LINE.finditer(text))
    if not matches:
        return [
            SectionSpan(
                key="texto_completo",
                label="Texto completo",
                header="",
                start=0,
                end=len(text),
                text=text.strip(),
            )
        ]

    spans: List[SectionSpan] = []
    for i, m in enumerate(matches):
        header = m.group(1).strip()
        key, label = _canonical_for_header(header)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        spans.append(
            SectionSpan(
                key=key,
                label=label,
                header=header,
                start=m.start(),
                end=end,
                text=block,
            )
        )
    return spans


def _parse_formacion_items(block: str) -> List[Dict[str, Any]]:
    sc = _scorer()
    items: List[Dict[str, Any]] = []
    for entry in sc._split_entries(block):
        if not entry.strip():
            continue
        tipo = "posdoc" if re.search(r"\b(posdoctorado|postdoctorado)\b", entry, re.I) else sc._classify_structural(entry)
        items.append(
            {
                "tipo": tipo,
                "titulo": sc._first_line(entry),
                "finalizado": sc._entry_completed(entry),
                "texto": re.sub(r"\s+", " ", entry.strip())[:500],
            }
        )
    return items


def _parse_cursos_items(block: str) -> List[Dict[str, Any]]:
    sc = _scorer()
    items: List[Dict[str, Any]] = []
    for entry in sc._split_curso_entries(block):
        entry = sc._strip_idioma_lines(entry)
        snippet = re.sub(r"\s+", " ", entry).strip()
        if len(snippet) < 12:
            continue
        horas_m = re.search(r"\b(?:Entre|Hasta)\s+(\d{1,4})\s*(?:Y\s+(\d{1,4}))?\s*horas\b", entry, re.I)
        items.append(
            {
                "titulo": snippet[:200],
                "con_horas": bool(horas_m),
                "horas": horas_m.group(0) if horas_m else "",
            }
        )
    return items


def _parse_idiomas_items(block: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line or _RE_NOISE.search(line):
            continue
        m = re.search(
            r"(Ingl[eé]s|Franc[eé]s|Portugu[eé]s|Italiano|Alem[aá]n|Chino|Japon[eé]s)\s*\[[^\]]+\]",
            line,
            re.I,
        )
        if m:
            items.append({"idioma": m.group(1), "linea": line[:260]})
    return items


def _parse_antecedentes_items(block: str) -> List[Dict[str, Any]]:
    sc = _scorer()
    items: List[Dict[str, Any]] = []
    for entry in sc._split_antecedentes_entries(block):
        snippet = re.sub(r"\s+", " ", entry).strip()
        rol = "docencia" if re.search(
            r"\b(?:Profesor(?:a)?|Docente|C[aá]tedra|JTP|Ayudante|Jefe\s+de\s+trabajos\s+pr[aá]cticos)\b",
            snippet,
            re.I,
        ) else ""
        if not rol and re.search(r"\bconeu\b|\bacreditaci[oó]n\b", snippet, re.I):
            rol = "gestion"
        elif not rol and re.search(
            r"\b(?:Coordinador(?:a)?|Director(?:a)?|Secretari[oa]|Decan[oa]|Vicerrector(?:a)?|"
            r"Rector(?:a)?|Consejer[oa]|Jefe\s+de|Subprograma|Asistente\s+Ejecutiv[a]?|"
            r"Asistente\s+de\s+Investigaci[oó]n|"
            r"Miembro\s+(?:del\s+)?(?:comit[eé]|consejo)\s+de\s+investigaci[oó]n|"
            r"Integrante\s+del\s+Comit[eé])\b",
            snippet,
            re.I,
        ):
            rol = "gestion"
        elif not rol and re.search(
            r"\b(?:Asesor(?:a)?|Consultor(?:a)?|Perit(?:o|aje)?|Auditor(?:a)?|Gerente|Responsable)\b",
            snippet,
            re.I,
        ):
            rol = "profesional"
        elif not rol and re.search(
            r"programa de incentivos|categor[ií]a\s+(?:i{1,3}|iv|v|vi)\b",
            snippet,
            re.I,
        ):
            rol = "incentivos"
        elif not rol:
            rol = "otro"
        items.append({"rol": rol, "texto": snippet[:400]})
    return items


def _parse_publicaciones_items(block: str) -> Dict[str, Any]:
    return parse_publicaciones_extended(block, _scorer())


def _append_trabajos_evento_from_block(pub_parsed: Dict[str, Any], extra_block: str) -> None:
    """Extrae pósters/resúmenes que en CVs cortos quedan al final de Eventos CyT."""
    if not extra_block or not extra_block.strip():
        return
    sc = _scorer()
    trabajos = list(pub_parsed.get("trabajos_evento", []))
    seen = {sc._norm_key(t.get("titulo", "")[:180]) for t in trabajos}
    evento_titles = sc._extract_evento_titles_set(extra_block)

    def _add(sn: str) -> None:
        if not sn or not re.search(r"(?:19|20)\d{2}", sn):
            return
        if sc._trabajo_duplicates_evento(sn, evento_titles):
            return
        key = sc._norm_key(sn[:180])
        if key in seen:
            return
        seen.add(key)
        trabajos.append({"titulo": sn[:300]})

    for poster in sc._extract_poster_presentaciones(extra_block):
        _add(poster)
    for row in sc._merge_publicacion_lines(extra_block):
        sn = re.sub(r"\s+", " ", row).strip()
        if re.search(r"(?i)^\d{4}\s*[-–]\s*Evento\s*:", sn):
            continue
        if sc._is_trabajo_evento_publicado(sn):
            _add(sn)

    pub_parsed["trabajos_evento"] = trabajos
    pub_parsed.setdefault("counts", {})["trabajos_evento_publicados"] = len(trabajos)


def _section_text_map(spans: List[SectionSpan]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for sp in spans:
        if sp.key in out:
            out[sp.key] = (out[sp.key] + "\n\n" + sp.text).strip()
        else:
            out[sp.key] = sp.text
    return out


def _build_counts(text: str, section_text: Dict[str, str], parsed_items: Dict[str, Any]) -> Dict[str, Any]:
    sc = _scorer()
    form_counts, _ = sc._count_formacion(text)
    cursos_items = parsed_items.get("formacion_complementaria", {}).get("cursos", [])
    if cursos_items:
        cursos_con = sum(1 for c in cursos_items if c.get("con_horas"))
        cursos_sin = sum(1 for c in cursos_items if not c.get("con_horas"))
    else:
        cursos_con, cursos_sin, _ = sc._count_cursos(text)
    idiomas, _ = sc._count_idiomas(text)
    antecedentes, antecedentes_ev = sc._count_antecedentes_cyt(text)
    ant_items = parsed_items.get("antecedentes_cyt", {}).get("entradas", [])
    if ant_items:
        antecedentes = {
            "gestion": sum(1 for e in ant_items if e.get("rol") == "gestion"),
            "profesional": sum(1 for e in ant_items if e.get("rol") == "profesional"),
        }
    section_agg = aggregate_section_counts(parsed_items)
    pub_counts = parsed_items.get("publicaciones", {}).get("counts", {})

    return {
        "formacion": form_counts,
        "cursos_con_horas": cursos_con,
        "cursos_sin_horas": cursos_sin,
        "idiomas": idiomas,
        "articulos_revista": pub_counts.get("articulos_revista", 0),
        "capitulos_libro": pub_counts.get("capitulos_libro", 0),
        "libros_isbn": pub_counts.get("libros_isbn", 0),
        "articulos_doi": pub_counts.get("articulos_doi", 0),
        "trabajos_evento_publicados": pub_counts.get("trabajos_evento_publicados", 0),
        "antecedentes_gestion": antecedentes.get("gestion", 0),
        "antecedentes_profesional": antecedentes.get("profesional", 0),
        "antecedentes_incentivos": sum(
            1 for e in parsed_items.get("antecedentes_cyt", {}).get("entradas", []) if e.get("rol") == "incentivos"
        ),
        "antecedentes_incentivos_evidence": next(
            (
                e.get("texto", "")
                for e in parsed_items.get("antecedentes_cyt", {}).get("entradas", [])
                if e.get("rol") == "incentivos"
            ),
            "",
        ),
        "rrhh": section_agg.get("rrhh", {}),
        "financiamiento": section_agg.get("financiamiento", {}),
        "evaluacion": section_agg.get("evaluacion", {}),
        "extension_actividades": section_agg.get("extension", 0),
        "eventos": section_agg.get("eventos", 0),
        "eventos_organizador": section_agg.get("eventos_organizador", 0),
        "eventos_asistente": section_agg.get("eventos_asistente", 0),
        "eventos_expositora": section_agg.get("eventos_expositora", 0),
        "eventos_premios": section_agg.get("eventos_premios", 0),
        "actividades_expositora": section_agg.get("actividades_expositora", 0),
        "actividades_profesionales": section_agg.get("actividades_profesionales", 0),
        "otros": section_agg.get("otros", {}),
        "section_chars": {k: len(v) for k, v in section_text.items()},
    }


def _build_audit(spans: List[SectionSpan], parsed_items: Dict[str, Any], counts: Dict[str, Any]) -> AuditReport:
    found = []
    seen = set()
    for sp in spans:
        if sp.key not in seen and sp.key != "texto_completo":
            found.append(sp.key)
            seen.add(sp.key)

    missing = [k for k in OPTIONAL_SECTIONS if k not in seen]
    item_counts: Dict[str, int] = {}
    warnings: List[str] = []

    fa = parsed_items.get("formacion_academica", {})
    item_counts["formacion_academica"] = len(fa.get("titulos", []))
    fc = parsed_items.get("formacion_complementaria", {})
    item_counts["formacion_complementaria"] = len(fc.get("cursos", [])) + len(fc.get("idiomas", []))
    item_counts["antecedentes_cyt"] = len(parsed_items.get("antecedentes_cyt", {}).get("entradas", []))
    item_counts["formacion_rrhh"] = len(parsed_items.get("formacion_rrhh", {}).get("entradas", []))
    item_counts["financiamiento_cyt"] = len(parsed_items.get("financiamiento_cyt", {}).get("entradas", []))
    item_counts["evaluacion_gestion"] = len(parsed_items.get("evaluacion_gestion", {}).get("entradas", []))
    item_counts["extension"] = len(parsed_items.get("extension", {}).get("entradas", []))
    item_counts["eventos_cyt"] = len(parsed_items.get("eventos_cyt", {}).get("entradas", []))
    item_counts["actividades_profesionales"] = len(
        parsed_items.get("actividades_profesionales", {}).get("entradas", [])
    )
    item_counts["otros_antecedentes"] = len(parsed_items.get("otros_antecedentes", {}).get("entradas", []))
    item_counts["publicaciones"] = (
        counts.get("articulos_revista", 0)
        + counts.get("capitulos_libro", 0)
        + counts.get("libros_isbn", 0)
        + counts.get("trabajos_evento_publicados", 0)
    )

    if "formacion_academica" in seen and item_counts["formacion_academica"] == 0:
        warnings.append("Formación académica presente pero sin títulos parseados — revisar formato.")
    if "publicaciones" in seen and counts.get("articulos_revista", 0) == 0:
        pub_text = parsed_items.get("publicaciones", {}).get("raw_chars", 0)
        if pub_text > 200:
            warnings.append("Sección Publicaciones con texto pero 0 artículos detectados.")

    if "texto_completo" in seen:
        warnings.append("No se detectaron encabezados de pestaña — se usó texto completo.")

    return AuditReport(
        sections_found=found,
        sections_missing=missing,
        section_item_counts=item_counts,
        warnings=warnings,
    )


def parse_cvar(
    clean_text: str,
    *,
    source_file: str = "",
    docente: str = "",
) -> Dict[str, Any]:
    """
    Parsea un CVar normalizado y devuelve el JSON estructurado (fuente de verdad).
    """
    sc = _scorer()
    text = sc._norm_spaces(clean_text)
    spans = segment_sections(text)
    section_text = _section_text_map(spans)

    # Bloques auxiliares (fallback cuando la segmentación no aisló la pestaña)
    form_block = section_text.get("formacion_academica") or sc._extract_formacion_block(text)
    comp_block = section_text.get("formacion_complementaria") or sc._extract_complementaria_block(text)
    comp_idiomas_block = section_text.get("formacion_complementaria") or sc._extract_complementaria_idiomas_block(text)
    ant_block = section_text.get("antecedentes_cyt") or sc._extract_antecedentes_cyt_block(text)
    pub_block = section_text.get("publicaciones") or sc._extract_publicaciones_block(text)

    rrhh_block = section_text.get("formacion_rrhh", "")
    fin_block = section_text.get("financiamiento_cyt", "")
    ev_block = section_text.get("evaluacion_gestion", "")
    ext_block = section_text.get("extension", "")
    evt_block = section_text.get("eventos_cyt", "")
    ap_block = section_text.get("actividades_profesionales", "")
    otros_block = section_text.get("otros_antecedentes", "")

    pub_parsed = _parse_publicaciones_items(pub_block)
    if evt_block:
        _append_trabajos_evento_from_block(pub_parsed, evt_block)

    parsed_items: Dict[str, Any] = {
        "formacion_academica": {
            "titulos": _parse_formacion_items(form_block),
        },
        "formacion_complementaria": {
            "cursos": _parse_cursos_items(comp_block),
            "idiomas": _parse_idiomas_items(comp_idiomas_block),
        },
        "antecedentes_cyt": {
            "entradas": _parse_antecedentes_items(ant_block),
        },
        "formacion_rrhh": parse_formacion_rrhh(rrhh_block),
        "financiamiento_cyt": parse_financiamiento(fin_block),
        "evaluacion_gestion": parse_evaluacion_gestion(ev_block),
        "extension": parse_extension(ext_block),
        "eventos_cyt": parse_eventos_cyt(evt_block),
        "actividades_profesionales": parse_actividades_profesionales(ap_block),
        "otros_antecedentes": parse_otros_antecedentes(otros_block),
        "publicaciones": pub_parsed,
    }

    counts = _build_counts(text, section_text, parsed_items)
    audit = _build_audit(spans, parsed_items, counts)

    sections_meta = [
        {
            "key": sp.key,
            "label": sp.label,
            "header": sp.header,
            "chars": len(sp.text),
            "preview": sp.text[:180].replace("\n", " ") if sp.text else "",
        }
        for sp in spans
    ]

    return {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "source_file": source_file,
            "docente": docente,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "text_length": len(text),
        },
        "audit": {
            "sections_found": audit.sections_found,
            "sections_missing": audit.sections_missing,
            "section_item_counts": audit.section_item_counts,
            "warnings": audit.warnings,
        },
        "sections": section_text,
        "sections_meta": sections_meta,
        "items": parsed_items,
        "counts": counts,
    }


def structured_to_json(structured: Dict[str, Any], *, indent: int = 2) -> str:
    return json.dumps(structured, ensure_ascii=False, indent=indent)


def scoring_text_from_structured(structured: Dict[str, Any]) -> str:
    """Reconstruye texto concatenando pestañas para ítems aún evaluados por regex de sección."""
    parts = structured.get("sections", {})
    order = [key for key, _, _ in SECTION_DEFINITIONS]
    chunks = []
    for key in order:
        block = parts.get(key, "").strip()
        if block:
            chunks.append(block)
    if chunks:
        return "\n\n".join(chunks)
    return "\n\n".join(parts.values())


def audit_summary_rows(structured: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filas para mostrar en tabla de auditoría en Streamlit."""
    labels = {k: lbl for k, lbl, _ in SECTION_DEFINITIONS}
    found = set(structured.get("audit", {}).get("sections_found", []))
    item_counts = structured.get("audit", {}).get("section_item_counts", {})
    section_chars = structured.get("counts", {}).get("section_chars", {})

    rows = []
    for key, label, _ in SECTION_DEFINITIONS:
        rows.append(
            {
                "Pestaña": label,
                "Clave": key,
                "Presente": "Sí" if key in found else "No",
                "Ítems detectados": item_counts.get(key, 0) if key in found else "—",
                "Caracteres": section_chars.get(key, 0) if key in found else 0,
            }
        )
    return rows
