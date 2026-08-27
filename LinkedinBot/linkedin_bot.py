"""
LinkedIn Auto-Message Bot — V2
Gestion multi-catégories : nouveaux abonnés, relances, réponses.

Usage :
    python linkedin_bot.py --refresh                    # scrape + mise à jour contacts.json
    python linkedin_bot.py --send <cat>                 # envoi réel (new|relance_1|relance_2|relance_2plus)
    python linkedin_bot.py --simulate <cat>             # simulation sans envoi
    python linkedin_bot.py --test-message <url>         # test sur un profil précis

Table des matières
──────────────────
  1. Imports & constantes       Chemins, catégories, logging
  2. Helpers                    load_config, load/save_contacts, human_delay
  3. LinkedInBot                Classe principale
     3.1  start / stop
     3.2  login
     3.3  get_followers
     3.4  _navigate_to_compose
     3.5  send_message
     3.6  simulate_message
  4. Pipeline                   get_category, save_perf, run()
"""

# ─── 1. Imports & constantes ──────────────────────────────────────────────────

import json
import re
import time
import random
import logging
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_DIR        = Path(__file__).resolve().parent
CONFIG_FILE     = BASE_DIR / "config.json"
CONTACTS_FILE   = BASE_DIR / "contacts.json"
LOG_FILE        = BASE_DIR / "bot.log"
BROWSER_PROFILE = BASE_DIR / "browser_profile"

CATEGORIES = ["new", "relance_1", "relance_2", "relance_2plus"]

CATEGORY_LABEL = {
    "new":          "Nouveaux abonnés",
    "relance_1":    "1ère relance",
    "relance_2":    "2ème relance",
    "relance_2plus":"2+ relances",
}

CATEGORY_MSG_KEY = {
    "new":          "message_new",
    "relance_1":    "message_relance_1",
    "relance_2":    "message_relance_2",
    "relance_2plus":"message_relance_2plus",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ─── 2. Helpers ───────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("config.json introuvable.")
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

def load_contacts() -> list:
    if not CONTACTS_FILE.exists():
        return []
    return json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))

def save_contacts(contacts: list):
    CONTACTS_FILE.write_text(
        json.dumps(contacts, indent=2, ensure_ascii=False), encoding="utf-8"
    )

def human_delay(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))

# ─── 3. LinkedInBot ───────────────────────────────────────────────────────────

class LinkedInBot:
    def __init__(self, config: dict, message_template: str = ""):
        self.email            = config["linkedin_email"]
        self.password         = config["linkedin_password"]
        self.page_url         = config.get("page_url", "")
        self.followers_url    = config.get("followers_url") or (self.page_url.rstrip("/") + "/followers/")
        self.message_template = message_template
        self.headless         = config.get("headless", False)
        self.page             = None
        self._context         = None

    # ── 3.1 start / stop ──────────────────────────────────────────────────────

    def start(self, playwright):
        BROWSER_PROFILE.mkdir(exist_ok=True)
        self._context = playwright.webkit.launch_persistent_context(
            str(BROWSER_PROFILE),
            headless=self.headless,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        )
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

    # ── 3.2 login ─────────────────────────────────────────────────────────────

    def _is_logged_in(self) -> bool:
        url = self.page.url
        return "/feed" in url or "/mynetwork" in url or "/jobs" in url

    def _try_auto_login(self) -> bool:
        for idx in [0, 1]:
            try:
                self.page.locator('input[type="email"]').nth(idx).fill(self.email, force=True)
                self.page.locator('input[type="password"]').nth(idx).fill(self.password, force=True)
                self.page.locator('button:has-text("Einloggen")').last.click(timeout=5_000)
                self.page.wait_for_load_state("networkidle", timeout=10_000)
                human_delay(2, 3)
                if self._is_logged_in():
                    return True
            except Exception:
                continue
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

        log.warning("⚠️  Connexion automatique impossible.")
        while not self._is_logged_in():
            input("→ ENTRÉE quand tu es sur le feed LinkedIn : ")
            try:
                self.page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeout:
                pass
        log.info("✅ Connecté.")

    # ── 3.3 get_followers ─────────────────────────────────────────────────────

    @staticmethod
    def _clean_name(raw: str) -> str:
        for sep in ["Relation de", "· 1er", "· 2e", "· 3e", "\n", "Connection"]:
            raw = raw.split(sep)[0]
        return re.sub(r'\s+', ' ', raw).strip()

    def get_followers(self) -> list[dict]:
        log.info(f"Récupération des abonnés : {self.followers_url}")
        self.page.goto(self.followers_url)
        human_delay(3, 5)

        EXPAND_BTNS = [
            "Afficher tous les abonnés", "Voir tous les abonnés", "Voir plus",
            "Show all followers", "See more", "Alle Follower anzeigen", "Mehr anzeigen",
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

        for _ in range(150):
            for card in self.page.query_selector_all("a[href*='/in/']"):
                href     = card.get_attribute("href")
                raw_name = card.inner_text().strip()
                if not href or not raw_name:
                    continue
                url = ("https://www.linkedin.com" + href if href.startswith("/") else href)
                url = url.split("?")[0].rstrip("/")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                name = self._clean_name(raw_name)
                if name:
                    followers.append({"url": url, "name": name})

            if len(followers) == last_count:
                no_new_count += 1
                if no_new_count >= 8:
                    break
            else:
                no_new_count = 0
                last_count = len(followers)
                log.info(f"  {len(followers)} abonnés chargés...")

            self.page.evaluate("""() => {
                const MODAL_SELS = [
                    '.artdeco-modal__content',
                    '.scaffold-finite-scroll__content',
                    '[data-finite-scroll-hotspot]',
                    '.followers-list',
                ];
                for (const sel of MODAL_SELS) {
                    const el = document.querySelector(sel);
                    if (el && el.scrollHeight > el.clientHeight + 10) { el.scrollBy(0, 1000); return; }
                }
                const link = document.querySelector('a[href*="/in/"]');
                if (link) {
                    let el = link.parentElement;
                    while (el && el !== document.body) {
                        const s = window.getComputedStyle(el);
                        if ((s.overflowY === 'auto' || s.overflowY === 'scroll')
                                && el.scrollHeight > el.clientHeight + 10) {
                            el.scrollBy(0, 1000); return;
                        }
                        el = el.parentElement;
                    }
                }
                window.scrollBy(0, 1000);
            }""")
            human_delay(2.5, 3.5)

        log.info(f"  → {len(followers)} abonnés trouvés.")
        return followers

    # ── 3.4 _navigate_to_compose ──────────────────────────────────────────────

    def _navigate_to_compose(self, profile_url: str, name: str):
        """Navigue vers le profil puis la page de composition.
        Retourne (text_box, message) ou (None, '') en cas d'échec."""
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
            return None, ""

        compose_url = ("https://www.linkedin.com" + msg_href).replace("&interop=msgOverlay", "")
        log.info(f"  Ouverture compose : {compose_url[:80]}...")
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
                    log.info(f"  Zone de texte trouvée ({sel})")
                    break
            except PlaywrightTimeout:
                continue

        if not text_box:
            log.warning(f"  ⚠️  Zone de texte introuvable pour {name}")
            return None, ""

        first_name = name.split()[0] if name else "là"
        message = self.message_template.replace("{prenom}", first_name).replace("{nom}", name)
        return text_box, message

    # ── 3.5 send_message ──────────────────────────────────────────────────────

    def send_message(self, profile_url: str, name: str) -> bool:
        try:
            log.info(f"  → Envoi message à {name} ({profile_url})")
            if not self.message_template.strip():
                log.error("  ❌ message_template vide.")
                return False

            text_box, message = self._navigate_to_compose(profile_url, name)
            if not text_box:
                return False

            try:
                text_box.click(timeout=10_000)
            except PlaywrightTimeout:
                log.warning(f"  ⚠️  Impossible de cliquer la zone de texte pour {name}")
                return False
            human_delay(0.5, 1)
            self.page.keyboard.type(message, delay=random.randint(30, 60))
            human_delay(1, 2)

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

            log.warning(f"  ⚠️  Bouton Envoyer introuvable pour {name}")
            return False

        except PlaywrightTimeout:
            log.error(f"  ❌ Timeout pour {name} (URL: {self.page.url})")
            # self.page.screenshot(path="debug_message.png")
            return False
        except Exception as e:
            log.error(f"  ❌ Erreur pour {name} : {e}")
            return False

    # ── 3.6 simulate_message ──────────────────────────────────────────────────

    def simulate_message(self, profile_url: str, name: str) -> bool:
        try:
            text_box, message = self._navigate_to_compose(profile_url, name)
            if not text_box:
                return False
            log.info(f'  ✅ Message prêt pour {name} : "{message}"')
            return True
        except Exception as e:
            log.error(f"  ❌ Erreur simulation pour {name} : {e}")
            return False

# ─── 4. Pipeline ──────────────────────────────────────────────────────────────

def get_category(contact: dict) -> str:
    if contact.get("responded"):
        return "responded"
    n = contact.get("messages_sent", 0)
    if n == 0: return "new"
    if n == 1: return "relance_1"
    if n == 2: return "relance_2"
    return "relance_2plus"

def save_perf(perf: dict):
    path = BASE_DIR / "perf.json"
    path.write_text(json.dumps(perf, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("📊 Performances sauvegardées → perf.json")

def run():
    args = sys.argv[1:]
    config = load_config()
    run_start = time.time()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Mode détection ────────────────────────────────────────────────────────
    if "--refresh" in args or "--dry-run" in args:
        mode, category = "refresh", None
    elif "--send" in args:
        mode = "send"
        idx = args.index("--send")
        category = args[idx + 1] if idx + 1 < len(args) else "new"
    elif "--simulate" in args:
        mode = "simulate"
        idx = args.index("--simulate")
        category = args[idx + 1] if idx + 1 < len(args) else "new"
    elif "--test-message" in args:
        mode = "test"
        idx = args.index("--test-message")
        category = None
        test_url = args[idx + 1] if idx + 1 < len(args) else ""
    else:
        log.error("Usage : --refresh | --send <cat> | --simulate <cat> | --test-message <url>")
        return

    log.info("=" * 50)

    # ── REFRESH : scrape + mise à jour contacts.json ──────────────────────────
    if mode == "refresh":
        log.info(f"Mode REFRESH — {now_str}")
        with sync_playwright() as p:
            bot = LinkedInBot(config)
            bot.start(p)
            try:
                bot.login()
                followers = bot.get_followers()
            finally:
                bot.stop()

        contacts = load_contacts()
        existing_urls = {c["url"] for c in contacts}

        # Migration depuis seen_followers.json (première utilisation de la V2)
        seen_urls: set = set()
        if not CONTACTS_FILE.exists():
            old_seen = BASE_DIR / "seen_followers.json"
            if old_seen.exists():
                raw = old_seen.read_text().strip()
                seen_urls = set(json.loads(raw)) if raw else set()
                log.info(f"  Migration V1→V2 : {len(seen_urls)} abonnés déjà contactés importés.")

        new_count = 0
        for f in followers:
            if f["url"] not in existing_urls:
                contacts.append({
                    "url": f["url"],
                    "name": f["name"],
                    "messages_sent": 1 if f["url"] in seen_urls else 0,
                    "last_contacted": None,
                    "responded": False,
                    "added_at": now_str,
                })
                new_count += 1

        save_contacts(contacts)
        log.info(f"✅ {new_count} nouveaux abonnés ajoutés. Total contacts : {len(contacts)}")
        log.info(f"Refresh terminé en {round(time.time() - run_start, 1)}s.")
        return

    # ── SEND / SIMULATE ───────────────────────────────────────────────────────
    if mode in ("send", "simulate"):
        if category not in CATEGORY_MSG_KEY:
            log.error(f"Catégorie inconnue : '{category}'. Valeurs : {', '.join(CATEGORIES)}")
            return

        msg_key = CATEGORY_MSG_KEY[category]
        message_template = config.get(msg_key, "")
        # Compatibilité V1 : utilise message_template si message_new est absent
        if not message_template and category == "new":
            message_template = config.get("message_template", "")
        if not message_template.strip():
            log.error(f"❌ Message vide pour '{category}'. Configure-le dans l'interface.")
            return

        contacts = load_contacts()
        to_contact = [c for c in contacts if get_category(c) == category]
        action = "SIMULATION" if mode == "simulate" else "ENVOI"
        log.info(f"Mode {action} — {CATEGORY_LABEL[category]} — {len(to_contact)} abonnés — {now_str}")

        perf = {"date": now_str, "mode": f"{mode}_{category}", "login_s": None, "messages": [], "total_s": None}

        with sync_playwright() as p:
            bot = LinkedInBot(config, message_template)
            bot.start(p)
            try:
                t = time.time()
                bot.login()
                perf["login_s"] = round(time.time() - t, 1)

                for contact in to_contact:
                    t = time.time()
                    if mode == "simulate":
                        success = bot.simulate_message(contact["url"], contact["name"])
                    else:
                        success = bot.send_message(contact["url"], contact["name"])
                        if success:
                            contact["messages_sent"] += 1
                            contact["last_contacted"] = now_str
                            save_contacts(contacts)

                    perf["messages"].append({
                        "name": contact["name"],
                        "url": contact["url"],
                        "success": success,
                        "duration_s": round(time.time() - t, 1),
                    })
                    if mode != "simulate" and contact is not to_contact[-1]:
                        human_delay(10, 20)
            finally:
                bot.stop()

        perf["total_s"] = round(time.time() - run_start, 1)
        save_perf(perf)
        log.info(f"Pipeline terminé en {perf['total_s']}s.")
        return

    # ── TEST MESSAGE ──────────────────────────────────────────────────────────
    if mode == "test":
        msg_template = config.get("message_new") or config.get("message_template", "")
        name = input("Nom de la personne de test (ex: Marie Dupont) : ").strip() or "Test"
        with sync_playwright() as p:
            bot = LinkedInBot(config, msg_template)
            bot.start(p)
            try:
                bot.login()
                success = bot.send_message(test_url, name)
            finally:
                bot.stop()
        log.info("✅ Message test envoyé." if success else "❌ Échec.")

if __name__ == "__main__":
    run()
