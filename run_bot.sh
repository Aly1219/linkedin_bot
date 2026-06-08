#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Launcher pour le bot LinkedIn — à appeler via cron
#
# Exemple crontab (toutes les 6h) :
#   0 */6 * * * /chemin/vers/run_bot.sh
#
# Pour éditer le cron : crontab -e
# ─────────────────────────────────────────────────────────────

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "[$(date)] Lancement du bot..." >> bot.log
python3 linkedin_bot.py
echo "[$(date)] Bot terminé." >> bot.log
