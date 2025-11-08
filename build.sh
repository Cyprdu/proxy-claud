#!/usr/bin/env bash
# Script de build pour Render

set -o errexit

# Installe les dépendances Python
pip install -r requirements.txt

# Installe les navigateurs Playwright
playwright install chromium
playwright install-deps chromium
