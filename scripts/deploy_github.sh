#!/usr/bin/env bash
# Crea el repo en GitHub (si no existe) y pushea main.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "GitHub CLI sin sesión. Ejecutá: gh auth login -h github.com"
  exit 1
fi

REPO="claudiomlarrea/Categorizador-Investigadores-UCCuyo"

if ! gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Creando repositorio $REPO ..."
  gh repo create "$REPO" --public \
    --description "Categorizador de investigadores UCCuyo desde CVar CONICET (Anexo VII)" \
    --source=. --remote=origin --push
else
  echo "Repositorio existente. Pusheando main ..."
  git push -u origin main
fi

echo ""
echo "Listo. Repo: https://github.com/$REPO"
echo "Streamlit Cloud: https://share.streamlit.io → New app → $REPO → main → app.py"
