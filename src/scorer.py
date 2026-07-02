import json
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional


# =========================
# Results struct
# =========================
@dataclass
class ItemResult:
    section: str
    item: str
    pattern: str
    count: int
    unit_points: float
    raw_points: float
    capped_item_points: float
    item_max_points: float
    evidence: str


# =========================
# IO
# =========================
def load_criteria(path: str = "criteria.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# =========================
# Small helpers
# =========================
def _compile(pattern: str) -> re.Pattern:
    return re.compile(pattern, flags=re.IGNORECASE | re.UNICODE)


def _pick_evidence(text: str, m: re.Match, max_chars: int = 260) -> str:
    start = max(0, m.start() - 80)
    end = min(len(text), m.end() + 120)
    snippet = text[start:end]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet[:max_chars]


def _norm_spaces(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u00A0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _norm_key(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\"'`´]", "", s)
    return s


_RE_CVAR_BOILERPLATE = re.compile(
    r"(?:CVar\s+ES\s+UNA\s+INICIATIVA|MINISTERIO\s+DE\s+CIENCIA|"
    r"Fecha\s+de\s+generaci[oó]n|TECNOLOG[IÍ]A\s+E\s+INNOVACI[ÓO]N)",
    re.IGNORECASE,
)


def _line_at_pos(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    return text[start:end]


def _is_valid_activity_match(text: str, m: re.Match) -> bool:
    """Descarta matches anclados en pies de página del CVAr o regex multilínea demasiado anchos."""
    line = _line_at_pos(text, m.start())
    if re.search(
        r"CVar\s+ES\s+UNA\s+INICIATIVA|Fecha\s+de\s+generaci|MINISTERIO\s+DE\s+CIENCIA",
        line,
        re.IGNORECASE,
    ):
        return False

    if m.end() - m.start() > 900:
        return False

    head = text[m.start() : m.start() + 240]
    if m.end() - m.start() > 500 and re.search(
        r"CONSULTOR\s+DE\s+EMPRESAS|PROGRAMA\s+DE\s+ACTUALIZACION",
        head,
        re.IGNORECASE,
    ):
        return False

    snippet = _pick_evidence(text, m, max_chars=320)
    if _RE_CVAR_BOILERPLATE.search(snippet):
        if re.search(
            r"\b(?:20\d{2}|19\d{2})\s*[-–]\s*(?:20\d{2}|19\d{2}|Actualidad)\b",
            snippet,
        ):
            return True
        if re.search(
            r"\b(?:Evaluaci[oó]n\s+de|Rol:\s|Investigador/a:|Tesista:|"
            r"Direcci[oó]n\s+de|Jurado|Revisor)\b",
            snippet,
            re.IGNORECASE,
        ):
            return True
        return False
    return True


def _tighten_dated_activity_pattern(pattern: str) -> str:
    """
    En patrones (?ims)^ de antecedentes datados, el .*? inicial puede saltar de sección.
    """
    if not pattern.startswith("(?ims)^"):
        return pattern
    return re.sub(r"\?\.\*\?", "?[^\n]{0,260}?", pattern, count=1)


def _regex_match_count(text: str, pattern: str, evidence_max_chars: int = 260) -> Tuple[int, str]:
    if not pattern:
        return 0, ""
    pattern = _tighten_dated_activity_pattern(pattern)
    try:
        rx = _compile(pattern)
    except re.error:
        return 0, ""
    matches = [m for m in rx.finditer(text) if _is_valid_activity_match(text, m)]
    if not matches:
        return 0, ""
    return len(matches), _pick_evidence(text, matches[0], max_chars=evidence_max_chars)


# ==========================================================
# Formación Académica: extracción + parse por entradas
# (evita regex “greedy” que se come 3 doctorados como 1)
# ==========================================================

_FORM_HEADERS = [
    r"\bFORMACI[ÓO]N\s+ACAD[ÉE]MICA\b",
    r"\bFORMACION\s+ACADEMICA\b",
    r"\bFORMACI[ÓO]N\s+ACAD[ÉE]MICA\s+Y\s+COMPLEMENTARIA\b",
    r"\bFORMACION\s+ACADEMICA\s+Y\s+COMPLEMENTARIA\b",
]

_NEXT_MARKERS = [
    r"\n\s*FORMACI[ÓO]N\s+COMPLEMENTARIA\b",
    r"\n\s*FORMACION\s+COMPLEMENTARIA\b",
    r"\n\s*FORMACI[ÓO]N\s+DE\s+RECURSOS\s+HUMANOS\b",
    r"\n\s*RECURSOS\s+HUMANOS\b",
    r"\n\s*RRHH\b",
    r"\n\s*ANTECEDENTES\b",
    r"\n\s*PRODUCCI[ÓO]N\b",
    r"\n\s*PUBLICACIONES\b",
    r"\n\s*ACTIVIDADES\b",
    r"\n\s*EXPERIENCIA\b",
    r"\n\s*CARGOS\b",
    r"\n\s*CURSOS\s+Y\s+CAPACITACIONES\b",
    r"\n\s*CURSOS\s+E\s+CAPACITACIONES\b",
]

_COMP_HEADERS = [
    r"\bFORMACI[ÓO]N\s+COMPLEMENTARIA\b",
    r"\bFORMACION\s+COMPLEMENTARIA\b",
]

_COMP_END_MARKERS = _NEXT_MARKERS + [
    r"\n\s*ANTECEDENTES\s+EN\s+CYT\b",
    r"\n\s*IDIOMAS\b",
]

_RE_NOISE_LINE = re.compile(
    r"(?:CVar\s+ES\s+UNA|Fecha\s+de\s+generaci|MINISTERIO\s+DE\s+CIENCIA|^\s*\d{1,3}\s*$)",
    re.IGNORECASE,
)

_RE_CURSO_YEAR = re.compile(
    r"(?im)^\s*(?:(?:\d{2}/\d{4})|(?:19|20)\d{2})\s*[-–]\s*(?:(?:\d{2}/\d{4})|(?:19|20)\d{2}|Actualidad)\s+",
)

_RE_CURSO_HORAS = re.compile(
    r"(?is)\b(?:Entre|Hasta)\s+\d{1,4}\s*(?:Y\s+\d{1,4})?\s*horas\b",
)

_RE_IDIOMA_LINE = re.compile(
    r"(?im)^(?:Ingl[eé]s|Franc[eé]s|Portugu[eé]s|Italiano|Alem[aá]n|Chino|Japon[eé]s)\s*\[",
)

_ANTECEDENTES_HEADERS = [
    r"\bANTECEDENTES\s+EN\s+CYT\b",
    r"\bANTECEDENTES\b",
]

_RE_ANTECEDENTES_DATE = re.compile(
    r"(?im)^\s*(?:\d{2}/\d{4}|\d{4})\s*[-–]\s*(?:\d{2}/\d{4}|\d{4}|Actualidad)\s*$",
)

# inicio de entrada (cuando el CVAr viene bien seccionado)
_RE_ENTRY_START = re.compile(
    r"(?im)^\s*(?:[-•·*]|\&\#61485;)?\s*"
    r"("
    r"Diplomatura|Diplomado|Diploma|"
    r"Posdoctorado|Postdoctorado|"
    r"Doctorado|Doctor\s+en|Doctor\s+de\s+la\s+Universidad|Doctor(?:a)?\b|"
    r"Maestr[ií]a|Mag[ií]ster|Magister|"
    r"Especializaci[oó]n|Especialidad|Especialista|"
    r"Profesorado|Profesor\s+Superior|Profesor\s+Universitario|Profesor(?:a)?\s+en|"
    r"Abogad[oa]s?|Notari[ao]s?|"
    r"Licenciatura|Licenciad[oa](?:\s+en)?|"
    r"Ingenier[oa]s?|Contador(?:a)?s?|Arquitect[oa]s?|"
    r"Enfermer[ií]a|Enfermer[oa]s?|"
    r"T[eé]cnica\s+Universitaria|Tecnicatura"
    r")\b",
    re.IGNORECASE
)

_TITLE_ENTRY_ANCHORS = (
    r"Diplomatura|Diplomado|Diploma|"
    r"Posdoctorado|Postdoctorado|"
    r"Doctorado|Doctor\s+en|Doctor\s+de\s+la\s+Universidad|Doctor(?:a)?\b|"
    r"Maestr[ií]a|Mag[ií]ster|Magister|"
    r"Especializaci[oó]n|Especialidad|Especialista|"
    r"Profesorado|Profesor\s+Superior|Profesor\s+Universitario|Profesor(?:a)?\s+en|"
    r"Abogad[oa]s?|Notari[ao]s?|"
    r"Licenciatura|Licenciad[oa](?:\s+en)?|"
    r"Ingenier[oa]s?|Contador(?:a)?s?|Arquitect[oa]s?|"
    r"Farmac[eé]utic[oa]s?|Bioqu[ií]mic[oa]s?|M[eé]dic[oa]s?|"
    r"Enfermer[ií]a|Enfermer[oa]s?|"
    r"T[eé]cnica\s+Universitaria|Tecnicatura"
)

_RE_ENTRY_HEADER_LINE = re.compile(
    rf"(?im)^\s*(?:[-•·*]|\&\#61485;)?\s*(?:{_TITLE_ENTRY_ANCHORS})\b",
    re.IGNORECASE,
)

_RE_NAME_REPEAT_LINE = re.compile(
    r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\s.'-]+,\s*[A-ZÁÉÍÓÚÜÑ]",
    re.IGNORECASE,
)

_RE_IN_PROGRESS = re.compile(
    r"\b(Actualidad|En\s+curso|Cursando|Actualmente|Vigente|Hasta\s+la\s+actualidad|A\s+la\s+fecha)\b",
    re.IGNORECASE
)

_RE_FINISH = re.compile(
    r"A(?:ñ|n)o\s+de\s+(?:finalizaci[oó]n|obtenci[oó]n|graduaci[oó]n)\s*[:\-–]?\s*(?:\d{2}/\d{4}|19\d{2}|20\d{2})",
    re.IGNORECASE
)

_RE_SITUACION_COMPLETO = re.compile(
    r"Situaci[oó]n\s+del\s+nivel\s*[:\-–]?\s*Completo",
    re.IGNORECASE
)

_RE_COMPLETION_CUES = re.compile(
    r"\b(finalizad[oa]|egresad[oa]|graduad[oa]|t[ií]tulo\s+obtenido|t[ií]tulo\s+otorgado|defendid[oa]|complet(?:o|ada))\b",
    re.IGNORECASE
)

# contexto que NO queremos que dispare posdoc (becas/rrhh)
_RE_BECARIO_CONTEXT = re.compile(
    r"\b(becari[oa]s?|beca|direcci[oó]n|co[- ]?direcci[oó]n|tesista|investigador/a|investigador)\b",
    re.IGNORECASE
)

# anclas institucionales típicas (para GRADO genérico)
_RE_INST_ANCHOR = re.compile(
    r"\b(FACULTAD|UNIVERSIDAD|INSTITUTO|ESCUELA|DEPARTAMENTO|CENTRO|COLEGIO)\b",
    re.IGNORECASE
)


def _extract_formacion_block(full_text: str) -> str:
    txt = _norm_spaces(full_text)
    start = None
    for h in _FORM_HEADERS:
        m = re.search(h, txt, flags=re.IGNORECASE)
        if m:
            start = m.end()
            break
    if start is None:
        return ""

    tail = txt[start:]
    end = len(tail)
    for mk in _NEXT_MARKERS:
        m2 = re.search(mk, tail, flags=re.IGNORECASE)
        if m2:
            end = min(end, m2.start())
    return tail[:end].strip()


def _split_entries(block: str) -> List[str]:
    if not block:
        return []

    # normalizamos líneas y eliminamos basura (pies de página CVar, nº de página)
    lines = [l.strip() for l in block.splitlines()]
    lines = [
        l for l in lines
        if l and l.lower() != "null" and not _RE_NOISE_LINE.search(l)
    ]

    entries: List[str] = []
    buf: List[str] = []

    for line in lines:
        if _RE_ENTRY_HEADER_LINE.search(line) and buf:
            entries.append("\n".join(buf).strip())
            buf = [line]
        else:
            buf.append(line)

    if buf:
        entries.append("\n".join(buf).strip())

    # Re-segmentar por títulos (CVAr con saltos de página entre ítems)
    blob = "\n".join(lines) if lines else block
    parts = re.split(rf"(?im)(?=^(?:{_TITLE_ENTRY_ANCHORS}))", blob)
    split_entries = [p.strip() for p in parts if p.strip()]
    if len(split_entries) > len(entries):
        entries = split_entries

    return entries


def _entry_completed(entry: str) -> bool:
    if _RE_IN_PROGRESS.search(entry):
        return False
    if _RE_FINISH.search(entry):
        return True
    if _RE_SITUACION_COMPLETO.search(entry):
        return True
    if _RE_COMPLETION_CUES.search(entry):
        return True
    return False


def _finish_token(entry: str) -> str:
    m = _RE_FINISH.search(entry)
    if m:
        return re.sub(r"\s+", "", m.group(0))
    if _RE_SITUACION_COMPLETO.search(entry):
        return "COMPLETO"
    if _RE_COMPLETION_CUES.search(entry):
        return "FINALIZADO"
    return ""


def _first_line(entry: str) -> str:
    for l in entry.splitlines():
        l = l.strip()
        if l and l.lower() != "null":
            return l
    return ""


def _has_institution_anchor(entry: str) -> bool:
    return bool(_RE_INST_ANCHOR.search(entry))


def _classify_structural(entry: str) -> str:
    """
    Clasificación estructural CORRECTA para CVAR (Argentina).

    Reglas:
    - Diplomaturas siempre primero (no son grado ni posgrado)
    - Doctorado / Maestría / Especialización explícitos
    - Profesor en Enseñanza Media y Superior = TÍTULO DE GRADO
    - Profesorado SOLO si dice explícitamente 'Profesorado'
    - Grado SOLO si hay FACULTAD/UNIVERSIDAD + finalización
    """

    head = _first_line(entry).lower()

    # 1️⃣ Diplomaturas (siempre excluidas de grado/posgrado)
    if re.search(r"\bdiplomatur|\bdiplomad|\bdiploma\b", head):
        return "diplomatura"

    # 2️⃣ Doctorado (incluye "Doctora en …", no solo "Doctor")
    if re.search(r"\bdoctorad[oa]?\b|\bdoctor(?:a)?\b", head):
        return "doctorado"

    # 3️⃣ Maestría
    if re.search(r"\bmaestr[ií]a|\bmag[ií]ster|\bmagister\b", head):
        return "maestria"

    # 4️⃣ Especialización
    if re.search(r"\bespecializaci[oó]n|\bespecialista\b", head):
        return "especializacion"

    # 5️⃣ Profesor superior / profesorado universitario
    if re.search(r"\bprofesor\s+superior\b", head):
        return "profesorado"

    # 6️⃣ PROFESOR EN ENSEÑANZA MEDIA Y SUPERIOR = GRADO
    if re.search(r"\bprofesor\s+en\s+enseñanza\s+media\b", head):
        return "grado"

    # 7️⃣ Profesorado (carreras específicas)
    if re.search(r"\bprofesorado\b", head):
        return "profesorado"

    # 8️⃣ Títulos profesionales de grado (Abogado, Licenciado, Enfermería, etc.)
    if re.search(
        r"^(?:abogad[oa]s?|notari[ao]s?|licenciad[oa]s?|ingenier[oa]s?|contador(?:a)?s?|arquitect[oa]s?|"
        r"bioqu[ií]mic[oa]s?|farmac[eé]utic[oa]s?|m[eé]dic[oa]s?|enfermer[ií]a|enfermer[oa]s?)\b",
        head,
    ):
        return "grado"

    # 9️⃣ Grado estructural (cualquier carrera con ancla institucional)
    if _has_institution_anchor(entry) and _entry_completed(entry):
        return "grado"

    return "otro"


# ==========================================================
# Producción: artículos en bloque PUBLICACIONES
# ==========================================================

_PUB_BLOCK_END = [
    r"\n\s*OTROS\s+ANTECEDENTES\b",
    r"\n\s*FORMACI[ÓO]N\s+DE\s+RECURSOS\s+HUMANOS\b",
    r"\n\s*ANTECEDENTES\s+EN\s+CYT\b",
    r"\n\s*ANTECEDENTES\b",
]

_PUB_SUBSECTION_END = [
    r"(?i)\bTesis\b",
    r"(?i)\bLibros\b",
    r"(?i)\bCap[ií]tulos\b",
    r"(?i)\bTrabajos\b",
    r"(?i)\bDem[aá]s\s+producciones\b",
    r"(?i)\bInformes\b",
    r"(?i)\bProducci[oó]n\s+art[ií]stica\b",
]

_RE_EVENTO_EN_PUBLICACION = re.compile(
    r"(?i)\b(?:En\s+(?:Libro\s+de\s+Resúmenes|Libro\s+de\s+Resumenes|ACTAS|Actas|Congreso|Jornadas|"
    r"Symposium|Meeting|Workshop|Taller|BIOCELL|Biocell)|Presentado en el evento)\b",
)

_RE_VENUE_TRABAJO_EVENTO = re.compile(
    r"(?i)(?:"
    r"\bactas\b|"
    r"\blibro\s+de\s+(?:actas|resúmenes|resumenes)\b|"
    r"\b(?:jornadas|simposio|symposium|meeting|workshop|taller)\b|"
    r"\bcongreso\s+(?:internacional|nacional|latinoamericano|de|del)\b|"
    r"\bproceedings\b"
    r")",
)


def _is_trabajo_evento_publicado(snippet: str) -> bool:
    """Trabajo publicado en actas/congreso/jornadas (incl. bloque combinado CONICET)."""
    if not snippet or not re.search(r"(?:19|20)\d{2}", snippet):
        return False
    if re.search(r"(?i)^\d{4}\s*[-–]\s*Evento\s*:", snippet.strip()):
        return False
    if re.search(r"(?i)Presentado en el evento", snippet):
        return True
    if _RE_EVENTO_EN_PUBLICACION.search(snippet):
        return True
    m = re.search(r"(?i)\bEn\s*:", snippet)
    if not m:
        return False
    return bool(_RE_VENUE_TRABAJO_EVENTO.search(snippet[m.end() :]))

_RE_NEW_ARTICLE_LINE = re.compile(
    r"^(?:"
    r"[A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúñü0-9 ,.;:'\-\(\)]+?\.\s*\""
    r"|\.?\s*\"[A-ZÁÉÍÓÚÜÑa-záéíóúñü]"
    r")",
    re.UNICODE,
)

_RE_PAGE_HEADER_NAME = re.compile(
    r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\s.'-]+,\s*[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\s.'-]+$",
    re.MULTILINE,
)

_RE_JOURNAL_CUE = re.compile(
    r"(?i)\b(?:revista|journal|proceedings|research|technology|science|medicina|biocell|"
    r"international|cuadernos|hematolog|uninter|ied|nano|pharmaceutical|drug|targets|"
    r"hipertension|bioan[aá]lisis|therapeutic|faseb|learning|innovaci[oó]n pedag[oó]gica)\b|"
    r"\bnum\.?\s*\d+|\bvol\.?\s*\d+|\(\s*(?:19|20)\d{2}\s*\)\s*:|,\s*\(\s*(?:19|20)\d{2}\s*\)",
)


def _extract_publicaciones_block(full_text: str) -> str:
    txt = _norm_spaces(full_text)
    m = re.search(r"\bPUBLICACIONES\b", txt, flags=re.IGNORECASE)
    if not m:
        return ""
    tail = txt[m.start():]
    end = len(tail)
    for mk in _PUB_BLOCK_END:
        m2 = re.search(mk, tail, flags=re.IGNORECASE)
        if m2:
            end = min(end, m2.start())
    return tail[:end].strip()


def _extract_publicaciones_subsection(block: str, subsection: str) -> str:
    if not block:
        return ""
    m = re.search(rf"(?i)\b{subsection}\b", block)
    if not m:
        return ""
    tail = block[m.end():]
    end = len(tail)
    for mk in _PUB_SUBSECTION_END:
        m2 = re.search(mk, tail)
        if m2:
            end = min(end, m2.start())
    return tail[:end].strip()


def _is_publication_noise_line(line: str) -> bool:
    """Filtra pies de página; no descarta líneas de autor con comillas (ej. Larrea, Claudio. "Título")."""
    if _RE_NOISE_LINE.search(line):
        return True
    if '"' in line or re.search(r"\bISBN\b", line, re.I):
        return False
    if _RE_PAGE_HEADER_NAME.match(line) and line.upper() == line.replace("ñ", "Ñ"):
        return True
    if _RE_NAME_REPEAT_LINE.match(line) and not re.search(r"\b(?:revista|journal|proceedings|num\.|vol\.)\b", line, re.I):
        # Encabezado de página "APELLIDO, NOMBRE" sin cuerpo de cita
        if len(line.split()) <= 6 and "." not in line[10:]:
            return True
    return False


def _merge_publicacion_lines(block: str) -> List[str]:
    """Agrupa líneas del bloque Artículos en citas completas (autor + título + revista + año)."""
    if not block or not block.strip():
        return []

    lines: List[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.lower() == "null":
            continue
        if re.match(
            r"^(?:PUBLICACIONES|Art[ií]culos|Libros(?:,|\b)|Cap[ií]tulos|Tesis|Trabajos|Dem[aá]s)\b",
            line,
            re.IGNORECASE,
        ):
            continue
        if _is_publication_noise_line(line):
            continue
        if re.match(r"^\d{1,3}\.?\s*$", line):
            continue
        lines.append(line)

    if not lines:
        return []

    entries: List[str] = []
    buf: List[str] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        text = re.sub(r"\s+", " ", " ".join(buf)).strip()
        if text:
            entries.append(text)
        buf = []

    for line in lines:
        is_title_continuation = bool(re.match(r'^[\w"].*"\s*\.', line)) or bool(
            re.match(r"^[a-záéíóúñü(]", line) and buf
        )
        is_new_article = bool(_RE_NEW_ARTICLE_LINE.match(line)) and not is_title_continuation

        if is_new_article and buf:
            flush()
        buf.append(line)

        joined = re.sub(r"\s+", " ", " ".join(buf))
        if re.search(r'"[^"]{8,400}"', joined) and re.search(r"(?:\(\s*(?:19|20)\d{2}\s*\)|,\s*(?:19|20)\d{2}\b)", joined):
            flush()

    flush()
    return entries


def _extract_articulo_title(snippet: str) -> str:
    m = re.search(r'"([^"]{8,400})"', snippet)
    return m.group(1).strip() if m else ""


def _extract_articulo_year(snippet: str) -> str:
    years = re.findall(r"(?:\(\s*((?:19|20)\d{2})\s*\)|,\s*((?:19|20)\d{2})\b|\.\s*((?:19|20)\d{2})\s*\.)", snippet)
    flat = [y for group in years for y in group if y]
    return flat[-1] if flat else ""


def _is_valid_articulo_row(snippet: str) -> bool:
    if not snippet or '"' not in snippet:
        return False

    title = _extract_articulo_title(snippet)
    if len(title) < 8:
        return False

    year = _extract_articulo_year(snippet)
    if not year:
        return False

    if re.search(r"\bTesis\s+de\b", snippet, re.IGNORECASE):
        return False
    if re.search(r"\bISBN\b", snippet, re.IGNORECASE):
        return False
    if re.search(r"En:\s*\(ed\.?\)|\bEn:\s*Larrea", snippet, re.IGNORECASE):
        return False
    if _is_trabajo_evento_publicado(snippet):
        return False
    if re.search(r"\bMaterial\s+Did[aá]ctico\b", snippet, re.IGNORECASE):
        return False
    if re.search(r"Traducci[oó]n\s+publicada\s+en\s+libro", snippet, re.IGNORECASE):
        return False
    if re.search(r"Traducci[oó]n\s+publicada", snippet, re.IGNORECASE):
        return bool(re.search(r"Traducci[oó]n\s+publicada\s+en\s+revista", snippet, re.IGNORECASE))

    # Fragmentos sueltos sin revista ni autor (restos de merge incorrecto)
    has_author = bool(re.search(r'[A-Za-zÁÉÍÓÚÜÑáéíóúñü]\.\s*"', snippet))
    has_journal = bool(_RE_JOURNAL_CUE.search(snippet))
    if not has_author and not has_journal:
        return False

    return True


def _dedupe_publication_rows(rows: List[str]) -> Tuple[int, str]:
    seen = set()
    evidence = ""
    count = 0
    for row in rows:
        snippet = re.sub(r"\s+", " ", row).strip()
        if not _is_valid_articulo_row(snippet):
            continue
        title = _extract_articulo_title(snippet)
        year = _extract_articulo_year(snippet)
        key = (_norm_key(title[:120]), year)
        if key in seen:
            continue
        seen.add(key)
        count += 1
        if not evidence:
            evidence = snippet[:260]
    return count, evidence


def _count_articulos_revistas(full_text: str) -> Tuple[int, str]:
    block = _extract_publicaciones_block(full_text)
    if not block:
        return 0, ""

    art_block = _extract_publicaciones_subsection(block, "Art[ií]culos")
    target = art_block if art_block else block
    return _dedupe_publication_rows(_merge_publicacion_lines(target))


def _extract_poster_presentaciones(block: str) -> List[str]:
    """Pósters/resúmenes con fecha M/YYYY y 'Presentado en el evento'."""
    if not block or not block.strip():
        return []
    parts = re.split(
        r"(?im)(?=\d{1,2}/(?:19|20)\d{2}\s*[-–]\s*[A-ZÁÉÍÓÚÜÑ])",
        block,
    )
    out: List[str] = []
    for part in parts:
        snippet = re.sub(r"\s+", " ", part).strip()
        if len(snippet) < 30:
            continue
        if re.search(r"(?i)Presentado en el evento", snippet):
            out.append(snippet[:500])
    return out


def _count_trabajos_eventos_publicados(full_text: str) -> Tuple[int, str]:
    blocks: List[str] = []
    pub = _extract_publicaciones_block(full_text)
    if pub:
        blocks.append(pub)
    # En CVs cortos los pósters a veces quedan al final de la pestaña Eventos
    evt_m = re.search(r"(?is)PARTICIPACI[ÓO]N\s+EN\s+EVENTOS.*", full_text)
    if evt_m:
        blocks.append(evt_m.group(0))
    if not blocks:
        return 0, ""

    count = 0
    evidence = ""
    seen = set()

    def _add(snippet: str) -> None:
        nonlocal count, evidence
        if not snippet or not re.search(r"(?:19|20)\d{2}", snippet):
            return
        key = _norm_key(snippet[:180])
        if key in seen:
            return
        seen.add(key)
        count += 1
        if not evidence:
            evidence = snippet[:260]

    for block in blocks:
        for poster in _extract_poster_presentaciones(block):
            _add(poster)
        for row in _merge_publicacion_lines(block):
            snippet = re.sub(r"\s+", " ", row).strip()
            if re.search(r"(?i)^\d{4}\s*[-–]\s*Evento\s*:", snippet):
                continue
            if not _is_trabajo_evento_publicado(snippet):
                continue
            _add(snippet)
    return count, evidence


def _count_idiomas(full_text: str) -> Tuple[int, str]:
    block = _extract_complementaria_idiomas_block(full_text)
    if not block:
        return 0, ""

    seen = set()
    evidence = ""
    count = 0
    for line in block.splitlines():
        line = line.strip()
        if not line or _RE_NOISE_LINE.search(line):
            continue
        m = re.search(
            r"(Ingl[eé]s|Franc[eé]s|Portugu[eé]s|Italiano|Alem[aá]n|Chino|Japon[eé]s)\s*\[[^\]]+\]",
            line,
            re.IGNORECASE,
        )
        if not m:
            continue
        key = _norm_key(m.group(0))
        if key in seen:
            continue
        seen.add(key)
        count += 1
        if not evidence:
            evidence = line[:260]
    return count, evidence


def _count_capitulos_libro(full_text: str) -> Tuple[int, str]:
    block = _extract_publicaciones_block(full_text)
    if not block:
        return 0, ""

    count = 0
    evidence = ""
    for row in _merge_publicacion_lines(block):
        snippet = re.sub(r"\s+", " ", row).strip()
        if _is_trabajo_evento_publicado(snippet):
            continue
        if not (
            re.search(r"En:\s*\(ed\.?\)", snippet, re.IGNORECASE)
            or re.search(r"\bCap[ií]tulo\b", snippet, re.IGNORECASE)
            or re.search(
                r'(?i)"[^"]+"\s*\.\s*En\s+[A-ZÁÉÍÓÚÜÑ]|'
                r'\bEn:\s*[^"]*\(ed\.?\)|\bEn:\s*[^(]+\(ed\.?\)',
                snippet,
            )
        ):
            continue
        count += 1
        if not evidence:
            evidence = snippet[:260]
    return count, evidence


def _extract_complementaria_block(full_text: str) -> str:
    txt = _norm_spaces(full_text)
    start = None
    for h in _COMP_HEADERS:
        m = re.search(h, txt, flags=re.IGNORECASE)
        if m:
            start = m.end()
            break
    if start is None:
        return ""

    tail = txt[start:]
    end = len(tail)
    for mk in _COMP_END_MARKERS:
        m2 = re.search(mk, tail, flags=re.IGNORECASE)
        if m2:
            end = min(end, m2.start())
    result = tail[:end].strip()
    m_idioma = _RE_IDIOMA_LINE.search(result)
    if m_idioma:
        result = result[:m_idioma.start()].strip()
    return result


def _extract_complementaria_idiomas_block(full_text: str) -> str:
    """Bloque complementario completo (incluye idiomas), sin cortar en idiomas."""
    txt = _norm_spaces(full_text)
    start = None
    for h in _COMP_HEADERS:
        m = re.search(h, txt, flags=re.IGNORECASE)
        if m:
            start = m.end()
            break
    if start is None:
        return ""

    tail = txt[start:]
    end = len(tail)
    for mk in _COMP_END_MARKERS:
        m2 = re.search(mk, tail, flags=re.IGNORECASE)
        if m2:
            end = min(end, m2.start())
    return tail[:end].strip()


def _extract_antecedentes_cyt_block(full_text: str) -> str:
    txt = _norm_spaces(full_text)
    start = None
    for h in _ANTECEDENTES_HEADERS:
        m = re.search(h, txt, flags=re.IGNORECASE)
        if m:
            start = m.end()
            break
    if start is None:
        return ""

    tail = txt[start:]
    end_markers = [
        r"\n\s*FORMACI[ÓO]N\s+DE\s+RECURSOS\s+HUMANOS\b",
        r"\n\s*FINANCIAMIENTO\b",
        r"\n\s*PUBLICACIONES\b",
        r"\n\s*PARTICIPACI[ÓO]N\s+EN\s+EVENTOS\b",
        r"\n\s*OTROS\s+ANTECEDENTES\b",
    ]
    end = len(tail)
    for mk in end_markers:
        m2 = re.search(mk, tail, flags=re.IGNORECASE)
        if m2:
            end = min(end, m2.start())
    return tail[:end].strip()


_RE_ANTECEDENTES_ROLE_LINE = re.compile(
    r"^\s*(?:Responsable|Gerente|Director|Coordinador|Profesor|Docente|Asesor|Consultor|"
    r"Auditor|Perit|Encargad|Jefe|Consejer|Secretari|Decan|Vicerrector|Rector)\b",
    re.I,
)


def _split_antecedentes_entries(block: str) -> List[str]:
    if not block:
        return []
    lines = []
    for l in block.splitlines():
        line = l.strip()
        if not line or _RE_NOISE_LINE.search(line):
            continue
        if _RE_NAME_REPEAT_LINE.match(line) and not _RE_ANTECEDENTES_ROLE_LINE.match(line):
            continue
        lines.append(line)
    blob = "\n".join(lines)
    parts = re.split(
        r"(?im)(?=^(?:\d{2}/\d{4}|\d{4})\s*[-–]\s*(?:\d{2}/\d{4}|\d{4}|Actualidad)\s*(?:\n|$)|"
        r"^\d{4}\s+Categor[ií]a\s+)",
        blob,
    )
    return [p.strip() for p in parts if p.strip()]


def _count_antecedentes_cyt(full_text: str) -> Tuple[Dict[str, int], Dict[str, str]]:
    block = _extract_antecedentes_cyt_block(full_text)
    counts = {"gestion": 0, "profesional": 0}
    evidence = {"gestion": "", "profesional": ""}

    for entry in _split_antecedentes_entries(block):
        snippet = re.sub(r"\s+", " ", entry).strip()
        if re.search(
            r"\b(?:Profesor(?:a)?|Docente|C[aá]tedra|JTP|Ayudante|Jefe\s+de\s+trabajos\s+pr[aá]cticos)\b",
            snippet,
            re.I,
        ):
            continue
        if re.search(
            r"\b(?:Coordinador(?:a)?|Director(?:a)?|Secretari[oa]|Decan[oa]|Vicerrector(?:a)?|"
            r"Rector(?:a)?|Consejer[oa]|Jefe\s+de|Subprograma|Asistente\s+Ejecutiv[a]?|"
            r"Asistente\s+de\s+Investigaci[oó]n|"
            r"Miembro\s+(?:del\s+)?(?:comit[eé]|consejo)\s+de\s+investigaci[oó]n|"
            r"Integrante\s+del\s+Comit[eé])\b",
            snippet,
            re.I,
        ):
            counts["gestion"] += 1
            if not evidence["gestion"]:
                evidence["gestion"] = snippet[:260]
            continue
        if re.search(
            r"\b(?:Asesor(?:a)?|Consultor(?:a)?|Perit(?:o|aje)?|Auditor(?:a)?|Gerente|Responsable)\b",
            snippet,
            re.I,
        ):
            counts["profesional"] += 1
            if not evidence["profesional"]:
                evidence["profesional"] = snippet[:260]

    return counts, evidence


_RE_IDIOMA_LINE_INLINE = re.compile(
    r"\b(?:Ingl[eé]s|Franc[eé]s|Portugu[eé]s|Italiano|Alem[aá]n|Chino|Japon[eé]s)\s*\[",
    re.I,
)


def _strip_idioma_lines(entry: str) -> str:
    """Quita líneas de idioma que a veces quedan pegadas al último curso del bloque."""
    lines = []
    for line in (entry or "").splitlines():
        if _RE_IDIOMA_LINE_INLINE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _split_curso_entries(block: str) -> List[str]:
    if not block:
        return []
    lines = [
        l.strip()
        for l in block.splitlines()
        if l.strip() and l.lower() != "null" and not _RE_NOISE_LINE.search(l)
    ]
    blob = "\n".join(lines)
    parts = re.split(_RE_CURSO_YEAR, blob)
    entries = [p.strip() for p in parts if p.strip()]
    if not entries and blob.strip():
        return [blob.strip()]
    return entries


def _count_cursos(full_text: str) -> Tuple[int, int, str]:
    """
    Devuelve (cursos_con_horas, cursos_sin_horas, evidencia).
    Cuenta ítems de Formación complementaria por bloque año-año.
    """
    block = _extract_complementaria_block(full_text)
    if not block:
        return 0, 0, ""

    con_horas = 0
    sin_horas = 0
    evidence = ""
    seen = set()

    for entry in _split_curso_entries(block):
        entry = _strip_idioma_lines(entry)
        snippet = re.sub(r"\s+", " ", entry).strip()
        if len(snippet) < 12:
            continue
        key = _norm_key(snippet[:160])
        if key in seen:
            continue
        seen.add(key)

        if _RE_CURSO_HORAS.search(entry):
            con_horas += 1
            if not evidence:
                evidence = snippet[:260]
        else:
            sin_horas += 1

    return con_horas, sin_horas, evidence


def _count_formacion(full_text: str) -> Tuple[Dict[str, int], Dict[str, str]]:
    """
    Devuelve:
    - counts por tipo (doctorado, maestria, especializacion, grado, profesorado, posdoc, diplomatura)
    - evidence por tipo (1ra evidencia para mostrar)
    """
    block = _extract_formacion_block(full_text)
    entries = _split_entries(block)

    counts = {
        "doctorado": 0,
        "maestria": 0,
        "especializacion": 0,
        "grado": 0,
        "profesorado": 0,
        "posdoc": 0,
        "diplomatura": 0,
    }
    evidence = {k: "" for k in counts.keys()}

    seen = set()

    for e in entries:
        # posdoc se detecta aparte por texto (no por “grado” genérico)
        if re.search(r"\b(posdoctorado|postdoctorado)\b", e, re.IGNORECASE):
            tipo = "posdoc"
        else:
            tipo = _classify_structural(e)

        if tipo not in counts:
            continue

        # posdoc: evitar falsas detecciones por contexto beca/rrhh
        if tipo == "posdoc" and _RE_BECARIO_CONTEXT.search(e):
            continue

        if not _entry_completed(e):
            continue

        title = _first_line(e)
        fin = _finish_token(e)
        key = (tipo, _norm_key(title), _norm_key(fin))
        if key in seen:
            continue
        seen.add(key)

        counts[tipo] += 1
        if not evidence[tipo]:
            evidence[tipo] = re.sub(r"\s+", " ", e.strip())[:260]

    return counts, evidence


# ==========================================================
# SCORE
# ==========================================================
def _counts_from_structured(structured: Dict[str, Any], text: str) -> Dict[str, Any]:
    """Usa conteos del JSON estructurado; recalcula evidencias desde el texto."""
    raw = structured.get("counts", {})
    parsed = structured.get("items", {})
    form_counts = raw.get("formacion") or _count_formacion(text)[0]
    _, form_evidence = _count_formacion(text)
    _, _, cursos_evidence = _count_cursos(text)
    _, idiomas_evidence = _count_idiomas(text)
    _, articulos_evidence = _count_articulos_revistas(text)
    _, trabajos_eventos_evidence = _count_trabajos_eventos_publicados(text)
    _, capitulos_evidence = _count_capitulos_libro(text)
    antecedentes_counts, antecedentes_evidence = _count_antecedentes_cyt(text)

    rrhh = raw.get("rrhh", {}) or parsed.get("formacion_rrhh", {}).get("counts", {})
    fin = raw.get("financiamiento", {}) or parsed.get("financiamiento_cyt", {}).get("counts", {})
    ev = raw.get("evaluacion", {}) or parsed.get("evaluacion_gestion", {}).get("counts", {})
    otros = raw.get("otros", {}) or parsed.get("otros_antecedentes", {}).get("counts", {})

    return {
        "form_counts": form_counts,
        "form_evidence": form_evidence,
        "cursos_con_horas": int(raw.get("cursos_con_horas", 0)),
        "cursos_sin_horas": int(raw.get("cursos_sin_horas", 0)),
        "cursos_evidence": cursos_evidence,
        "idiomas_count": int(raw.get("idiomas", 0)),
        "idiomas_evidence": idiomas_evidence,
        "articulos_count": int(raw.get("articulos_revista", 0)),
        "articulos_evidence": articulos_evidence,
        "articulos_doi_count": int(raw.get("articulos_doi", 0)),
        "libros_isbn_count": int(raw.get("libros_isbn", 0)),
        "trabajos_eventos_count": int(raw.get("trabajos_evento_publicados", 0)),
        "trabajos_eventos_evidence": trabajos_eventos_evidence,
        "capitulos_count": int(raw.get("capitulos_libro", 0)),
        "capitulos_evidence": capitulos_evidence,
        "rrhh_counts": rrhh,
        "rrhh_evidence": parsed.get("formacion_rrhh", {}).get("evidence", {}),
        "fin_counts": fin,
        "fin_evidence": parsed.get("financiamiento_cyt", {}).get("evidence", {}),
        "ev_counts": ev,
        "ev_evidence": parsed.get("evaluacion_gestion", {}).get("evidence", {}),
        "eventos_count": int(raw.get("eventos", 0)),
        "eventos_premios": int(raw.get("eventos_premios", 0)),
        "eventos_premios_evidence": parsed.get("eventos_cyt", {}).get("evidence", {}).get("premios", ""),
        "eventos_evidence": parsed.get("eventos_cyt", {}).get("evidence", {}).get("eventos", ""),
        "actividades_prof_count": int(raw.get("actividades_profesionales", 0)),
        "actividades_prof_evidence": parsed.get("actividades_profesionales", {}).get("evidence", {}).get(
            "actividades_profesionales", ""
        ),
        "extension_count": int(raw.get("extension_actividades", 0)),
        "extension_evidence": parsed.get("extension", {}).get("evidence", {}).get("extension", ""),
        "otros_counts": otros,
        "otros_evidence": parsed.get("otros_antecedentes", {}).get("evidence", {}),
        "antecedentes_counts": {
            "gestion": int(raw.get("antecedentes_gestion", antecedentes_counts.get("gestion", 0))),
            "profesional": int(raw.get("antecedentes_profesional", antecedentes_counts.get("profesional", 0))),
        },
        "antecedentes_incentivos": int(raw.get("antecedentes_incentivos", 0)),
        "antecedentes_incentivos_evidence": raw.get("antecedentes_incentivos_evidence", ""),
        "antecedentes_evidence": antecedentes_evidence,
    }


def score_structured(
    structured: Dict[str, Any],
    criteria: Dict[str, Any],
    evidence_max_chars: int = 260,
) -> Tuple[List[ItemResult], Dict[str, float], float, str, Dict[str, Any]]:
    from cvar_parser import scoring_text_from_structured

    text = _norm_spaces(scoring_text_from_structured(structured))
    return _score_with_counts(
        text,
        criteria,
        _counts_from_structured(structured, text),
        evidence_max_chars=evidence_max_chars,
    )


def _score_with_counts(
    text: str,
    criteria: Dict[str, Any],
    counts_bundle: Dict[str, Any],
    evidence_max_chars: int = 260,
) -> Tuple[List[ItemResult], Dict[str, float], float, str, Dict[str, Any]]:
    sections = criteria.get("sections", {})
    categorias = criteria.get("categorias", {})

    form_counts = counts_bundle["form_counts"]
    form_evidence = counts_bundle["form_evidence"]
    cursos_con_horas = counts_bundle["cursos_con_horas"]
    cursos_sin_horas = counts_bundle["cursos_sin_horas"]
    cursos_evidence = counts_bundle["cursos_evidence"]
    idiomas_count = counts_bundle["idiomas_count"]
    idiomas_evidence = counts_bundle["idiomas_evidence"]
    articulos_count = counts_bundle["articulos_count"]
    articulos_evidence = counts_bundle["articulos_evidence"]
    trabajos_eventos_count = counts_bundle["trabajos_eventos_count"]
    trabajos_eventos_evidence = counts_bundle["trabajos_eventos_evidence"]
    capitulos_count = counts_bundle["capitulos_count"]
    capitulos_evidence = counts_bundle["capitulos_evidence"]
    antecedentes_counts = counts_bundle["antecedentes_counts"]
    antecedentes_evidence = counts_bundle["antecedentes_evidence"]
    rrhh_counts = counts_bundle.get("rrhh_counts", {})
    rrhh_evidence = counts_bundle.get("rrhh_evidence", {})
    fin_counts = counts_bundle.get("fin_counts", {})
    fin_evidence = counts_bundle.get("fin_evidence", {})
    ev_counts = counts_bundle.get("ev_counts", {})
    ev_evidence = counts_bundle.get("ev_evidence", {})
    eventos_count = counts_bundle.get("eventos_count", 0)
    eventos_evidence = counts_bundle.get("eventos_evidence", "")
    actividades_prof_count = counts_bundle.get("actividades_prof_count", 0)
    actividades_prof_evidence = counts_bundle.get("actividades_prof_evidence", "")
    extension_count = counts_bundle.get("extension_count", 0)
    extension_evidence = counts_bundle.get("extension_evidence", "")
    otros_counts = counts_bundle.get("otros_counts", {})
    otros_evidence = counts_bundle.get("otros_evidence", {})
    articulos_doi_count = counts_bundle.get("articulos_doi_count", 0)
    libros_isbn_count = counts_bundle.get("libros_isbn_count", 0)

    results: List[ItemResult] = []
    section_totals: Dict[str, float] = {}
    total_points = 0.0

    for section_name, sec in sections.items():
        sec_max = float(sec.get("max_points", 10**9))
        sec_sum = 0.0
        sec_indices: List[int] = []

        items = sec.get("items", {})
        for item_name, item in items.items():
            pattern = item.get("pattern", "")
            unit_points = float(item.get("unit_points", 0))
            item_max = float(item.get("max_points", 0))

            count = 0
            evidence = ""
            il = item_name.lower()
            sec_l = section_name.strip().lower()
            forma_struct_locked = False
            pub_struct_locked = False
            antecedentes_struct_locked = False
            rrhh_struct_locked = False
            fin_struct_locked = False
            ev_struct_locked = False
            eventos_struct_locked = False
            otros_struct_locked = False

            # =========================
            # OVERRIDE Formación académica y complementaria
            # =========================
            if sec_l.startswith("formación académica") or sec_l.startswith("formacion academica"):

                # Antes que Doctorado: "postdoctorado..." contiene la subcadena "doctorad".
                if il.strip().startswith("postdoctorado"):
                    count = form_counts["posdoc"]
                    evidence = form_evidence["posdoc"]
                    forma_struct_locked = True
                elif "doctorad" in il or il.strip().startswith("doctor"):
                    count = form_counts["doctorado"]
                    evidence = form_evidence["doctorado"]
                    forma_struct_locked = True
                elif "maestr" in il or "magister" in il or "magíster" in il:
                    count = form_counts["maestria"]
                    evidence = form_evidence["maestria"]
                    forma_struct_locked = True
                elif re.match(r"(?i)^especializ", item_name.strip()) or re.match(
                    r"(?i)^especialidad", item_name.strip()
                ):
                    count = form_counts["especializacion"]
                    evidence = form_evidence["especializacion"]
                    forma_struct_locked = True
                elif "título de grado" in il or "titulo de grado" in il or il.strip() == "grado":
                    count = form_counts["grado"]
                    evidence = form_evidence["grado"]
                    forma_struct_locked = True
                elif "profesorado" in il or "docencia universitaria" in il:
                    count = form_counts["profesorado"]
                    evidence = form_evidence["profesorado"]
                    forma_struct_locked = True
                # Solo el fallback "sin horas" usa Diplomatura estructural; "con horas" sigue por regex
                elif "sin horas" in il and "diplom" in il:
                    count = form_counts["diplomatura"]
                    evidence = form_evidence["diplomatura"]
                    forma_struct_locked = True
                elif "con horas" in il and "curso" in il:
                    count = cursos_con_horas
                    evidence = cursos_evidence
                    forma_struct_locked = True
                elif "sin horas" in il and "curso" in il:
                    count = cursos_sin_horas
                    evidence = cursos_evidence
                    forma_struct_locked = True
                elif "idioma" in il:
                    count = idiomas_count
                    evidence = idiomas_evidence
                    forma_struct_locked = True
                elif "nivel medio" in il or "nivel básico" in il or "nivel basico" in il:
                    count = 0
                    evidence = ""
                    forma_struct_locked = True
                else:
                    # otros ítems (becas línea CONICET…) siguen por regex
                    pass

            # =========================
            # OVERRIDE Producción científica (artículos)
            # =========================
            if sec_l.startswith("producción científica") or sec_l.startswith("produccion cientifica"):
                if il.startswith("artículos en revistas") or il.startswith("articulos en revistas"):
                    count = articulos_count
                    evidence = articulos_evidence
                    pub_struct_locked = True
                elif il.startswith("capítulos de libro") or il.startswith("capitulos de libro"):
                    count = capitulos_count
                    evidence = capitulos_evidence
                    pub_struct_locked = True
                elif "trabajos en eventos" in il or "actas" in il:
                    count = trabajos_eventos_count
                    evidence = trabajos_eventos_evidence
                    pub_struct_locked = True
                elif "doi" in il:
                    count = articulos_doi_count
                    evidence = articulos_evidence
                    pub_struct_locked = True
                elif "libros" in il and "isbn" in il:
                    count = libros_isbn_count
                    evidence = capitulos_evidence
                    pub_struct_locked = True

            # =========================
            # OVERRIDE Formación de recursos humanos
            # =========================
            if sec_l.startswith("formación de recursos humanos") or sec_l.startswith("formacion de recursos humanos"):
                rrhh_map = [
                    ("co-dirección de beca", "codireccion_beca"),
                    ("dirección de beca", "direccion_beca"),
                    ("co-dirección de tesis de doctorado", "codireccion_tesis_doctorado"),
                    ("dirección de tesis de doctorado", "direccion_tesis_doctorado"),
                    ("co-dirección de trabajo final de especialización", "codireccion_especializacion"),
                    ("dirección de trabajo final de especialización", "direccion_especializacion"),
                    ("co-dirección de maestría", "codireccion_maestria"),
                    ("dirección de maestría", "direccion_maestria"),
                    ("co-dirección de investigador", "codireccion_investigador_otra"),
                    ("dirección de investigador", "direccion_investigador_otra"),
                    ("dirección de personal de apoyo", "direccion_apoyo_id"),
                    ("co-dirección de personal de apoyo", "codireccion_apoyo_id"),
                    ("co-dirección de tesina", "codireccion_tesina_grado"),
                    ("dirección de tesina", "direccion_tesina_grado"),
                    ("dirección de pasantía", "direccion_pasantia"),
                ]
                for label, key in rrhh_map:
                    if label in il:
                        if key == "direccion_tesina_grado":
                            count = int(rrhh_counts.get("direccion_tesina_grado", 0)) + int(
                                rrhh_counts.get("codireccion_tesina_grado", 0)
                            )
                            evidence = (
                                rrhh_evidence.get("direccion_tesina_grado", "")
                                or rrhh_evidence.get("codireccion_tesina_grado", "")
                            )
                        else:
                            count = int(rrhh_counts.get(key, 0))
                            evidence = rrhh_evidence.get(key, "")
                        rrhh_struct_locked = True
                        break

            # =========================
            # OVERRIDE Financiamiento CyT
            # =========================
            if "financiamiento" in sec_l:
                fin_map = [
                    ("co-dirección de proyecto", "codireccion_proyecto"),
                    ("dirección de proyecto i+d", "direccion_proyecto"),
                    ("participación en proyecto", "participacion_proyecto"),
                    ("becario/a en proyecto", "estudiante_proyecto"),
                    ("beca (iniciación", "beca_financiamiento"),
                    ("estancia de i+d", "estancia_id"),
                    ("proyecto de extensión con dirección", "direccion_extension"),
                ]
                for label, key in fin_map:
                    if label in il:
                        if key == "participacion_proyecto":
                            count = sum(
                                int(fin_counts.get(k, 0))
                                for k in ("investigador_proyecto", "tecnico_proyecto", "participacion_proyecto")
                            )
                            evidence = (
                                fin_evidence.get("investigador_proyecto", "")
                                or fin_evidence.get("tecnico_proyecto", "")
                                or fin_evidence.get("participacion_proyecto", "")
                            )
                        else:
                            count = int(fin_counts.get(key, 0))
                            evidence = fin_evidence.get(key, "")
                        fin_struct_locked = True
                        break

            # =========================
            # OVERRIDE Evaluación y gestión editorial
            # =========================
            if "evaluación" in sec_l or "evaluacion" in sec_l:
                ev_map = [
                    ("gestión cyt", "gestion_comite"),
                    ("evaluación de programas", "evaluacion_programas"),
                    ("evaluación institucional", "evaluacion_institucional"),
                    ("evaluación académica puntual", "evaluacion_academica_puntual"),
                    ("evaluación de trabajos en revistas", "revisor_revista"),
                    ("jurado", "jurado"),
                    ("coneu", "conau"),
                    ("acreditación", "conau"),
                ]
                for label, key in ev_map:
                    if label in il:
                        count = int(ev_counts.get(key, 0))
                        evidence = ev_evidence.get(key, "")
                        ev_struct_locked = True
                        break

            # =========================
            # OVERRIDE Eventos y actividades profesionales
            # =========================
            if sec_l.startswith("participación en eventos") or sec_l.startswith("participacion en eventos"):
                if il.startswith("eventos cyt"):
                    count = eventos_count
                    evidence = eventos_evidence
                    eventos_struct_locked = True
                elif "premios" in il or "menciones" in il:
                    count = int(counts_bundle.get("eventos_premios", 0))
                    evidence = counts_bundle.get("eventos_premios_evidence", "")
                    eventos_struct_locked = True
                elif "actividades profesionales" in il:
                    count = actividades_prof_count + antecedentes_counts["profesional"]
                    evidence = actividades_prof_evidence or antecedentes_evidence.get("profesional", "")
                    eventos_struct_locked = True

            # =========================
            # OVERRIDE Otros antecedentes CyT
            # =========================
            if sec_l.startswith("otros antecedentes"):
                if "gestión universitaria" in il or "gestion universitaria" in il:
                    count = antecedentes_counts["gestion"]
                    evidence = antecedentes_evidence["gestion"]
                    otros_struct_locked = True
                elif "programa de incentivos" in il:
                    count = int(otros_counts.get("incentivos", 0)) + int(
                        counts_bundle.get("antecedentes_incentivos", 0)
                    )
                    evidence = otros_evidence.get("incentivos", "") or counts_bundle.get(
                        "antecedentes_incentivos_evidence", ""
                    )
                    otros_struct_locked = True
                elif "redes temáticas" in il:
                    count = int(otros_counts.get("redes", 0))
                    evidence = otros_evidence.get("redes", "")
                    otros_struct_locked = True
                elif "desarrollos tecnológicos" in il:
                    count = int(otros_counts.get("desarrollos", 0))
                    evidence = otros_evidence.get("desarrollos", "")
                    otros_struct_locked = True
                elif "extensión (charlas" in il or "extension (charlas" in il:
                    count = extension_count
                    evidence = extension_evidence
                    otros_struct_locked = True

            # =========================
            # DEFAULT: regex global
            # =========================
            struct_locked = any(
                [
                    forma_struct_locked,
                    pub_struct_locked,
                    antecedentes_struct_locked,
                    rrhh_struct_locked,
                    fin_struct_locked,
                    ev_struct_locked,
                    eventos_struct_locked,
                    otros_struct_locked,
                ]
            )
            if not struct_locked and pattern:
                count, evidence = _regex_match_count(
                    text, pattern, evidence_max_chars=evidence_max_chars
                )

            raw_points = count * unit_points
            capped_item_points = min(raw_points, item_max) if item_max >= 0 else raw_points

            results.append(
                ItemResult(
                    section=section_name,
                    item=item_name,
                    pattern=pattern,
                    count=count,
                    unit_points=unit_points,
                    raw_points=raw_points,
                    capped_item_points=capped_item_points,
                    item_max_points=item_max,
                    evidence=evidence[:evidence_max_chars] if evidence else "",
                )
            )
            sec_indices.append(len(results) - 1)
            sec_sum += capped_item_points

        if sec_sum > sec_max and sec_sum > 0:
            allocated = 0.0
            for j, idx in enumerate(sec_indices):
                r = results[idx]
                if j == len(sec_indices) - 1:
                    new_pts = round(sec_max - allocated, 2)
                else:
                    new_pts = round(r.capped_item_points * sec_max / sec_sum, 2)
                    allocated += new_pts
                results[idx] = ItemResult(
                    section=r.section,
                    item=r.item,
                    pattern=r.pattern,
                    count=r.count,
                    unit_points=r.unit_points,
                    raw_points=r.raw_points,
                    capped_item_points=new_pts,
                    item_max_points=r.item_max_points,
                    evidence=r.evidence,
                )
            sec_sum = sec_max
        else:
            sec_sum = min(sec_sum, sec_max)
        section_totals[section_name] = sec_sum
        total_points += sec_sum

    # categoría por umbral
    category = "VI"
    if categorias:
        ordered = sorted(
            categorias.items(),
            key=lambda kv: float(kv[1].get("min_points", 0)),
            reverse=True
        )
        for cat, info in ordered:
            if total_points >= float(info.get("min_points", 0)):
                category = cat
                break

    return results, section_totals, total_points, category, categorias


def score_text(
    text: str,
    criteria: Dict[str, Any],
    evidence_max_chars: int = 260,
    structured: Optional[Dict[str, Any]] = None,
) -> Tuple[List[ItemResult], Dict[str, float], float, str, Dict[str, Any]]:
    text = _norm_spaces(text)
    if structured is not None:
        return score_structured(structured, criteria, evidence_max_chars=evidence_max_chars)

    from cvar_parser import parse_cvar

    structured = parse_cvar(text)
    return score_structured(structured, criteria, evidence_max_chars=evidence_max_chars)
