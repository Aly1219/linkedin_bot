"""
LinkedIn Auto-Message Bot
Détecte les nouveaux abonnés d'une Page LinkedIn et envoie un message automatique.

Usage:
    python linkedin_bot.py             # mode normal (envoi de messages)
    python linkedin_bot.py --dry-run   # mode test : scrape les abonnés et les sauvegarde dans un fichier JSON sans envoyer de messages

Config:
    Remplir le fichier config.json avant de lancer.
"""

import json
import time
import random
import logging
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─── Configuration ────────────────────────────────────────────────────────────

CONFIG_FILE = Path("config.json")
SEEN_FILE = Path("seen_followers.json")
LOG_FILE = Path("bot.log")
BROWSER_PROFILE = Path("browser_profile")  # profil persistant (cookies + fingerprint)

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Fichier config.json introuvable. Copie config.example.json → config.json et remplis-le.")
    with open(CONFIG_FILE) as f:
        return json.load(f)

def load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    with open(SEEN_FILE) as f:
        return set(json.load(f))

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f, indent=2)

def human_delay(min_s=2.0, max_s=5.0):
    """Pause aléatoire pour imiter un comportement humain."""
    time.sleep(random.uniform(min_s, max_s))

# ─── LinkedIn Bot ──────────────────────────────────────────────────────────────

class LinkedInBot:
    def __init__(self, config: dict):
        self.email = config["linkedin_email"]
        self.password = config["linkedin_password"]
        self.page_url = config["page_url"]
        self.followers_url = config.get("followers_url") or (self.page_url.rstrip("/") + "/followers/")
        self.message_template = config["message_template"]
        self.headless = config.get("headless", False)
        self.page = None
        self._context = None

    def start(self, playwright):
        BROWSER_PROFILE.mkdir(exist_ok=True)
        # Profil persistant : cookies + localStorage + fingerprint sauvegardés sur disque
        self._context = playwright.webkit.launch_persistent_context(
            str(BROWSER_PROFILE),
            headless=self.headless,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        )
        # Réutiliser la page existante (évite d'ouvrir 2 fenêtres)
        if self._context.pages:
            self.page = self._context.pages[0]
            for extra in self._context.pages[1:]:
                extra.close()
        else:
            self.page = self._context.new_page()
        if BROWSER_PROFILE.exists() and any(BROWSER_PROFILE.iterdir()):
            log.info("Profil de navigateur chargé (session persistante).")

    def stop(self):
        if self._context:
            self._context.close()

    def _is_logged_in(self) -> bool:
        url = self.page.url
        return "/feed" in url or "/mynetwork" in url or "/jobs" in url

    def _try_auto_login(self) -> bool:
        """Tente un login automatique. Retourne True si on arrive sur le feed."""
        try:
            # Les deux premiers champs visible/caché — on essaie first puis last
            for idx in [0, 1]:
                try:
                    self.page.locator('input[type="email"]').nth(idx).fill(self.email, force=True)
                    self.page.locator('input[type="password"]').nth(idx).fill(self.password, force=True)
                    # Cliquer le bouton Einloggen correspondant (last = visible d'après les tests)
                    self.page.locator('button:has-text("Einloggen")').last.click(timeout=5_000)
                    self.page.wait_for_load_state("networkidle", timeout=10_000)
                    human_delay(2, 3)
                    if self._is_logged_in():
                        return True
                except Exception:
                    continue
        except Exception as e:
            log.debug(f"  Auto-login error: {e}")
        return False

    def login(self):
        log.info("Connexion à LinkedIn...")
        self.page.goto("https://www.linkedin.com/login")
        try:
            self.page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeout:
            pass

        log.info(f"  URL : {self.page.url}")

        if self._is_logged_in():
            log.info("✅ Déjà connecté (session persistante).")
            return

        if "checkpoint" in self.page.url or "challenge" in self.page.url:
            log.warning("⚠️  Vérification LinkedIn requise. Résous-la dans le navigateur, puis ENTRÉE.")
            input("→ ENTRÉE : ")
            return

        log.info("  Tentative de connexion automatique...")
        if self._try_auto_login():
            log.info("✅ Connecté automatiquement.")
            return

        # Fallback : login manuel dans la fenêtre du navigateur
        log.warning("⚠️  Connexion automatique impossible (protection LinkedIn).")
        log.warning("   Le navigateur est ouvert.")
        log.warning("   1. Entre tes identifiants dans le navigateur")
        log.warning("   2. Si LinkedIn demande une vérification sur ton téléphone, valide-la")
        log.warning("   3. Attends d'être sur linkedin.com/feed")
        log.warning("   4. SEULEMENT ALORS appuie sur ENTRÉE ici")

        while not self._is_logged_in():
            input("→ ENTRÉE quand tu es sur le feed LinkedIn : ")
            try:
                self.page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeout:
                pass
            if not self._is_logged_in():
                log.warning(f"  Pas encore sur le feed (URL actuelle : {self.page.url})")
                log.warning("  Attends d'être sur linkedin.com/feed avant d'appuyer sur ENTRÉE.")

        log.info("✅ Connecté.")

    @staticmethod
    def _clean_name(raw: str) -> str:
        """Extrait le nom propre depuis le texte brut d'une carte LinkedIn."""
        import re
        # Le nom est sur la première ligne, avant les mots-clés LinkedIn
        for sep in ["Relation de", "· 1er", "· 2e", "· 3e", "\n", "Connection"]:
            raw = raw.split(sep)[0]
        return re.sub(r'\s+', ' ', raw).strip()

    def get_followers(self) -> list[dict]:
        """Navigue vers la liste des abonnés et extrait les profils."""
        log.info(f"Récupération des abonnés : {self.followers_url}")
        self.page.goto(self.followers_url)
        human_delay(3, 5)
        self.page.screenshot(path="debug_followers.png")
        log.info("  Screenshot → debug_followers.png")

        # Cliquer le bouton qui affiche la liste complète des abonnés
        EXPAND_BTNS = [
            "Afficher tous les abonnés",
            "Voir tous les abonnés",
            "Voir plus",
            "Show all followers",
            "See more",
            "Alle Follower anzeigen",
            "Mehr anzeigen",
        ]
        for text in EXPAND_BTNS:
            try:
                btn = self.page.locator(f"button:has-text('{text}')").first
                if btn.is_visible():
                    btn.click()
                    log.info(f"  Cliqué '{text}'")
                    human_delay(3, 5)
                    break
            except Exception:
                pass

        seen_urls: set[str] = set()
        followers: list[dict] = []
        last_count = 0
        no_new_count = 0

        for _ in range(100):  # max 100 scrolls (1 000 abonnés)
            cards = self.page.query_selector_all("a[href*='/in/']")
            for card in cards:
                href = card.get_attribute("href")
                raw_name = card.inner_text().strip()
                if not href or not raw_name:
                    continue
                clean_url = ("https://www.linkedin.com" + href if href.startswith("/") else href)
                clean_url = clean_url.split("?")[0].rstrip("/")
                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)
                name = self._clean_name(raw_name)
                if name:
                    followers.append({"url": clean_url, "name": name})

            if len(followers) == last_count:
                no_new_count += 1
                if no_new_count >= 5:  # 4 scrolls sans nouveau = fin de liste
                    break
            else:
                no_new_count = 0
                last_count = len(followers)
                log.info(f"  {len(followers)} abonnés chargés...")

            # Scroller le container de la modale (scroll infini avec lazy-load)
            self.page.evaluate("""() => {
                // Remonter depuis un lien /in/ pour trouver le container scrollable de la modale
                const link = document.querySelector('a[href*="/in/"]');
                if (!link) { window.scrollBy(0, 800); return; }
                let el = link.parentElement;
                while (el && el !== document.body) {
                    const s = window.getComputedStyle(el);
                    if ((s.overflowY === 'auto' || s.overflowY === 'scroll')
                            && el.scrollHeight > el.clientHeight + 10) {
                        el.scrollBy(0, 800);
                        return;
                    }
                    el = el.parentElement;
                }
                window.scrollBy(0, 800);
            }""")
            human_delay(2.5, 3.5)  # Attendre le lazy-load (~1s requis par LinkedIn)

        log.info(f"  → {len(followers)} abonnés trouvés.")
        return followers

    def send_message(self, profile_url: str, name: str) -> bool:
        """Ouvre le profil et envoie un message."""
        try:
            log.info(f"  → Envoi message à {name} ({profile_url})")
            self.page.goto(profile_url)
            human_delay(2, 4)

            # Cherche le bouton "Message"
            msg_btn = self.page.query_selector("button:has-text('Message')")
            if not msg_btn:
                log.warning(f"  ⚠️  Bouton Message introuvable pour {name}")
                return False

            msg_btn.click()
            human_delay(1.5, 3)

            first_name = name.split()[0] if name else "là"
            message = self.message_template.replace("{prenom}", first_name).replace("{nom}", name)

            # Tape le message
            text_box = self.page.query_selector("div[contenteditable='true']")
            if not text_box:
                log.warning(f"  ⚠️  Zone de texte introuvable pour {name}")
                return False

            text_box.click()
            human_delay(0.5, 1)
            text_box.type(message, delay=random.randint(30, 80))  # Frappe humaine
            human_delay(1, 2)

            # Envoi
            send_btn = self.page.query_selector("button:has-text('Envoyer')")
            if not send_btn:
                send_btn = self.page.query_selector("button[type='submit']")
            if send_btn:
                send_btn.click()
                human_delay(1, 2)
                log.info(f"  ✅ Message envoyé à {name}")
                return True
            else:
                log.warning(f"  ⚠️  Bouton Envoyer introuvable pour {name}")
                return False

        except PlaywrightTimeout:
            log.error(f"  ❌ Timeout pour {name}")
            return False
        except Exception as e:
            log.error(f"  ❌ Erreur pour {name} : {e}")
            return False

# ─── Pipeline principal ────────────────────────────────────────────────────────

def save_all_followers(followers: list[dict]):
    """Sauvegarde tous les abonnés dans un fichier JSON horodaté."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_file = Path(f"all_followers_{ts}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(followers, f, indent=2, ensure_ascii=False)
    log.info(f"📄 {len(followers)} abonné(s) sauvegardé(s) dans {output_file}")

def run():
    dry_run = "--dry-run" in sys.argv
    config = load_config()
    seen = load_seen()
    bot = LinkedInBot(config)

    log.info("=" * 50)
    mode_label = "DRY-RUN (pas d'envoi)" if dry_run else "ENVOI ACTIF"
    log.info(f"Démarrage pipeline [{mode_label}] — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    with sync_playwright() as p:
        bot.start(p)
        try:
            bot.login()
            followers = bot.get_followers()

            if dry_run:
                save_all_followers(followers)
                log.info("Mode dry-run terminé. Aucun message envoyé.")
                return

            new_followers = [f for f in followers if f["url"] not in seen]
            log.info(f"{len(new_followers)} nouveau(x) abonné(s) détecté(s).")

            for follower in new_followers:
                success = bot.send_message(follower["url"], follower["name"])
                if success:
                    seen.add(follower["url"])
                    save_seen(seen)  # Sauvegarde après chaque envoi
                human_delay(10, 20)  # Pause entre chaque message

        finally:
            bot.stop()

    log.info("Pipeline terminé.")

if __name__ == "__main__":
    run()
