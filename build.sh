#!/usr/bin/env bash
# Script de build pour Render

set -o errexit

echo "📦 Installation des dépendances Python..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🌐 Configuration de Playwright..."
# Utilise /opt/render/project/src au lieu de $HOME
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/src/.cache/ms-playwright

echo "📂 Chemin d'installation: $PLAYWRIGHT_BROWSERS_PATH"

echo "📚 Installation des dépendances système..."
python -m playwright install-deps chromium

echo "⬇️ Téléchargement de Chromium..."
python -m playwright install chromium

echo "🔍 Vérification de l'installation..."
if ls $PLAYWRIGHT_BROWSERS_PATH/chromium-*/chrome-linux/chrome 1> /dev/null 2>&1; then
    echo "✅ Chromium installé avec succès !"
    ls -la $PLAYWRIGHT_BROWSERS_PATH/
else
    echo "⚠️ Chromium non trouvé, listage du contenu:"
    ls -la $PLAYWRIGHT_BROWSERS_PATH/ || echo "Dossier n'existe pas"
fi

echo "✅ Build terminé !"
