"""
launcher.py — SGA Finance Launcher / Watchdog
=============================================
Always running on port 5001.
Use this to START or STOP the main app (port 5000) from your phone browser.

Password: sanjay@#0531
"""

import os
import sys
import subprocess
import threading
from flask import Flask, request, jsonify, render_template_string

# ── Config ──────────────────────────────────────────────────────────────────
LAUNCHER_PORT    = 5001
LAUNCHER_PASSWORD = "sanjay@#0531"
APP_SCRIPT       = os.path.join(os.path.dirname(__file__), "app.py")
PYTHON_EXE       = os.path.join(os.path.dirname(__file__), "venv314", "Scripts", "python.exe")

# ── State ────────────────────────────────────────────────────────────────────
_app_process = None   # subprocess.Popen handle for the main app
_lock = threading.Lock()

# ── Launcher Flask app ────────────────────────────────────────────────────────
launcher = Flask(__name__)

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>SGA Finance — Launcher</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: linear-gradient(145deg, #14532d 0%, #166534 40%, #15803d 100%);
      display: flex; align-items: center; justify-content: center;
      padding: 24px;
    }
    .card {
      background: #fff;
      border-radius: 24px;
      padding: 40px 32px;
      max-width: 380px;
      width: 100%;
      text-align: center;
      box-shadow: 0 32px 80px rgba(0,0,0,.35);
    }
    .logo {
      width: 72px; height: 72px;
      background: linear-gradient(135deg,#14532d,#16a34a);
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 2rem; color: #fff;
      margin: 0 auto 16px;
    }
    h1 { font-size: 1.5rem; font-weight: 800; color: #14532d; margin-bottom: 4px; }
    .sub { color: #64748b; font-size: .875rem; margin-bottom: 28px; }

    .status-badge {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 16px; border-radius: 999px; font-size: .82rem;
      font-weight: 600; margin-bottom: 28px;
    }
    .status-badge.running  { background: #dcfce7; color: #166534; }
    .status-badge.stopped  { background: #fee2e2; color: #991b1b; }
    .dot { width:8px; height:8px; border-radius:50%; }
    .dot.green { background:#16a34a; animation: pulse 1.4s ease-in-out infinite; }
    .dot.red   { background:#dc2626; }
    @keyframes pulse {
      0%,100% { opacity:1; } 50% { opacity:.4; }
    }

    input[type=password] {
      width: 100%; padding: 12px 16px;
      border: 1.5px solid #d1fae5; border-radius: 12px;
      font-size: .9375rem; outline: none; margin-bottom: 12px;
      transition: border-color .2s;
    }
    input[type=password]:focus { border-color: #16a34a; }

    .err { color: #dc2626; font-size: .82rem; margin-bottom: 10px; min-height: 18px; }

    .btn {
      width: 100%; padding: 13px;
      border: none; border-radius: 12px;
      font-weight: 700; font-size: 1rem; cursor: pointer;
      transition: filter .2s, transform .15s;
      margin-bottom: 10px;
    }
    .btn:hover { filter: brightness(1.07); transform: translateY(-1px); }
    .btn:active { transform: translateY(0); }
    .btn-start { background: linear-gradient(135deg,#16a34a,#22c55e); color: #fff; }
    .btn-stop  { background: linear-gradient(135deg,#dc2626,#ef4444); color: #fff; }
    .btn-refresh { background: #f1f5f9; color: #475569; font-size:.875rem; padding:10px; }

    .note { color: #94a3b8; font-size: .78rem; margin-top: 16px; }
  </style>
</head>
<body>
<div class="card">
  <div class="logo">⚡</div>
  <h1>SGA Finance</h1>
  <p class="sub">Server Control Panel</p>

  <div class="status-badge {{ 'running' if running else 'stopped' }}">
    <span class="dot {{ 'green' if running else 'red' }}"></span>
    {{ 'Server is Running' if running else 'Server is Stopped' }}
  </div>

  <input type="password" id="pwd" placeholder="Enter password" 
         onkeydown="if(event.key==='Enter') action()" />
  <div class="err" id="err"></div>

  {% if not running %}
  <button class="btn btn-start" onclick="action('start')">▶ Start Server</button>
  {% else %}
  <button class="btn btn-stop"  onclick="action('stop')">⏹ Stop Server</button>
  {% endif %}
  <button class="btn btn-refresh" onclick="location.reload()">↻ Refresh Status</button>

  <p class="note">Port 5000 · Launcher on 5001</p>
</div>

<script>
  function action(cmd) {
    const pwd = document.getElementById('pwd').value;
    if (!pwd) { document.getElementById('err').textContent = 'Enter the password first.'; return; }
    document.getElementById('err').textContent = '';

    fetch('/launcher/' + cmd, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd })
    })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data }) => {
      if (!ok) {
        document.getElementById('err').textContent = data.error || 'Wrong password.';
      } else {
        setTimeout(() => location.reload(), 1500);
      }
    })
    .catch(() => {
      setTimeout(() => location.reload(), 2000);
    });
  }
</script>
</body>
</html>
"""


def _is_running():
    """Check if the main app process is alive."""
    global _app_process
    if _app_process is None:
        return False
    poll = _app_process.poll()
    return poll is None  # None means still running


@launcher.route("/")
def index():
    return render_template_string(PAGE, running=_is_running())


@launcher.route("/launcher/start", methods=["POST"])
def start_app():
    global _app_process
    data = request.get_json(silent=True) or {}
    if data.get("password") != LAUNCHER_PASSWORD:
        return jsonify({"error": "Wrong password."}), 403

    with _lock:
        if _is_running():
            return jsonify({"status": "already_running"}), 200
        _app_process = subprocess.Popen(
            [PYTHON_EXE, APP_SCRIPT],
            cwd=os.path.dirname(__file__)
        )
    return jsonify({"status": "started"}), 200


@launcher.route("/launcher/stop", methods=["POST"])
def stop_app():
    global _app_process
    data = request.get_json(silent=True) or {}
    if data.get("password") != LAUNCHER_PASSWORD:
        return jsonify({"error": "Wrong password."}), 403

    with _lock:
        if not _is_running():
            return jsonify({"status": "already_stopped"}), 200
        _app_process.terminate()
        try:
            _app_process.wait(timeout=5)
        except Exception:
            _app_process.kill()
        _app_process = None
    return jsonify({"status": "stopped"}), 200


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n  SGA Finance Launcher running on http://0.0.0.0:{LAUNCHER_PORT}")
    print(f"  Main app will be started on port 5000\n")

    # Auto-start the main app when launcher boots
    with _lock:
        _app_process = subprocess.Popen(
            [PYTHON_EXE, APP_SCRIPT],
            cwd=os.path.dirname(__file__)
        )
        print("  [OK] Main app started (PID:", _app_process.pid, ")")

    launcher.run(host="0.0.0.0", port=LAUNCHER_PORT, debug=False)
