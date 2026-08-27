# LinkedIn Bot — Cahelis

Bot de prospection LinkedIn qui détecte les nouveaux abonnés de la page **Cahelis** et leur envoie un message personnalisé. Gère plusieurs cycles de relance avec une interface web locale.

---

## Sommaire

1. [Prérequis](#1-prérequis)
2. [Installation](#2-installation)
3. [Premier lancement](#3-premier-lancement)
4. [Interface web](#4-interface-web)
5. [Workflow recommandé](#5-workflow-recommandé)
6. [Configuration](#6-configuration)
7. [Transférer sur un autre Mac](#7-transférer-sur-un-autre-mac)
8. [Structure des fichiers](#8-structure-des-fichiers)
9. [Base de données contacts.json](#9-base-de-données-contactsjson)
10. [Modes du bot (avancé)](#10-modes-du-bot-avancé)
11. [Dépannage](#11-dépannage)

---

## 1. Prérequis

| Élément | Requis | Note |
|---|---|---|
| macOS | ✅ | Monterey 12+ recommandé |
| Python 3.10+ | ✅ | Déjà installé sur macOS récent |
| Connexion internet | ✅ | Pour le premier téléchargement |
| Compte LinkedIn | ✅ | Accès admin page Cahelis |

Vérifier que Python est installé :
```bash
python3 --version
```
Si la commande n'existe pas : télécharger sur [python.org](https://www.python.org/downloads/).

---

## 2. Installation

Le dossier contient tout le nécessaire. **Aucune installation manuelle requise** — tout est automatisé au premier lancement.

```
linkedin_bot/
├── launch.command       ← lanceur macOS (double-clic)
├── linkedin_bot.py      ← moteur du bot
├── app.py               ← serveur web
├── templates/
│   └── index.html       ← interface
├── requirements.txt     ← dépendances Python
├── config.json          ← identifiants & messages
└── contacts.json        ← base de données abonnés
```

---

## 3. Premier lancement

1. **Double-cliquer sur `launch.command`**
   - Si macOS affiche *"impossible d'ouvrir"* → **clic droit → Ouvrir → Ouvrir** (une seule fois)
2. Un terminal s'ouvre et installe automatiquement :
   - L'environnement Python isolé (`venv/`)
   - Les bibliothèques Flask et Playwright
   - Le navigateur WebKit (~150 Mo)
   - **Durée : 5 à 10 minutes**
3. Le navigateur s'ouvre sur `http://localhost:5000`
4. Le terminal reste ouvert pendant toute la session

### Connexion LinkedIn initiale

Au premier lancement ou si la session a expiré, le bot ouvre LinkedIn dans un navigateur visible :

1. Se connecter manuellement avec le compte Cahelis
2. Valider la vérification téléphonique si demandée
3. Attendre d'être sur le fil d'actualité LinkedIn
4. Appuyer sur **ENTRÉE** dans le terminal

La session est sauvegardée dans `browser_profile/` — les lancements suivants sont automatiques.

---

## 4. Interface web

L'interface est accessible sur **http://localhost:5000**.

### Navigation (sidebar gauche)

| Section | Description |
|---|---|
| 📊 **Dashboard** | Vue d'ensemble, génération de la liste, logs |
| 👋 **Nouveaux abonnés** | Abonnés jamais contactés |
| 🔔 **1ère relance** | Ont reçu 1 message, en attente de suivi |
| 🔔 **2ème relance** | Ont reçu 2 messages |
| ♻️ **2+ relances** | Ont reçu 3 messages ou plus |
| ✅ **Ont répondu** | Marqués manuellement comme ayant répondu |
| ⚙️ **Paramètres** | Email et mot de passe LinkedIn |

### Dashboard

- **Cartes de statistiques** — nombre d'abonnés par catégorie, cliquables pour y accéder
- **Générer la liste d'abonnés** — scrape LinkedIn et met à jour la base de données
- **Marquer comme "À répondu"** — modal de gestion des réponses
- **Logs en direct** — sortie temps réel du bot en cours d'exécution

### Vue catégorie

- **Éditeur de message** — personnaliser le message avec `{prenom}` et `{nom}`
- **⚡ Simuler** — parcourt les profils sans envoyer (test)
- **✉ Envoyer à tous** — envoie à toute la catégorie
- **Liste des abonnés** — recherche par nom, lien profil, bouton "A répondu" individuel

### Modal "À répondu"

- Colonne gauche : tous les abonnés actifs avec recherche
- Colonne droite : abonnés ayant répondu
- Cliquer un nom → le déplace d'une colonne à l'autre instantanément

---

## 5. Workflow recommandé

### Routine hebdomadaire

```
1. Double-clic → launch.command
2. Dashboard → [Générer la liste d'abonnés]   (~3-5 min)
3. Vérifier les nouveaux abonnés
4. Nouveaux abonnés → vérifier le message → [Envoyer à tous]
5. Arrêter le serveur quand c'est terminé
```

### Cycle de relance

Les abonnés progressent automatiquement à chaque envoi réussi :

```
Nouvel abonné détecté
       ↓  [Envoyer — Nouveaux abonnés]
1ère relance          (1 message reçu)
       ↓  [Envoyer — 1ère relance]
2ème relance          (2 messages reçus)
       ↓  [Envoyer — 2ème relance]
2+ relances           (3+ messages reçus)
       ↓  [Bouton "A répondu"]
Ont répondu  ← sortis du pipeline définitivement
```

### Bonnes pratiques

- Configurer un message différent pour chaque catégorie (ton progressivement plus personnel)
- Toujours **Simuler** avant un premier envoi dans une nouvelle catégorie
- Espacer les relances d'au moins 1 semaine
- Ne pas envoyer plus de 30 à 50 messages par session pour éviter les restrictions LinkedIn
- Vérifier les logs après chaque envoi

---

## 6. Configuration

Le fichier `config.json` contient tous les paramètres. Il se modifie via la section **Paramètres** (email/mot de passe) ou directement dans chaque catégorie (messages).

```json
{
  "linkedin_email": "alisson.calovini@gmail.com",
  "linkedin_password": "••••••••",
  "page_url": "https://www.linkedin.com/company/113208199/",
  "followers_url": "https://www.linkedin.com/company/113208199/admin/analytics/followers/",
  "headless": true,
  "message_new": "Bonjour {prenom}, merci de suivre la page Cahelis !...",
  "message_relance_1": "Rebonjour {prenom}, ...",
  "message_relance_2": "...",
  "message_relance_2plus": "..."
}
```

| Clé | Description |
|---|---|
| `linkedin_email` | Email du compte LinkedIn admin Cahelis |
| `linkedin_password` | Mot de passe LinkedIn |
| `page_url` | URL de la page entreprise |
| `followers_url` | URL de la liste des abonnés (admin) |
| `headless` | `true` = navigateur invisible, `false` = visible (debug) |
| `message_new` | Message pour les nouveaux abonnés |
| `message_relance_1` | Message de 1ère relance |
| `message_relance_2` | Message de 2ème relance |
| `message_relance_2plus` | Message pour 3+ relances |

---

## 7. Transférer sur un autre Mac

### Fichiers à copier

```
✅  linkedin_bot.py
✅  app.py
✅  templates/
✅  requirements.txt
✅  launch.command
✅  config.json          ← identifiants Cahelis inclus
✅  contacts.json        ← base de données abonnés (important !)
```

### Fichiers à ne PAS copier

```
❌  venv/               ← binaires spécifiques au Mac source
❌  browser_profile/    ← session LinkedIn du Mac source
❌  bot.log  server.log  run_output.txt  perf.json
❌  all_followers.json  seen_followers.json
```

### Procédure sur le nouveau Mac

1. Copier le dossier (clé USB, AirDrop, etc.)
2. Vérifier Python 3 : `python3 --version`
3. **Clic droit → Ouvrir** sur `launch.command` (première fois uniquement, contournement Gatekeeper)
4. Attendre l'installation automatique (~5-10 min)
5. Se connecter manuellement à LinkedIn au premier lancement du bot
6. La session est sauvegardée → les prochains lancements sont automatiques

> **Important** : copier `contacts.json` pour conserver l'historique complet des abonnés et relances. Sans ce fichier, la base repart de zéro.

---

## 8. Structure des fichiers

```
linkedin_bot/
│
├── launch.command          Script de lancement macOS
├── linkedin_bot.py         Moteur du bot (Playwright WebKit)
├── app.py                  Serveur web (Flask)
├── templates/
│   └── index.html          Interface web (SPA vanilla JS)
│
├── requirements.txt        playwright==1.60.0, Flask==3.1.3
├── config.json             ⚠️ Identifiants & messages (ne pas partager)
│
├── contacts.json           Base de données abonnés          [auto]
├── perf.json               Performances du dernier run       [auto]
├── bot.log                 Logs complets                     [auto]
├── run_output.txt          Sortie du dernier run             [auto]
├── server.log              Logs du serveur Flask             [auto]
│
├── browser_profile/        Session LinkedIn persistante      [auto]
└── venv/                   Environnement Python isolé        [auto]
```

---

## 9. Base de données contacts.json

Chaque abonné est un objet JSON :

```json
{
  "url": "https://www.linkedin.com/in/jean-dupont",
  "name": "Jean Dupont",
  "messages_sent": 1,
  "last_contacted": "2026-07-06 08:12",
  "responded": false,
  "added_at": "2026-07-01 10:30"
}
```

| Champ | Description |
|---|---|
| `url` | URL du profil LinkedIn (identifiant unique) |
| `name` | Nom complet |
| `messages_sent` | Nombre de messages envoyés (détermine la catégorie) |
| `last_contacted` | Date du dernier message |
| `responded` | `true` si marqué manuellement comme ayant répondu |
| `added_at` | Date d'ajout à la base |

### Règle de catégorisation

| `messages_sent` | `responded` | Catégorie affichée |
|---|---|---|
| 0 | `false` | 👋 Nouveaux abonnés |
| 1 | `false` | 🔔 1ère relance |
| 2 | `false` | 🔔 2ème relance |
| 3+ | `false` | ♻️ 2+ relances |
| — | `true` | ✅ Ont répondu |

---

## 10. Modes du bot (avancé)

Le bot peut être utilisé en ligne de commande depuis le terminal :

```bash
# Activer l'environnement
source venv/bin/activate

# Scraper et mettre à jour contacts.json
python linkedin_bot.py --refresh

# Envoyer à une catégorie
python linkedin_bot.py --send new
python linkedin_bot.py --send relance_1
python linkedin_bot.py --send relance_2
python linkedin_bot.py --send relance_2plus

# Simuler sans envoyer
python linkedin_bot.py --simulate new
python linkedin_bot.py --simulate relance_1

# Test sur un profil précis
python linkedin_bot.py --test-message https://www.linkedin.com/in/exemple
```

---

## 11. Dépannage

### Le terminal affiche "port already in use"
Un ancien serveur tourne encore :
```bash
lsof -ti :5000 | xargs kill
```
Puis relancer `launch.command`. Le script fait cette vérification automatiquement depuis la V2.

### LinkedIn demande une vérification téléphonique
Normal lors de la première connexion ou après une longue absence. Valider sur le téléphone, puis ENTRÉE dans le terminal.

### "Lien Message introuvable pour X"
LinkedIn a peut-être mis à jour son interface. Passer `"headless": false` dans `config.json` pour voir ce qui se passe visuellement.

### Le bot s'arrête au milieu d'un envoi
Les abonnés déjà contactés avec succès sont sauvegardés immédiatement dans `contacts.json`. Relancer reprend là où ça s'est arrêté (les envoyés sont déjà en catégorie suivante).

### Les abonnés ne se chargent pas (reste à 0)
- Vérifier que `followers_url` dans `config.json` est correct
- Vérifier les droits admin sur la page Cahelis
- Passer en `"headless": false` pour observer le navigateur

### La session expire (reconnexion demandée)
Supprimer le dossier `browser_profile/` et relancer. Le bot demandera une connexion manuelle.

---

## Sécurité

- `config.json` contient des identifiants réels — **ne jamais le partager ni le publier**
- Le fichier est exclu du dépôt git (`.gitignore`)
- Le serveur web écoute uniquement sur `127.0.0.1` — inaccessible depuis le réseau local
- Aucune donnée n'est transmise vers un serveur externe

---

*LinkedIn Bot V2 — Cahelis · Playwright + Flask*
