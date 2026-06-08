"""
Parsers tipados por pestaña CVar (RRHH, Financiamiento, Evaluación, Eventos, etc.).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

_RE_NOISE = re.compile(
    r"(?:CVar\s+ES\s+UNA|Fecha\s+de\s+generaci|MINISTERIO\s+DE\s+CIENCIA|^\s*\d{1,3}\s*$)",
    re.IGNORECASE,
)

_RE_NAME_REPEAT = re.compile(
    r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\s.'-]+,\s*[A-ZÁÉÍÓÚÜÑ]",
    re.IGNORECASE,
)

_RE_DATE_LINE = re.compile(
    r"(?im)^\s*(?:"
    r"\d{2}/\d{4}\s*[-–]\s*(?:\d{2}/\d{4}|Actualidad|\d{4}-\d{2}-\d{2}[^\n]{0,30})|"
    r"\d{4}\s*[-–]\s*(?:\d{4}|Actualidad|Evento\s*:)"
    r")"
)

_RE_BECARIO = re.compile(r"becari[oa](?:/a)?\s*:", re.I)
_RE_TESISTA = re.compile(r"tesista\s*:", re.I)
_RE_INVESTIGADOR = re.compile(r"investigador/a\s*:", re.I)
_RE_JEFE = re.compile(r"jefe\s*:", re.I)
_RE_PASANTE = re.compile(r"pasante\s*:", re.I)

_RE_SUBSECTION = re.compile(
    r"(?im)^\s*(?:"
    r"Participaci[oó]n en redes tem[aá]ticas|"
    r"Membres[ií]as en asociaciones|"
    r"Coordinaci[oó]n de proyectos de cooperaci[oó]n|"
    r"Desarrollos tecnol[oó]gicos|"
    r"Programa de Incentivos"
    r")"
)


def _norm_key(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\"'`´]", "", s)
    return s


def _snippet(entry: str, n: int = 260) -> str:
    return re.sub(r"\s+", " ", entry).strip()[:n]


def _clean_lines(block: str) -> List[str]:
    lines = []
    for raw in (block or "").splitlines():
        line = raw.strip()
        if not line or line.lower() == "null":
            continue
        if _RE_NOISE.search(line) or _RE_NAME_REPEAT.match(line):
            continue
        lines.append(line)
    return lines


def split_dated_entries(block: str) -> List[str]:
    """Divide un bloque CVar en entradas que comienzan con fecha o 'YYYY - Evento:'."""
    if not block or not block.strip():
        return []

    lines = _clean_lines(block)
    if not lines:
        return []

    blob = "\n".join(lines)
    parts = re.split(
        r"(?im)(?=^(?:\d{2}/\d{4}\s*[-–]\s*(?:\d{2}/\d{4}|Actualidad|\d{4}-\d{2}-\d{2})|\d{4}\s*[-–]\s*(?:\d{4}|Actualidad|Evento\s*:)))",
        blob,
    )
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 8]


def _dedupe_entries(entries: List[Dict[str, Any]], key_fields: Tuple[str, ...]) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, str]]:
    seen = set()
    items: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    evidence: Dict[str, str] = {}

    for ent in entries:
        tipo = ent.get("tipo", "otro")
        key = tuple(_norm_key(ent.get(f, "")) for f in key_fields)
        dedupe_key = (tipo,) + key
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(ent)
        counts[tipo] = counts.get(tipo, 0) + 1
        if tipo not in evidence:
            evidence[tipo] = ent.get("texto", "")[:260]

    return items, counts, evidence


# ---------------------------------------------------------------------------
# Formación de recursos humanos
# ---------------------------------------------------------------------------

def _extract_tesista_name(entry: str) -> str:
    m = re.search(r"Tesista\s*:\s*(.+)", entry, re.I)
    return (m.group(1) if m else "").strip()[:120]


def _classify_rrhh(entry: str) -> str:
    head = entry[:400]
    h = head.lower()

    if re.search(r"direcci[oó]n de beca", h) and not re.search(r"co-?direcci[oó]n", h):
        return "direccion_beca" if _RE_BECARIO.search(entry) else "otro"
    if re.search(r"co-?direcci[oó]n de beca", h):
        return "codireccion_beca" if _RE_BECARIO.search(entry) else "otro"
    if re.search(r"direcci[oó]n de tesis de doctorado", h) and not re.search(r"co-?direcci", h):
        return "direccion_tesis_doctorado" if _RE_TESISTA.search(entry) else "otro"
    if re.search(r"co-?direcci[oó]n de tesis de doctorado", h):
        return "codireccion_tesis_doctorado" if _RE_TESISTA.search(entry) else "otro"
    if re.search(r"direcci[oó]n de trabajo final de especializaci[oó]n", h) and not re.search(r"co-?direcci", h):
        return "direccion_especializacion" if _RE_TESISTA.search(entry) else "otro"
    if re.search(r"co-?direcci[oó]n de trabajo final de especializaci[oó]n", h):
        return "codireccion_especializacion" if _RE_TESISTA.search(entry) else "otro"
    if re.search(r"direcci[oó]n de trabajo final,\s*proyecto,\s*obra o tesis de maestr", h):
        return "direccion_maestria" if _RE_TESISTA.search(entry) else "otro"
    if re.search(r"co-?direcci[oó]n de trabajo final,\s*proyecto,\s*obra o tesis de maestr", h):
        return "codireccion_maestria" if _RE_TESISTA.search(entry) else "otro"
    if re.search(r"co-?direcci[oó]n de (?:tesina|trabajo final de grado|trabajo final)\b", h):
        return "codireccion_tesina_grado" if _RE_TESISTA.search(entry) else "otro"
    if re.search(r"direcci[oó]n de (?:tesina|trabajo final de grado|trabajo final)\b", h) and not re.search(r"co-?direcci", h):
        return "direccion_tesina_grado" if _RE_TESISTA.search(entry) else "otro"
    if re.search(r"direcci[oó]n de investigador\s*:\s*otra", h) and not re.search(r"co-?direcci", h):
        return "direccion_investigador_otra" if _RE_INVESTIGADOR.search(entry) else "otro"
    if re.search(r"co-?direcci[oó]n de investigador\s*:\s*otra", h):
        return "codireccion_investigador_otra" if _RE_INVESTIGADOR.search(entry) else "otro"
    if re.search(r"co-?direcci[oó]n de personal de apoyo a la i\+d", h):
        return "codireccion_apoyo_id" if _RE_JEFE.search(entry) else "otro"
    if re.search(r"direcci[oó]n de (?:formaci[oó]n acad[eé]mica|tareas de investigaci[oó]n).+pasante", h):
        return "direccion_pasantia" if _RE_PASANTE.search(entry) else "otro"
    return "otro"


def parse_formacion_rrhh(block: str) -> Dict[str, Any]:
    raw_entries = []
    for entry in split_dated_entries(block):
        tipo = _classify_rrhh(entry)
        if tipo == "otro":
            continue
        raw_entries.append(
            {
                "tipo": tipo,
                "texto": _snippet(entry, 400),
                "resumen": entry.split("\n", 1)[0][:200],
                "tesista": _extract_tesista_name(entry),
            }
        )

    items, counts, evidence = _dedupe_entries(raw_entries, ("resumen", "tesista"))
    return {"entradas": items, "counts": counts, "evidence": evidence}


# ---------------------------------------------------------------------------
# Financiamiento CyT
# ---------------------------------------------------------------------------

_RE_PERIOD_MY = re.compile(
    r"(?im)^\s*(\d{2})/(\d{4})\s*[-–]\s*(?:(\d{2})/(\d{4})|Actualidad)\b"
)
_RE_PERIOD_Y = re.compile(
    r"(?im)^\s*((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{4}|Actualidad)\b"
)


def _entry_finalizado(entry: str, ref: Optional[date] = None) -> bool:
    """True si el período del ítem terminó antes del mes de referencia."""
    ref = ref or date.today()
    head = entry.split("\n", 1)[0]
    m = _RE_PERIOD_MY.search(head)
    if m:
        if m.group(3) is None:
            return False
        end_year, end_month = int(m.group(4)), int(m.group(3))
        return (end_year, end_month) < (ref.year, ref.month)

    m2 = _RE_PERIOD_Y.search(head)
    if m2:
        if m2.group(2).lower() == "actualidad":
            return False
        end_year = int(m2.group(2))
        return end_year < ref.year
    return False


def _classify_financiamiento(entry: str) -> str:
    h = entry.lower()
    if re.search(r"director(?:a)? en el proyecto de extensi[oó]n", h):
        return "direccion_extension"
    if re.search(r"co-?director(?:a)? en el proyecto de i\+d", h):
        return "codireccion_proyecto"
    if re.search(r"director(?:a)? en el proyecto de i\+d", h):
        return "direccion_proyecto"
    if re.search(
        r"(?:alumn[oa]|estudiante)\s+becari[oa]\s+en el proyecto de i\+d|"
        r"estudiante en el proyecto de i\+d",
        h,
    ):
        return "estudiante_proyecto"
    if re.search(r"investigador(?:a)? en el proyecto de i\+d", h):
        return "investigador_proyecto"
    if re.search(r"personal t[eé]cnico en el proyecto de i\+d", h):
        return "tecnico_proyecto"
    if re.search(r"\bbeca de (?:iniciaci[oó]n|postgrado|doctorado|especializaci[oó]n|otro tipo)", h):
        return "beca_financiamiento"
    if re.search(r"\bestancia de i\+d\b", h):
        return "estancia_id"
    return "otro"


def parse_financiamiento(block: str) -> Dict[str, Any]:
    raw_entries = []
    for entry in split_dated_entries(block):
        tipo = _classify_financiamiento(entry)
        if tipo == "otro":
            continue
        finalizado = _entry_finalizado(entry)
        raw_entries.append(
            {
                "tipo": tipo,
                "finalizado": finalizado,
                "texto": _snippet(entry, 400),
                "resumen": entry.split("\n", 1)[0][:220],
            }
        )

    items, counts, evidence = _dedupe_entries(raw_entries, ("resumen",))
    inv_fin = sum(1 for it in items if it.get("tipo") == "investigador_proyecto" and it.get("finalizado"))
    if inv_fin:
        counts["investigador_proyecto_finalizado"] = inv_fin
        for it in items:
            if it.get("tipo") == "investigador_proyecto" and it.get("finalizado"):
                evidence["investigador_proyecto_finalizado"] = it.get("texto", "")
                break
    return {"entradas": items, "counts": counts, "evidence": evidence}


# ---------------------------------------------------------------------------
# Evaluación y gestión editorial
# ---------------------------------------------------------------------------

def _classify_evaluacion(entry: str) -> str:
    h = entry.lower()
    if re.search(r"coneu|acreditaci[oó]n de carreras|evaluaci[oó]n y/o acreditaci[oó]n", h):
        return "conau"
    if re.search(r"jurado de tesinas|jurado de tesis|jurado\b", h):
        return "jurado"
    if re.search(r"evaluaci[oó]n de programas y proyectos", h):
        return "evaluacion_programas"
    if re.search(r"proyectos institucionales|evaluaci[oó]n institucional", h):
        return "evaluacion_institucional"
    if re.search(r"integrante del comit[eé]|miembro del comit[eé]", h) and not re.search(r"organizada por", h):
        return "gestion_comite"
    if re.search(r"comisi[oó]n|consejo|cai|comit[eé]", h) and not re.search(r"organizada por", h):
        return "gestion_comite"
    if re.search(r"revisor|reviewer|evaluador de art[ií]culos", h) and "jurado" not in h:
        return "revisor_revista"
    if re.search(r"p[oó]ster|simposio|pasant[ií]a|plan de doctorado", h):
        return "evaluacion_academica_puntual"
    if re.search(r"evaluaci[oó]n de investigadores|evaluador/a", h):
        return "evaluacion_programas"
    return "otro"


def parse_evaluacion_gestion(block: str) -> Dict[str, Any]:
    raw_entries = []
    for entry in split_dated_entries(block):
        tipo = _classify_evaluacion(entry)
        if tipo == "otro":
            continue
        raw_entries.append({"tipo": tipo, "texto": _snippet(entry, 400), "resumen": entry.split("\n", 1)[0][:220]})

    items, counts, evidence = _dedupe_entries(raw_entries, ("resumen",))
    return {"entradas": items, "counts": counts, "evidence": evidence}


# ---------------------------------------------------------------------------
# Extensión
# ---------------------------------------------------------------------------

def parse_extension(block: str) -> Dict[str, Any]:
    items = []
    for entry in split_dated_entries(block):
        if not re.search(r'"[^"]{5,}"', entry):
            continue
        items.append({"tipo": "extension", "texto": _snippet(entry, 300), "titulo": re.search(r'"([^"]+)"', entry).group(1)[:200]})

    seen = set()
    unique = []
    for it in items:
        key = _norm_key(it["titulo"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    return {
        "entradas": unique,
        "counts": {"extension": len(unique)},
        "evidence": {"extension": unique[0]["texto"] if unique else ""},
    }


# ---------------------------------------------------------------------------
# Eventos CyT
# ---------------------------------------------------------------------------

def _classify_evento_roles(entry: str) -> List[str]:
    """Detecta roles en el título o cuerpo de una entrada de evento (puede haber varios)."""
    h = entry.lower()
    roles: List[str] = []

    modo_m = re.search(r"modo de participaci[oó]n\s*:\s*([^\n.\"]+)", entry, re.I)
    if modo_m:
        modo = modo_m.group(1).lower()
        if "asistente" in modo:
            roles.append("asistente")
        if re.search(r"presentador|p[oó]ster|expositora?|panelista|conferencista|ponente|disertante", modo):
            roles.append("expositora")
        if re.search(r"organizador", modo):
            roles.append("organizador")
        if roles:
            return roles

    if re.search(
        r"organizador(?:a)?|comit[eé]\s+organizador|miembro\s+del\s+comit[eé]",
        h,
    ):
        roles.append("organizador")
    if re.search(
        r"organizador(?:a)?\s+y\s+asistente|organizador(?:a)?\s*[-–]\s*asistente|organizadora?\s+y\s+asistente",
        h,
    ):
        roles.append("asistente")
    if re.search(r"expositora?|conferencista|ponente|disertante|panelista|presentador", h):
        roles.append("expositora")
    return roles


def _parse_premios_eventos(block: str) -> List[Dict[str, Any]]:
    m = re.search(r"(?is)\bPremios\b(.*)", block or "")
    if not m:
        return []
    tail = m.group(1).strip()
    if not tail:
        return []
    entries = re.split(r"(?im)(?=^\d{4}\s*[-–]\s+)", tail)
    entries = [e.strip() for e in entries if e.strip()]
    if not entries:
        entries = [tail]
    premios: List[Dict[str, Any]] = []
    for entry in entries:
        if re.search(
            r"puesto|premio|menci[oó]n|distinci[oó]n|galard[oó]n|ponencia|accesit|\d{1,2}[º°o]\.",
            entry,
            re.I,
        ):
            premios.append({"tipo": "premio", "texto": _snippet(entry, 300)})
    return premios


def parse_eventos_cyt(block: str) -> Dict[str, Any]:
    premios_block = block or ""
    event_block = re.split(r"(?is)\bPremios\b", premios_block)[0] if premios_block else ""

    items = []
    role_counts: Dict[str, int] = {"organizador": 0, "asistente": 0, "expositora": 0}
    role_evidence: Dict[str, str] = {}

    for entry in split_dated_entries(event_block):
        if not (re.search(r"evento\s*:", entry, re.I) or re.search(r"organizada por\s*:", entry, re.I)):
            continue
        titulo_m = re.search(r'"([^"]{5,300})"', entry)
        roles = _classify_evento_roles(entry)
        items.append(
            {
                "tipo": "evento",
                "roles": roles,
                "texto": _snippet(entry, 400),
                "titulo": titulo_m.group(1)[:200] if titulo_m else entry.split("\n", 1)[0][:200],
            }
        )

    seen = set()
    unique = []
    for it in items:
        key = _norm_key(it["titulo"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
        for rol in it.get("roles", []):
            role_counts[rol] = role_counts.get(rol, 0) + 1
            if rol not in role_evidence:
                role_evidence[rol] = it["texto"]

    premios = _parse_premios_eventos(premios_block)
    counts = {"eventos": len(unique), **role_counts}
    if premios:
        counts["premios"] = len(premios)
    evidence = {"eventos": unique[0]["texto"] if unique else "", **role_evidence}
    if premios:
        evidence["premios"] = premios[0]["texto"]

    return {
        "entradas": unique,
        "premios": premios,
        "counts": counts,
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Actividades profesionales
# ---------------------------------------------------------------------------

def _classify_actividad_rol(entry: str) -> str:
    h = entry.lower()
    if re.search(r"\b(?:disertante|expositora?|conferencista|ponente)\b", h):
        return "expositora"
    return "otro"


def parse_actividades_profesionales(block: str) -> Dict[str, Any]:
    items = []
    for entry in split_dated_entries(block):
        if re.search(r"\b(?:profesor(?:a)?|docente|c[aá]tedra|jtp|ayudante)\b", entry, re.I):
            continue
        if re.search(
            r"\b(?:asesor(?:a)?|consultor(?:a)?|auditor(?:a)?|capacitador(?:a)?|perit(?:o|aje)?|"
            r"responsable del equipo|disertante|tutor[ií]a|coordinaci[oó]n editorial)\b",
            entry,
            re.I,
        ):
            rol = _classify_actividad_rol(entry)
            items.append(
                {
                    "tipo": "actividad_profesional",
                    "rol": rol,
                    "texto": _snippet(entry, 400),
                    "resumen": entry.split("\n", 1)[0][:220],
                }
            )

    seen = set()
    unique = []
    expositora = 0
    expositora_evidence = ""
    for it in items:
        key = _norm_key(it["resumen"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
        if it.get("rol") == "expositora":
            expositora += 1
            if not expositora_evidence:
                expositora_evidence = it["texto"]

    counts: Dict[str, int] = {"actividades_profesionales": len(unique)}
    evidence: Dict[str, str] = {"actividades_profesionales": unique[0]["texto"] if unique else ""}
    if expositora:
        counts["expositora"] = expositora
        evidence["expositora"] = expositora_evidence

    return {
        "entradas": unique,
        "counts": counts,
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Otros antecedentes CyT
# ---------------------------------------------------------------------------

def _classify_otros(entry: str, subsection: str = "") -> str:
    h = (subsection + " " + entry).lower()
    if re.search(r"programa de incentivos|categor[ií]a\s+(?:i{1,3}|iv|v|vi)\b", h):
        return "incentivos"
    if re.search(r"red(?:es)?\s+tem[aá]tica|red(?:es)?\s+institucional|participaci[oó]n en redes", h):
        return "redes"
    if re.search(r"desarrollo(?:s)? tecnol|observatorio|coordinaci[oó]n de proyectos", h):
        return "desarrollos"
    if re.search(r"membres[ií]a|sociedad|asociaci[oó]n|colegio|instituto", h) and re.search(r"actualidad|\d{4}", h):
        return "redes"
    return "otro"


def parse_otros_antecedentes(block: str) -> Dict[str, Any]:
    if not block:
        return {"entradas": [], "counts": {}, "evidence": {}, "subsections": []}

    lines = _clean_lines(block)
    current_sub = ""
    chunks: List[Tuple[str, str]] = []
    buf: List[str] = []

    def flush():
        nonlocal buf
        if buf:
            chunks.append((current_sub, "\n".join(buf).strip()))
            buf = []

    for line in lines:
        if _RE_SUBSECTION.search(line):
            flush()
            current_sub = line
            continue
        if _RE_DATE_LINE.match(line) and buf:
            flush()
        buf.append(line)
    flush()

    raw_entries = []
    for subsection, chunk in chunks:
        for entry in split_dated_entries(chunk) if _RE_DATE_LINE.search(chunk) else [chunk]:
            tipo = _classify_otros(entry, subsection)
            if tipo == "otro":
                continue
            raw_entries.append(
                {
                    "tipo": tipo,
                    "subsection": subsection[:120],
                    "texto": _snippet(entry, 400),
                    "resumen": (entry.split("\n", 1)[0] if entry else subsection)[:220],
                }
            )

    items, counts, evidence = _dedupe_entries(raw_entries, ("resumen", "subsection"))
    return {"entradas": items, "counts": counts, "evidence": evidence}


# ---------------------------------------------------------------------------
# Publicaciones (ampliado)
# ---------------------------------------------------------------------------

def _parse_combo_libros_capitulos(
    combo_block: str, scorer_mod: Any = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parsea libros, capítulos y trabajos en eventos desde el bloque combinado CONICET."""
    libros: List[Dict[str, Any]] = []
    capitulos: List[Dict[str, Any]] = []
    trabajos: List[Dict[str, Any]] = []
    if not combo_block or not combo_block.strip():
        return libros, capitulos, trabajos

    is_trabajo = getattr(scorer_mod, "_is_trabajo_evento_publicado", None)

    seen_lib: set = set()
    for chunk in re.split(r"(?i)(?=\bISBN\s*:)", combo_block):
        snippet = re.sub(r"\s+", " ", chunk).strip()
        if not re.search(r"(?i)\bISBN\s*:", snippet):
            continue
        if re.search(r'(?i)"[^"]+"\s*\.\s*En[\s:]', snippet) and not re.search(r"(?i)\d+\s*p\.\s*ISBN", snippet):
            continue
        if is_trabajo and is_trabajo(snippet):
            continue
        key = _norm_key(snippet[:180])
        if key in seen_lib:
            continue
        seen_lib.add(key)
        libros.append({"titulo": snippet[:300]})

    seen_cap: set = set()
    seen_trab: set = set()
    for chunk in re.split(r'(?m)(?=\s*(?:[A-ZÁÉÍÓÚÜÑ][^.]{2,40}\.\s*"|^\.\s*"))', combo_block):
        snippet = re.sub(r"\s+", " ", chunk).strip()
        if not re.search(r"(?i)\bEn:\s*", snippet):
            continue
        if is_trabajo and is_trabajo(snippet):
            key = _norm_key(snippet[:180])
            if key not in seen_trab:
                seen_trab.add(key)
                trabajos.append({"titulo": snippet[:300]})
            continue
        if not re.search(r"(?i)\(ed\.?\)|\bed\.\)", snippet):
            continue
        key = _norm_key(snippet[:180])
        if key in seen_cap:
            continue
        seen_cap.add(key)
        capitulos.append({"titulo": snippet[:300]})

    return libros, capitulos, trabajos


def _extract_combo_libros_capitulos_block(block: str) -> str:
    """Bloque combinado 'Libros, capítulos y trabajos en eventos' (común en CVs CONICET)."""
    if not block:
        return ""
    m = re.search(r"(?i)Libros,\s*cap[ií]tulos y trabajos en eventos", block)
    if not m:
        return ""
    tail = block[m.end() :]
    end_m = re.search(r"(?i)\bTesis de (?:doctorado|grado)\b", tail)
    return tail[: end_m.start() if end_m else len(tail)].strip()


def parse_publicaciones_extended(block: str, scorer_mod: Any) -> Dict[str, Any]:
    art_block = scorer_mod._extract_publicaciones_subsection(block, "Art[ií]culos") or block
    combo_block = _extract_combo_libros_capitulos_block(block)
    cap_block = scorer_mod._extract_publicaciones_subsection(block, "Cap[ií]tulos") or combo_block or ""
    lib_block = scorer_mod._extract_publicaciones_subsection(block, "Libros") or combo_block or ""

    art_rows = scorer_mod._merge_publicacion_lines(art_block)
    art_count, _ = scorer_mod._dedupe_publication_rows(art_rows)
    valid_art = [r for r in art_rows if scorer_mod._is_valid_articulo_row(re.sub(r"\s+", " ", r).strip())]

    capitulos: List[Dict[str, Any]] = []
    libros: List[Dict[str, Any]] = []
    trabajos: List[Dict[str, Any]] = []
    seen_trab: set = set()

    def _add_trabajo(sn: str) -> None:
        if not scorer_mod._is_trabajo_evento_publicado(sn):
            return
        key = _norm_key(sn[:180])
        if key in seen_trab:
            return
        seen_trab.add(key)
        trabajos.append({"titulo": sn[:300]})

    if combo_block:
        libros, capitulos, trabajos_combo = _parse_combo_libros_capitulos(combo_block, scorer_mod)
        for t in trabajos_combo:
            _add_trabajo(t.get("titulo", ""))
    else:
        for row in scorer_mod._merge_publicacion_lines(cap_block or block):
            sn = re.sub(r"\s+", " ", row).strip()
            if scorer_mod._is_trabajo_evento_publicado(sn):
                _add_trabajo(sn)
                continue
            if re.search(
                r'(?i)"[^"]+"\s*\.\s*En\s+[A-ZÁÉÍÓÚÜÑ]|'
                r'\bEn:\s*[^"]*\(ed\.?\)|\bEn:\s*[^(]+\(ed\.?\)|\bCap[ií]tulo\b',
                sn,
            ):
                capitulos.append({"titulo": sn[:300]})
        for row in scorer_mod._merge_publicacion_lines(lib_block or block):
            sn = re.sub(r"\s+", " ", row).strip()
            if (
                re.search(r"(?i)\bISBN\s*:\s*[\dXx\-]", sn)
                and not re.search(r"(?i)sin\s+dato\s+de\s+issn/isbn", sn)
                and not re.search(r'(?i)"[^"]+"\s*\.\s*En\s+', sn)
            ):
                libros.append({"titulo": sn[:300]})

    for row in scorer_mod._merge_publicacion_lines(block):
        sn = re.sub(r"\s+", " ", row).strip()
        _add_trabajo(sn)

    doi_count = len(re.findall(r"(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)(10\.\S+)", block, re.I))

    return {
        "articulos": [{"titulo": r[:300]} for r in valid_art],
        "capitulos": capitulos,
        "libros": libros,
        "trabajos_evento": trabajos,
        "counts": {
            "articulos_revista": art_count,
            "capitulos_libro": len(capitulos),
            "libros_isbn": len(libros),
            "trabajos_evento_publicados": len(trabajos),
            "articulos_doi": doi_count,
        },
        "raw_chars": len(block),
    }


def aggregate_section_counts(parsed_items: Dict[str, Any]) -> Dict[str, Any]:
    """Aplana conteos de todas las pestañas parseadas."""
    out: Dict[str, Any] = {}

    rrhh = parsed_items.get("formacion_rrhh", {}).get("counts", {})
    out["rrhh"] = rrhh

    fin = parsed_items.get("financiamiento_cyt", {}).get("counts", {})
    out["financiamiento"] = fin

    ev = parsed_items.get("evaluacion_gestion", {}).get("counts", {})
    out["evaluacion"] = ev

    ext = parsed_items.get("extension", {}).get("counts", {})
    out["extension"] = ext.get("extension", 0)

    evn = parsed_items.get("eventos_cyt", {}).get("counts", {})
    out["eventos"] = evn.get("eventos", 0)
    out["eventos_organizador"] = evn.get("organizador", 0)
    out["eventos_asistente"] = evn.get("asistente", 0)
    out["eventos_expositora"] = evn.get("expositora", 0)
    out["eventos_premios"] = evn.get("premios", 0)

    ap = parsed_items.get("actividades_profesionales", {}).get("counts", {})
    out["actividades_profesionales"] = ap.get("actividades_profesionales", 0)
    out["actividades_expositora"] = ap.get("expositora", 0)

    otros = parsed_items.get("otros_antecedentes", {}).get("counts", {})
    out["otros"] = otros

    pub = parsed_items.get("publicaciones", {}).get("counts", {})
    out["articulos_revista"] = pub.get("articulos_revista", 0)
    out["capitulos_libro"] = pub.get("capitulos_libro", 0)
    out["libros_isbn"] = pub.get("libros_isbn", 0)
    out["trabajos_evento_publicados"] = pub.get("trabajos_evento_publicados", 0)
    out["articulos_doi"] = pub.get("articulos_doi", 0)

    return out
