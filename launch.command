#!/bin/bash
cd "$(dirname "$0")"

# Créer le venv et installer les dépendances si première utilisation
if [ ! -d "venv" ]; then
    echo "⚙️  Première utilisation — installation des dépendances..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt --quiet
    playwright install webkit
    echo "✅ Installation terminée."
else
    source venv/bin/activate
fi

# Ouvrir le navigateur après 2s
(sleep 2 && open http://localhost:5000) &

echo ""
echo "🚀 LinkedIn Bot démarré → http://localhost:5000"
echo "   Utilise le bouton 'Arrêter' dans l'interface pour stopper proprement."
echo ""

python app.py
