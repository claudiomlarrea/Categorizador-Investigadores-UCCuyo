"""Tests unitarios para fixes de auditoría CV."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from section_parsers import _classify_evaluacion, _parse_premios_eventos  # noqa: E402
from scorer import (  # noqa: E402
    _classify_structural,
    _extract_evento_titles_set,
    _merge_publicacion_lines,
    _split_traduccion_publicaciones,
    _trabajo_duplicates_evento,
)


def test_evaluacion_trabajos_en_revistas():
    entry = '2020 - Evaluación de trabajos en revistas\nRevista X, artículo "Título"'
    assert _classify_evaluacion(entry) == "revisor_revista"


def test_premios_diploma_honor():
    block = 'Premios\n2020 - Diploma de Honor por trayectoria docente.'
    premios = _parse_premios_eventos(block)
    assert len(premios) == 1


def test_posgraduado_es_especializacion():
    assert _classify_structural("POS GRADUADO EN ENFERMERÍA\nUniversidad Nacional de Cuyo") == "especializacion"


def test_split_traducciones_tras_tesis():
    merged = (
        'Tesis de grado "Algo" 1985. López, R.; García, M. "Traducción uno". 2016. '
        'Traducción publicada en revista. Revista A; López, R.; Pérez, J. "Traducción dos". '
        '2018. Traducción publicada en revista. Revista B'
    )
    parts = _split_traduccion_publicaciones([merged])
    traducciones = [p for p in parts if "Traducción publicada en revista" in p]
    assert len(traducciones) >= 2


def test_merge_publicacion_flush_traduccion():
    merged = (
        'Tesis de grado "Mi tesis" 1990. Autor, A.; Autor, B. "Libro traducido". 2015. '
        'Traducción publicada en revista. Revista X'
    )
    parts = _split_traduccion_publicaciones([merged])
    assert any("Traducción publicada en revista" in p for p in parts)


def test_trabajo_duplica_evento():
    eventos = '2020 - Evento: "Jornadas de Química Orgánica"\nOrganizada por: Facultad'
    titles = _extract_evento_titles_set(eventos)
    poster = (
        '3/2020 - Póster "Síntesis". Presentado en el evento "Jornadas de Química Orgánica"'
    )
    assert _trabajo_duplicates_evento(poster, titles)
