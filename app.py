"""
Interface web pour LinkedIn Bot.
Usage : python app.py  →  ouvre http://localhost:5000
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

CONFIG_FILE = Path("config.json")
SEEN_FILE   = Path("seen_followers.json")
RUN_LOG     = Path("run_output.txt")

_proc = None
_lock = threading.Lock()

ALLOWED_FILES = {"all_followers.json", "perf.json"}


def _load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}


def _save_config(patch: dict):
    cfg = _load_config()
    cfg.update(patch)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def _stats() -> dict:
    seen_count = 0
    if SEEN_FILE.exists():
        seen_count = len(json.loads(SEEN_FILE.read_text(encoding="utf-8")))

    perf_path = Path("perf.json")
    last_perf = None
    if perf_path.exists():
        last_perf = json.loads(perf_path.read_text(encoding="utf-8"))

    return {"seen_count": seen_count, "last_perf": last_perf}


def _is_running() -> bool:
    with _lock:
        return _proc is not None and _proc.poll() is None


@app.route("/")
def index():
    return render_template(
        "index.html",
        config=_load_config(),
        stats=_stats(),
        followers_files=["all_followers.json"] if Path("all_followers.json").exists() else [],
        perf_files=["perf.json"] if Path("perf.json").exists() else [],
        running=_is_running(),
    )


@app.route("/run/<mode>", methods=["POST"])
def run_bot(mode):
    global _proc

    if _is_running():
        return jsonify({"error": "Bot déjà en cours d'exécution"}), 409

    modes = {"dry-run": ["--dry-run"], "simulate": ["--simulate"], "send": []}
    if mode not in modes:
        return jsonify({"error": "Mode inconnu"}), 400

    cmd = [sys.executable, "linkedin_bot.py"] + modes[mode]

    def _run():
        global _proc
        fout = open(RUN_LOG, "w", encoding="utf-8")
        proc = subprocess.Popen(
            cmd, stdout=fout, stderr=subprocess.STDOUT,
            text=True, cwd=Path(".").resolve(),
        )
        with _lock:
            _proc = proc
        proc.wait()
        fout.close()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/status")
def status():
    output = ""
    if RUN_LOG.exists():
        output = RUN_LOG.read_text(encoding="utf-8", errors="replace")
    return jsonify({"running": _is_running(), "output": output[-5000:]})


@app.route("/config", methods=["POST"])
def update_config():
    _save_config(request.json)
    return jsonify({"status": "ok"})


@app.route("/files/<path:filename>")
def view_file(filename):
    if filename not in ALLOWED_FILES:
        return "Non autorisé", 403
    p = Path(filename)
    if not p.exists():
        return "Introuvable", 404
    return jsonify(json.loads(p.read_text(encoding="utf-8")))


@app.route("/shutdown", methods=["POST"])
def shutdown():
    threading.Timer(0.5, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
    return jsonify({"status": "stopping"})


if __name__ == "__main__":
    print("Interface disponible sur → http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
