# LinkedIn Auto-Message Bot

Détecte automatiquement les nouveaux abonnés de ta Page LinkedIn et leur envoie un message personnalisé.

## Prérequis

- Python 3.10+
- Google Chrome installé

## Installation

```bash
# 1. Installer les dépendances
pip install playwright

# 2. Installer le navigateur Chromium
playwright install chromium

# 3. Copier et remplir la config
cp config.example.json config.json
# → Édite config.json avec tes identifiants
```

## Configuration (config.json)

| Clé | Description |
|-----|-------------|
| `linkedin_email` | Ton email de connexion LinkedIn (compte admin de la Page) |
| `linkedin_password` | Ton mot de passe LinkedIn |
| `page_url` | URL de ta Page LinkedIn (ex: `https://www.linkedin.com/company/ma-page/`) |
| `message_template` | Message envoyé. Utilise `{prenom}` et `{nom}` pour personnaliser |
| `headless` | `false` = tu vois le navigateur (recommandé au début), `true` = invisible |

## Lancement manuel

```bash
python3 linkedin_bot.py
```

## Lancement automatique (cron)

```bash
# Rendre le script exécutable
chmod +x run_bot.sh

# Ouvrir le cron
crontab -e

# Ajouter cette ligne (exécution toutes les 6h) :
0 */6 * * * /chemin/complet/vers/run_bot.sh
```

## Fichiers générés

- `seen_followers.json` — liste des abonnés déjà traités
- `bot.log` — journal d'activité

## ⚠️ Avertissements

- Ce script automatise des actions sur LinkedIn, ce qui est contre leurs CGU.
- Lance d'abord avec `headless: false` pour vérifier que tout fonctionne.
- En cas de CAPTCHA ou 2FA, le script te demandera de résoudre manuellement.
- Ne pas envoyer plus de 20-30 messages/jour pour éviter les restrictions.
