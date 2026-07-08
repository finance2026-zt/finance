"""
launcher.py — SGA Finance Launcher / Watchdog
=============================================
Always running on port 5001.
Use this to START or STOP the main app (port 5000) from your phone browser.

Password: sanjay@#0531
"""

import os
import socket
import subprocess
import threading
from flask import Flask, request, jsonify, render_template_string

# ── Config ───────────────────────────────────────────────────────────────────
LAUNCHER_PORT     = 5001
APP_PORT          = 5000
LAUNCHER_PASSWORD = "sanjay@#0531"
APP_SCRIPT        = os.path.join(os.path.dirname(__file__), "app.py")
PYTHON_EXE        = os.path.join(os.path.dirname(__file__), "venv314", "Scripts", "python.exe")

# ── State ────────────────────────────────────────────────────────────────────
_app_process = None
_lock = threading.Lock()

# ── Real health check — actually connects to port 5000 ───────────────────────
def _is_running():
    """Return True only if something is actually listening on APP_PORT."""
    try:
        with socket.create_connection(("127.0.0.1", APP_PORT), timeout=1):
            return True
    except OSError:
        return False

# ── HTML page ────────────────────────────────────────────────────────────────
PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>SGA Finance — Control Panel</title>
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
    .sub { color: #64748b; font-size: .875rem; margin-bottom: 24px; }

    .status-badge {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 8px 20px; border-radius: 999px; font-size: .85rem;
      font-weight: 700; margin-bottom: 28px;
    }
    .status-badge.running { background: #dcfce7; color: #166534; }
    .status-badge.stopped { background: #fee2e2; color: #991b1b; }
    .dot { width: 9px; height: 9px; border-radius: 50%; }
    .dot.green { background: #16a34a; animation: pulse 1.4s ease-in-out infinite; }
    .dot.red   { background: #dc2626; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }

    .section-label {
      font-size: .78rem; font-weight: 700; color: #94a3b8;
      text-transform: uppercase; letter-spacing: .08em;
      margin-bottom: 10px; text-align: left;
    }
    input[type=password] {
      width: 100%; padding: 13px 16px;
      border: 1.5px solid #d1fae5; border-radius: 12px;
      font-size: 1rem; outline: none; margin-bottom: 10px;
      transition: border-color .2s; background: #f0fdf4;
    }
    input[type=password]:focus { border-color: #16a34a; background: #fff; }
    .err {
      color: #dc2626; font-size: .82rem; margin-bottom: 10px;
      min-height: 18px; text-align: left;
    }
    .btn {
      width: 100%; padding: 14px;
      border: none; border-radius: 12px;
      font-weight: 700; font-size: 1rem; cursor: pointer;
      transition: filter .2s, transform .15s;
      margin-bottom: 10px;
    }
    .btn:hover  { filter: brightness(1.07); transform: translateY(-1px); }
    .btn:active { transform: translateY(0); }
    .btn-start   { background: linear-gradient(135deg,#16a34a,#22c55e); color: #fff; }
    .btn-stop    { background: linear-gradient(135deg,#dc2626,#ef4444); color: #fff; }
    .btn-refresh {
      background: #f1f5f9; color: #475569;
      font-size: .875rem; padding: 11px;
      border: 1.5px solid #e2e8f0;
    }
    .note { color: #94a3b8; font-size: .78rem; margin-top: 18px; }
    .spinner {
      display: none; width: 20px; height: 20px;
      border: 3px solid rgba(255,255,255,.4);
      border-top-color: #fff; border-radius: 50%;
      animation: spin .7s linear infinite;
      margin: 0 auto;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
<div class="card">
  <div class="logo">&#9889;</div>
  <h1>SGA Finance</h1>
  <p class="sub">Server Control Panel</p>

  <div class="status-badge {{ 'running' if running else 'stopped' }}">
    <span class="dot {{ 'green' if running else 'red' }}"></span>
    {{ 'Server Running' if running else 'Server Stopped' }}
  </div>

  <div class="section-label">Password required</div>
  <input type="password" id="pwd" placeholder="Enter shutdown password"
         onkeydown="if(event.key==='Enter') doAction()" />
  <div class="err" id="err"></div>

  {% if not running %}
  <button class="btn btn-start" id="actionBtn" onclick="doAction('start')">
    &#9654; Start Server
  </button>
  {% else %}
  <button class="btn btn-stop" id="actionBtn" onclick="doAction('stop')">
    &#9209; Stop Server
  </button>
  {% endif %}

  <button class="btn btn-refresh" onclick="location.reload()">&#8635; Refresh Status</button>

  <p class="note">Main app: port {{ app_port }} &nbsp;|&nbsp; Launcher: port {{ launcher_port }}</p>
</div>

<script>
  function doAction(cmd) {
    const pwd = document.getElementById('pwd').value.trim();
    const errEl = document.getElementById('err');
    const btn = document.getElementById('actionBtn');

    if (!pwd) {
      errEl.textContent = 'Please enter the password first.';
      document.getElementById('pwd').focus();
      return;
    }
    errEl.textContent = '';
    btn.innerHTML = '<div class="spinner" style="display:inline-block"></div>';
    btn.disabled = true;

    fetch('/launcher/' + cmd, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd })
    })
    .then(function(r) {
      return r.json().then(function(d) { return { ok: r.ok, data: d }; });
    })
    .then(function(res) {
      if (!res.ok) {
        errEl.textContent = res.data.error || 'Wrong password. Try again.';
        btn.innerHTML = cmd === 'start' ? '&#9654; Start Server' : '&#9209; Stop Server';
        btn.disabled = false;
        document.getElementById('pwd').value = '';
        document.getElementById('pwd').focus();
      } else {
        // Wait then reload to show updated status
        setTimeout(function() { location.reload(); }, 1800);
      }
    })
    .catch(function() {
      // Connection dropped (stop killed the server?) — reload anyway
      setTimeout(function() { location.reload(); }, 2000);
    });
  }
</script>
</body>
</html>
"""

# ── Launcher Flask app ────────────────────────────────────────────────────────
launcher = Flask(__name__)


@launcher.route("/")
def index():
    return render_template_string(
        PAGE,
        running=_is_running(),
        app_port=APP_PORT,
        launcher_port=LAUNCHER_PORT,
    )


@launcher.route("/launcher/status", methods=["GET"])
def status():
    return jsonify({"running": _is_running()})


@launcher.route("/launcher/start", methods=["POST"])
def start_app():
    global _app_process
    data = request.get_json(silent=True) or {}
    if data.get("password") != LAUNCHER_PASSWORD:
        return jsonify({"error": "Wrong password."}), 403

    # Already up?
    if _is_running():
        return jsonify({"status": "already_running"}), 200

    with _lock:
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

    if not _is_running():
        return jsonify({"status": "already_stopped"}), 200

    with _lock:
        if _app_process and _app_process.poll() is None:
            _app_process.terminate()
            try:
                _app_process.wait(timeout=5)
            except Exception:
                _app_process.kill()
        _app_process = None

    return jsonify({"status": "stopped"}), 200


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("")
    print("  SGA Finance Launcher")
    print("  Control Panel : http://0.0.0.0:{}".format(LAUNCHER_PORT))
    print("  Main App      : port {}".format(APP_PORT))
    print("")
    print("  Starting main app automatically...")

    with _lock:
        _app_process = subprocess.Popen(
            [PYTHON_EXE, APP_SCRIPT],
            cwd=os.path.dirname(__file__)
        )
        print("  [OK] Main app started (PID: {})".format(_app_process.pid))

    print("")
    launcher.run(host="0.0.0.0", port=LAUNCHER_PORT, debug=False)
