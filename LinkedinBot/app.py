"""
LinkedIn Bot V2 — Interface web
Usage : python app.py → http://localhost:5000
"""

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE_DIR      = Path(__file__).resolve().parent
CONFIG_FILE   = BASE_DIR / "config.json"
CONTACTS_FILE = BASE_DIR / "contacts.json"
RUN_LOG       = BASE_DIR / "run_output.txt"

_proc = None
_lock = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}

def _save_config(patch: dict):
    cfg = _load_config()
    cfg.update(patch)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def _load_contacts() -> list:
    return json.loads(CONTACTS_FILE.read_text(encoding="utf-8")) if CONTACTS_FILE.exists() else []

def _save_contacts(contacts: list):
    CONTACTS_FILE.write_text(json.dumps(contacts, indent=2, ensure_ascii=False), encoding="utf-8")

def _get_category(c: dict) -> str:
    if c.get("responded"):
        return "responded"
    n = c.get("messages_sent", 0)
    if n == 0: return "new"
    if n == 1: return "relance_1"
    if n == 2: return "relance_2"
    return "relance_2plus"

def _get_counts() -> dict:
    contacts = _load_contacts()
    counts = {"new": 0, "relance_1": 0, "relance_2": 0, "relance_2plus": 0, "responded": 0, "total": len(contacts)}
    for c in contacts:
        counts[_get_category(c)] += 1
    return counts

def _is_running() -> bool:
    with _lock:
        return _proc is not None and _proc.poll() is None

# ── Routes principales ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

# ── API config ────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(_load_config())

@app.route("/api/config", methods=["POST"])
def api_config_post():
    _save_config(request.json)
    return jsonify({"status": "ok"})

# ── API contacts ──────────────────────────────────────────────────────────────

@app.route("/api/counts")
def api_counts():
    return jsonify(_get_counts())

@app.route("/api/contacts")
def api_contacts():
    q = (request.args.get("q") or "").lower()
    contacts = _load_contacts()
    if q:
        contacts = [c for c in contacts if q in c.get("name", "").lower()]
    for c in contacts:
        c["_category"] = _get_category(c)
    return jsonify(contacts)

@app.route("/api/contacts/<category>")
def api_contacts_by_cat(category):
    contacts = _load_contacts()
    return jsonify([c for c in contacts if _get_category(c) == category])

@app.route("/api/mark-responded", methods=["POST"])
def api_mark_responded():
    url = request.json.get("url")
    contacts = _load_contacts()
    for c in contacts:
        if c["url"] == url:
            c["responded"] = True
            break
    _save_contacts(contacts)
    return jsonify({"status": "ok", "counts": _get_counts()})

@app.route("/api/unmark-responded", methods=["POST"])
def api_unmark_responded():
    url = request.json.get("url")
    contacts = _load_contacts()
    for c in contacts:
        if c["url"] == url:
            c["responded"] = False
            break
    _save_contacts(contacts)
    return jsonify({"status": "ok", "counts": _get_counts()})

# ── API bot ───────────────────────────────────────────────────────────────────

VALID_MODES = {
    "refresh":          ["--refresh"],
    "send_new":         ["--send", "new"],
    "send_relance_1":   ["--send", "relance_1"],
    "send_relance_2":   ["--send", "relance_2"],
    "send_relance_2plus":["--send", "relance_2plus"],
    "sim_new":          ["--simulate", "new"],
    "sim_relance_1":    ["--simulate", "relance_1"],
    "sim_relance_2":    ["--simulate", "relance_2"],
    "sim_relance_2plus":["--simulate", "relance_2plus"],
}

@app.route("/run/<mode>", methods=["POST"])
def run_bot(mode):
    global _proc
    if _is_running():
        return jsonify({"error": "Bot déjà en cours d'exécution"}), 409

    if mode in ("send_once", "sim_once"):
        data = request.json or {}
        urls = [u for u in (data.get("urls") or []) if isinstance(u, str) and u]
        if not urls:
            return jsonify({"error": "Sélectionne au moins un destinataire"}), 400
        flag = "--send-once" if mode == "send_once" else "--simulate-once"
        cmd = [sys.executable, str(BASE_DIR / "linkedin_bot.py"), flag] + urls
    elif mode in VALID_MODES:
        data = request.json or {}
        urls = data.get("urls")
        if urls is not None and not urls:
            return jsonify({"error": "Sélectionne au moins un abonné"}), 400
        cmd = [sys.executable, str(BASE_DIR / "linkedin_bot.py")] + VALID_MODES[mode]
        if urls:
            cmd += ["--urls"] + [u for u in urls if isinstance(u, str) and u]
    else:
        return jsonify({"error": "Mode inconnu"}), 400

    def _run():
        global _proc
        with open(RUN_LOG, "w", encoding="utf-8") as fout:
            proc = subprocess.Popen(cmd, stdout=fout, stderr=subprocess.STDOUT,
                                    text=True, cwd=str(BASE_DIR))
            with _lock:
                _proc = proc
            proc.wait()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/status")
def status():
    output = RUN_LOG.read_text(encoding="utf-8", errors="replace") if RUN_LOG.exists() else ""
    return jsonify({"running": _is_running(), "output": output[-6000:], "counts": _get_counts()})

@app.route("/shutdown", methods=["POST"])
def shutdown():
    threading.Timer(0.5, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
    return jsonify({"status": "stopping"})

if __name__ == "__main__":
    print("Interface disponible sur → http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
