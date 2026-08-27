#!/bin/bash
cd "$(dirname "$0")"

# Fermer le terminal automatiquement quand ce script se termine
cleanup() {
    nohup osascript -e 'tell application "Terminal" to close front window' >/dev/null 2>&1 &
    disown $!
}
trap cleanup EXIT

# Créer le venv et installer les dépendances si première utilisation
if [ ! -d "venv" ]; then
    echo "Première utilisation — installation (~5-10 min)..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt --quiet
    playwright install webkit
    echo "Installation terminée."
else
    source venv/bin/activate
fi

# Arrêter une instance précédente si elle tourne encore
lsof -ti :5000 | xargs kill 2>/dev/null; sleep 0.5

# Ouvrir le navigateur après 2s
(sleep 2 && open http://localhost:5000) &

echo ""
echo "LinkedIn Bot démarré → http://localhost:5000"
echo "Utilise le bouton 'Arrêter' dans l'interface pour stopper proprement."
echo ""

python app.py
# Flask a quitté → le trap EXIT ferme le terminal
