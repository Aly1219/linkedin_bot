#!/bin/bash
cd "$(dirname "$0")"

# Fermer le terminal automatiquement quand ce script se termine
cleanup() {
    nohup osascript -e 'tell application "Terminal" to close front window' >/dev/null 2>&1 &
    disown $!
}
trap cleanup EXIT

# En cas d'échec critique : afficher l'erreur et attendre avant de fermer
# (sinon le trap ci-dessus referme la fenêtre avant que le message soit lisible)
fail() {
    echo ""
    echo "❌ $1"
    echo "Appuie sur une touche pour fermer cette fenêtre..."
    read -n 1 -s -r
    exit 1
}

# Créer le venv et installer les dépendances si première utilisation
if [ ! -d "venv" ]; then
    echo "Première utilisation — installation (~5-10 min)..."
    python3 -m venv venv || fail "Impossible de créer l'environnement Python (venv). Python 3 est-il installé ?"
    source venv/bin/activate
    pip install -r requirements.txt --quiet || fail "Échec de l'installation des dépendances (pip install)."
    playwright install webkit || fail "Échec de l'installation du navigateur Playwright (webkit)."
    echo "Installation terminée."
else
    source venv/bin/activate
fi

# Arrêter une instance précédente si elle tourne encore
lsof -ti :5000 | xargs kill 2>/dev/null; sleep 0.5

# Ouvrir le navigateur dès que le serveur répond réellement (jusqu'à 30s),
# au lieu d'un délai fixe qui peut ouvrir une page blanche si Flask n'a pas
# encore démarré. On force 127.0.0.1 (pas "localhost") et on ignore tout
# proxy système, sinon la vérification peut échouer en boucle sur un Mac
# où un proxy réseau est configuré (le navigateur, lui, l'ignore pour
# localhost — d'où un écart entre "curl échoue" et "ça marche à la main").
(
  for i in $(seq 1 60); do
    if curl -sf --noproxy '*' http://127.0.0.1:5000/ >/dev/null 2>&1; then
      open http://127.0.0.1:5000
      break
    fi
    sleep 0.5
  done
) &

echo ""
echo "LinkedIn Bot démarré → http://localhost:5000"
echo "Utilise le bouton 'Arrêter' dans l'interface pour stopper proprement."
echo ""

python app.py || fail "Le serveur s'est arrêté avec une erreur. Regarde le message ci-dessus."
# Flask a quitté normalement → le trap EXIT ferme le terminal
