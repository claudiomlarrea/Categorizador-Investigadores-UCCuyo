# Categorizador de Investigadores — UCCuyo

Sistema local para categorizar docentes-investigadores a partir del **CVar** (CONICET), según el **Anexo VII — Valorador de Currículum Docente**.

## Flujo

1. **Entrada:** PDF del CVar descargado de CONICET, o TXT ya normalizado (`__CVAR_CLEAN.txt`).
2. **Normalización:** extracción de texto, limpieza y estructuración por secciones/pestañas del CVar.
3. **Valoración:** puntaje por ítem y por sección usando `config/criteria.json`.
4. **Salida:** categoría de investigador en pantalla + informes **Excel** y **Word**.

## Categorías (Anexo VII)

| Categoría | Puntaje |
|---|---|
| I — Investigador Superior | ≥ 1800 |
| II — Investigador Principal | 1200 – 1799 |
| III — Investigador Independiente | 700 – 1199 |
| IV — Investigador Adjunto | 350 – 699 |
| V — Investigador Asistente | 1 – 349 |
| VI — Becario de Iniciación | 0 |

## Estructura del proyecto

```
Categorizador-Investigadores-UCCuyo/
├── app.py                 # Aplicación Streamlit unificada
├── config/criteria.json   # Reglas de puntaje
├── src/
│   ├── normalizer.py      # PDF → texto estructurado
│   ├── scorer.py          # Motor de puntuación
│   └── report.py          # Exportación Excel / Word
├── data/
│   ├── cvar_ejemplos/     # CVars de prueba
│   └── valoraciones_referencia/
├── docs/                  # Normativa (Anexo VII)
├── outputs/               # Informes generados (opcional)
└── scripts/run_local.sh   # Arranque local
```

## Uso local

```bash
cd ~/Documents/Categorizador-Investigadores-UCCuyo
chmod +x scripts/run_local.sh
./scripts/run_local.sh
```

O manualmente:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Abrí `http://localhost:8501`, cargá un PDF o TXT y descargá los informes.

## Archivos de referencia incluidos

- `docs/Anexo_VII_Valorador_Curriculum_Docente.docx`
- `data/cvar_ejemplos/` — CVars de Virna Vinader, Diego Kasshua, Young, Larrea, Codorniu
- `data/valoraciones_referencia/` — grillas manuales de comparación

## Próximo paso: GitHub + Streamlit Cloud

1. Inicializar repositorio y subir a GitHub.
2. Desplegar `app.py` en [Streamlit Cloud](https://streamlit.io/cloud).
3. Compartir el enlace con el equipo de investigación.

## Proyectos base

Este sistema integra código de:

- `~/Documents/Normalizador-de-CVar`
- `~/Documents/Valorador-CVar-CLEAN`
