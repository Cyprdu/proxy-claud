#!/usr/bin/env bash
# Script de build pour Render

set -o errexit

echo "📦 Installation des dépendances Python..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🌐 Installation de Chromium pour Playwright..."
# Définit le chemin où Playwright doit installer les navigateurs
export PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright

# Installe d'abord les dépendances système
python -m playwright install-deps chromium

# Puis installe Chromium
python -m playwright install chromium

# Vérifie que Chromium est bien installé
if [ -f "$HOME/.cache/ms-playwright/chromium-*/chrome-linux/chrome" ]; then
    echo "✅ Chromium installé avec succès !"
else
    echo "⚠️ Attention: Chromium pourrait ne pas être installé correctement"
fi

echo "✅ Build terminé !"
