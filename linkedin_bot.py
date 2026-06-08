"""
LinkedIn Auto-Message Bot
Détecte les nouveaux abonnés d'une Page LinkedIn et envoie un message automatique.

Usage:
    python linkedin_bot.py                                      # mode normal (envoi de messages)
    python linkedin_bot.py --dry-run                            # scrape les abonnés sans envoyer
    python linkedin_bot.py --test-message <url_profil_linkedin> # envoie un message test à un profil spécifique

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
        btn_clicked = False
        for text in EXPAND_BTNS:
            try:
                btn = self.page.locator(f"button:has-text('{text}')").first
                if btn.is_visible():
                    btn.click()
                    log.info(f"  Cliqué '{text}'")
                    human_delay(3, 5)
                    btn_clicked = True
                    break
            except Exception:
                pass
        if not btn_clicked:
            log.warning("  ⚠️  Bouton 'Afficher tous les abonnés' non trouvé — scraping de la page telle quelle.")
        self.page.screenshot(path="debug_followers_modal.png")
        log.info("  Screenshot modal → debug_followers_modal.png")

        seen_urls: set[str] = set()
        followers: list[dict] = []
        last_count = 0
        no_new_count = 0

        for i in range(150):  # max 150 scrolls (~1 500 abonnés)
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
                if no_new_count >= 8:  # 8 scrolls consécutifs sans nouveau = fin de liste
                    break
            else:
                no_new_count = 0
                last_count = len(followers)
                log.info(f"  {len(followers)} abonnés chargés...")

            # Scroller : essaie d'abord les containers connus de LinkedIn,
            # puis remonte depuis un lien /in/, sinon scroll la fenêtre
            scrolled = self.page.evaluate("""() => {
                // 1. Containers connus de la modale LinkedIn
                const MODAL_SELS = [
                    '.artdeco-modal__content',
                    '.scaffold-finite-scroll__content',
                    '[data-finite-scroll-hotspot]',
                    '.followers-list',
                ];
                for (const sel of MODAL_SELS) {
                    const el = document.querySelector(sel);
                    if (el && el.scrollHeight > el.clientHeight + 10) {
                        el.scrollBy(0, 1000);
                        return sel;
                    }
                }
                // 2. Remonter depuis un lien /in/
                const link = document.querySelector('a[href*="/in/"]');
                if (link) {
                    let el = link.parentElement;
                    while (el && el !== document.body) {
                        const s = window.getComputedStyle(el);
                        if ((s.overflowY === 'auto' || s.overflowY === 'scroll')
                                && el.scrollHeight > el.clientHeight + 10) {
                            el.scrollBy(0, 1000);
                            return 'parent-of-link';
                        }
                        el = el.parentElement;
                    }
                }
                // 3. Fallback : scroll fenêtre
                window.scrollBy(0, 1000);
                return 'window';
            }""")
            if i < 3:
                log.info(f"  Scroll {i+1} via : {scrolled}")
            human_delay(2.5, 3.5)  # Attendre le lazy-load (~1s requis par LinkedIn)

        log.info(f"  → {len(followers)} abonnés trouvés.")
        return followers

    def send_message(self, profile_url: str, name: str) -> bool:
        """Ouvre le profil, récupère l'URL de composition et envoie un message."""
        try:
            log.info(f"  → Envoi message à {name} ({profile_url})")
            self.page.goto(profile_url)
            try:
                self.page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeout:
                pass
            human_delay(2, 3)
            self.page.keyboard.press("Escape")
            human_delay(0.5, 1)

            # Le bouton "Message" sur un profil LinkedIn est un <a> vers /messaging/compose/
            msg_href = self.page.evaluate("""() => {
                const el = Array.from(document.querySelectorAll('a')).find(a => {
                    if (!a.textContent.trim().toLowerCase().includes('message')) return false;
                    if (a.closest('nav, header')) return false;
                    const href = a.getAttribute('href') || '';
                    if (!href.includes('messaging/compose')) return false;
                    const r = a.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
                return el ? el.getAttribute('href') : null;
            }""")

            if not msg_href:
                self.page.screenshot(path="debug_message.png")
                log.warning(f"  ⚠️  Lien Message introuvable pour {name} → debug_message.png")
                return False

            # Naviguer directement vers la page de composition (sans interop=msgOverlay)
            compose_url = ("https://www.linkedin.com" + msg_href).replace("&interop=msgOverlay", "")
            log.info(f"  Ouverture compose : {compose_url[:80]}...")
            self.page.goto(compose_url)
            try:
                self.page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeout:
                pass
            human_delay(2, 3)

            if not self.message_template.strip():
                log.error("  ❌ message_template vide dans config.json — remplis-le avant d'envoyer.")
                return False

            first_name = name.split()[0] if name else "là"
            message = self.message_template.replace("{prenom}", first_name).replace("{nom}", name)

            # Zone de texte de composition
            text_box = None
            for sel in ["div.msg-form__contenteditable", "div[contenteditable='true']", "[contenteditable='true']"]:
                try:
                    text_box = self.page.wait_for_selector(sel, timeout=8_000)
                    if text_box:
                        log.info(f"  Zone de texte trouvée ({sel})")
                        break
                except PlaywrightTimeout:
                    continue

            if not text_box:
                self.page.screenshot(path="debug_message.png")
                log.warning(f"  ⚠️  Zone de texte introuvable pour {name} → debug_message.png")
                return False

            # Cliquer pour focuser, puis taper via le clavier (plus fiable sur contenteditable)
            try:
                text_box.click(timeout=10_000)
            except PlaywrightTimeout:
                log.warning(f"  ⚠️  Impossible de cliquer la zone de texte pour {name}")
                self.page.screenshot(path="debug_message.png")
                return False
            human_delay(0.5, 1)
            self.page.keyboard.type(message, delay=random.randint(30, 60))
            human_delay(1, 2)

            # Bouton d'envoi (classe CSS LinkedIn + texte multilingue)
            send_btn = None
            for sel in [
                "button.msg-form__send-button",
                "button[aria-label*='Envoyer']",
                "button[aria-label*='Send']",
                "button:has-text('Envoyer')",
                "button:has-text('Send')",
                "button:has-text('Senden')",
            ]:
                try:
                    btn = self.page.locator(sel).last
                    if btn.is_visible(timeout=2_000):
                        send_btn = btn
                        log.info(f"  Bouton Envoyer trouvé ({sel})")
                        break
                except Exception:
                    continue

            if send_btn:
                send_btn.click(timeout=10_000)
                human_delay(1, 2)
                log.info(f"  ✅ Message envoyé à {name}")
                return True
            else:
                self.page.screenshot(path="debug_message.png")
                log.warning(f"  ⚠️  Bouton Envoyer introuvable pour {name} → debug_message.png")
                return False

        except PlaywrightTimeout:
            log.error(f"  ❌ Timeout pour {name} (URL: {self.page.url})")
            self.page.screenshot(path="debug_message.png")
            log.error(f"  Screenshot → debug_message.png")
            return False
        except Exception as e:
            log.error(f"  ❌ Erreur pour {name} : {e}")
            return False

    def simulate_message(self, profile_url: str, name: str) -> bool:
        """Vérifie que le message est prêt à envoyer sans l'envoyer."""
        try:
            self.page.goto(profile_url)
            try:
                self.page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeout:
                pass
            human_delay(2, 3)
            self.page.keyboard.press("Escape")
            human_delay(0.5, 1)

            msg_href = self.page.evaluate("""() => {
                const el = Array.from(document.querySelectorAll('a')).find(a => {
                    if (!a.textContent.trim().toLowerCase().includes('message')) return false;
                    if (a.closest('nav, header')) return false;
                    const href = a.getAttribute('href') || '';
                    if (!href.includes('messaging/compose')) return false;
                    const r = a.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
                return el ? el.getAttribute('href') : null;
            }""")

            if not msg_href:
                log.warning(f"  ⚠️  Lien Message introuvable pour {name}")
                return False

            compose_url = ("https://www.linkedin.com" + msg_href).replace("&interop=msgOverlay", "")
            self.page.goto(compose_url)
            try:
                self.page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeout:
                pass
            human_delay(2, 3)

            text_box = None
            for sel in ["div.msg-form__contenteditable", "div[contenteditable='true']", "[contenteditable='true']"]:
                try:
                    text_box = self.page.wait_for_selector(sel, timeout=8_000)
                    if text_box:
                        break
                except PlaywrightTimeout:
                    continue

            if not text_box:
                log.warning(f"  ⚠️  Zone de texte introuvable pour {name}")
                return False

            first_name = name.split()[0] if name else "là"
            message = self.message_template.replace("{prenom}", first_name).replace("{nom}", name)
            log.info(f'  ✅ Message prêt à être envoyé pour {name} : "{message}"')
            return True

        except Exception as e:
            log.error(f"  ❌ Erreur simulation pour {name} : {e}")
            return False

# ─── Pipeline principal ────────────────────────────────────────────────────────

def save_perf(perf: dict):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = Path(f"perf_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(perf, f, indent=2, ensure_ascii=False)
    log.info(f"📊 Performances sauvegardées → {path}")

def save_all_followers(followers: list[dict]):
    """Sauvegarde tous les abonnés dans un fichier JSON horodaté."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_file = Path(f"all_followers_{ts}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(followers, f, indent=2, ensure_ascii=False)
    log.info(f"📄 {len(followers)} abonné(s) sauvegardé(s) dans {output_file}")

def _parse_args():
    dry_run = "--dry-run" in sys.argv
    simulate = "--simulate" in sys.argv
    test_url = None
    if "--test-message" in sys.argv:
        idx = sys.argv.index("--test-message")
        if idx + 1 < len(sys.argv):
            test_url = sys.argv[idx + 1]
        else:
            raise SystemExit("Usage : python linkedin_bot.py --test-message <https://www.linkedin.com/in/andrea-milano/>")
    return dry_run, simulate, test_url

def _duration(start: float) -> float:
    return round(time.time() - start, 1)

def run():
    dry_run, simulate, test_url = _parse_args()
    config = load_config()
    seen = load_seen()
    bot = LinkedInBot(config)

    run_start = time.time()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    log.info("=" * 50)
    if test_url:
        mode_label = f"TEST MESSAGE → {test_url}"
    elif simulate:
        mode_label = "SIMULATION (pipeline complet, aucun message envoyé)"
    elif dry_run:
        mode_label = "DRY-RUN (scraping seul)"
    else:
        mode_label = "ENVOI ACTIF"
    log.info(f"Démarrage pipeline [{mode_label}] — {now_str}")

    perf = {
        "date": now_str,
        "mode": mode_label,
        "login_s": None,
        "scraping_s": None,
        "messages": [],
        "total_s": None,
    }

    with sync_playwright() as p:
        bot.start(p)
        try:
            t = time.time()
            bot.login()
            perf["login_s"] = _duration(t)
            log.info(f"  ⏱ Login : {perf['login_s']}s")

            if test_url:
                name = input("Prénom/Nom de la personne de test (ex: Marie Dupont) : ").strip() or "Test"
                log.info(f"Envoi d'un message test à {name} ({test_url})...")
                t = time.time()
                success = bot.send_message(test_url, name)
                perf["messages"].append({"name": name, "url": test_url, "success": success, "duration_s": _duration(t)})
                if success:
                    log.info("✅ Message test envoyé avec succès.")
                else:
                    log.error("❌ Échec de l'envoi du message test.")
                perf["total_s"] = _duration(run_start)
                save_perf(perf)
                return

            t = time.time()
            followers = bot.get_followers()
            perf["scraping_s"] = _duration(t)
            log.info(f"  ⏱ Scraping : {perf['scraping_s']}s")

            if dry_run:
                save_all_followers(followers)
                perf["total_s"] = _duration(run_start)
                save_perf(perf)
                log.info("Mode dry-run terminé. Aucun message envoyé.")
                return

            new_followers = [f for f in followers if f["url"] not in seen]
            log.info(f"{len(new_followers)} nouveau(x) abonné(s) à traiter.")

            if simulate:
                for follower in new_followers:
                    log.info(f"→ Message à envoyer à {follower['name']}")
                    t = time.time()
                    success = bot.simulate_message(follower["url"], follower["name"])
                    perf["messages"].append({"name": follower["name"], "url": follower["url"], "success": success, "duration_s": _duration(t)})
                    human_delay(3, 5)
                perf["total_s"] = _duration(run_start)
                save_perf(perf)
                log.info("Simulation terminée. Aucun message envoyé, seen_followers.json inchangé.")
                return

            for follower in new_followers:
                t = time.time()
                success = bot.send_message(follower["url"], follower["name"])
                perf["messages"].append({"name": follower["name"], "url": follower["url"], "success": success, "duration_s": _duration(t)})
                if success:
                    seen.add(follower["url"])
                    save_seen(seen)
                human_delay(10, 20)

        finally:
            bot.stop()

    perf["total_s"] = _duration(run_start)
    save_perf(perf)
    log.info(f"Pipeline terminé en {perf['total_s']}s.")

if __name__ == "__main__":
    run()
