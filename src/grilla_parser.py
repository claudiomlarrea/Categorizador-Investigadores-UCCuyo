"""
Parser de grillas manuales UCCuyo (DOC/DOCX) para comparación con el puntaje automático.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_GRILLA_SECTION_NAMES = [
    ("formacion_academica", r"formaci[oó]n\s+acad[eé]mica"),
    ("docencia", r"docencia\s+en\s+instituciones"),
    ("investigacion_cyt", r"investigaci[oó]n\s+cient[ií]fica"),
    ("produccion_academica", r"producci[oó]n\s+acad[eé]mica"),
    ("actividad_cientifica", r"actividad\s+cient[ií]fica"),
    ("formacion_rrhh", r"formaci[oó]n\s+de\s+recursos\s+humanos"),
    ("gestion_universitaria", r"gesti[oó]n\s+universitaria"),
]

_RE_SCORE_LINE = re.compile(r"^\s*(\d{1,4})\s*$")
_RE_CATEGORY = re.compile(
    r"(?i)(?:"
    r"CATEGOR[IÍ]A\s+RESULTANTE\s*:\s*(?:N[ºo°]\s*:\s*)?([IVXLC]+)\b"
    r"|"
    r"CATEGOR[IÍ]A\s+RESULTANTE\s*:\s*([A-ZÁÉÍÓÚÜÑa-záéíóúüñ\s]+?)\s+N[ºo°]\s*:\s*([IVXLC]+)"
    r")",
)
_RE_CATEGORY_LABEL = re.compile(
    r"(?i)(superior|principal|independiente|adjunto|asistente|becario)",
)
_RE_ANNOTATION_POINTS = re.compile(r"(?i)(\d+)\s*P\b")
_RE_DOCENTE = re.compile(
    r"(?i)APELLIDO,\s*NOMBRES?\s*:\s*([^\n]+?)(?:\s+DNI\s*:|$)",
)


def _extract_text_from_doc_bytes(doc_bytes: bytes, suffix: str = ".doc") -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(doc_bytes)
        path = tmp.name
    try:
        proc = subprocess.run(
            ["textutil", "-stdout", "-convert", "txt", path],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout or ""
    finally:
        Path(path).unlink(missing_ok=True)


def extract_grilla_text(raw: bytes, filename: str = "") -> str:
    name = filename.lower()
    if name.endswith(".docx"):
        import io
        from docx import Document

        doc = Document(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)
    if name.endswith(".doc"):
        return _extract_text_from_doc_bytes(raw, ".doc")
    return raw.decode("utf-8", errors="ignore")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _parse_summary_sections(lines: List[str]) -> Dict[str, float]:
    """Extrae puntajes del cuadro resumen inicial (nombre de ítem → número en línea siguiente)."""
    scores: Dict[str, float] = {}
    current_key: Optional[str] = None
    desc_lines = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("COMENTARIOS"):
            continue
        if _norm(stripped) in ("ítem", "item", "aspectos que se evalúan", "puntaje"):
            continue

        matched_key = None
        for key, pat in _GRILLA_SECTION_NAMES:
            if re.search(pat, stripped, re.I) and len(stripped) < 80:
                matched_key = key
                break

        if matched_key:
            current_key = matched_key
            desc_lines = 0
            continue

        if current_key and _RE_SCORE_LINE.match(stripped):
            scores[current_key] = float(stripped)
            current_key = None
            desc_lines = 0
            continue

        if current_key:
            desc_lines += 1
            if desc_lines > 4 and _RE_SCORE_LINE.match(stripped):
                scores[current_key] = float(stripped)
                current_key = None

    return scores


def _parse_total(lines: List[str]) -> Optional[float]:
    for i, line in enumerate(lines):
        if re.search(r"PUNTAJE\s+TOTAL", line, re.I):
            for nxt in lines[i + 1 : i + 6]:
                m = _RE_SCORE_LINE.match(nxt.strip())
                if m:
                    return float(m.group(1))
    return None


def _parse_category(text: str) -> Tuple[Optional[str], str]:
    roman = None
    label = ""
    for m in _RE_CATEGORY.finditer(text):
        if m.lastindex and m.lastindex >= 1:
            for g in m.groups():
                if g and re.fullmatch(r"[IVXLC]+", g.strip(), re.I):
                    roman = g.strip().upper()
                elif g and _RE_CATEGORY_LABEL.search(g):
                    label = g.strip()
    if not roman:
        m2 = re.search(r"(?i)N[ºo°]\s*:\s*([IVXLC]+)\b", text)
        if m2:
            roman = m2.group(1).upper()
    if not label and roman:
        label_map = {
            "I": "Superior",
            "II": "Principal",
            "III": "Independiente",
            "IV": "Adjunto",
            "V": "Asistente",
            "VI": "Becario",
        }
        label = label_map.get(roman, "")
    return roman, label


def _parse_annotations(text: str) -> List[Dict[str, Any]]:
    """Extrae anotaciones del evaluador (ej. '4 CURSOS 20 P', 'EXPOSITORA 1 20P')."""
    annotations: List[Dict[str, Any]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or len(raw) < 8:
            continue
        if not _RE_ANNOTATION_POINTS.search(raw):
            continue
        if not re.search(r"(?i)curso|proyecto|expositora?|asistente|organizadora?|beca|tesis|publicaci|gesti[oó]n|investigaci[oó]n", raw):
            continue
        points = [int(x) for x in _RE_ANNOTATION_POINTS.findall(raw)]
        annotations.append(
            {
                "texto": raw[:300],
                "puntos_manuales": sum(points) if points else None,
                "puntos_lista": points,
            }
        )
    return annotations


def parse_grilla(raw: bytes, filename: str = "") -> Dict[str, Any]:
    text = extract_grilla_text(raw, filename)
    lines = text.splitlines()

    docente_m = _RE_DOCENTE.search(text)
    docente = docente_m.group(1).strip() if docente_m else ""

    section_scores = _parse_summary_sections(lines)
    total = _parse_total(lines)
    category_roman, category_label = _parse_category(text)

    return {
        "meta": {
            "source_file": filename,
            "docente": docente,
            "text_length": len(text),
            "scale": "grilla_uccuyo",
        },
        "total_manual": total,
        "category_manual": category_roman,
        "category_label_manual": category_label,
        "section_scores": section_scores,
        "annotations": _parse_annotations(text),
        "raw_preview": "\n".join(lines[:40]),
    }


def load_grilla_mapping(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
