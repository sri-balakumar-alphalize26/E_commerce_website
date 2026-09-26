# -*- coding: utf-8 -*-
"""Auto-provision the Baileys WhatsApp helper: copy bundled files to a runtime dir, npm install,
and register the OdooWABaileys auto-start task. Idempotent + non-disruptive."""
import os
import json
import shutil
import logging
import platform
import subprocess
import tempfile
import threading
import urllib.request

_logger = logging.getLogger(__name__)

TASK = "OdooWABaileys"
STATUS_URL = "http://127.0.0.1:8788/status"
NODE_INDEX = "https://nodejs.org/dist/index.json"
# Pin auto-installed Node to this LTS line for reproducible installs across machines
# (still picks up patch releases within the line; falls back to newest LTS if absent).
NODE_MAJOR = "22"


def _runtime_dir():
    base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return os.path.join(base, "odoo_wa_baileys")


def _find_node():
    cand = shutil.which("node")
    if cand:
        return cand
    for p in (r"C:\Program Files\nodejs-nvm\nodejs\node.exe",
              r"C:\Program Files\nodejs\node.exe",
              r"C:\Program Files (x86)\nodejs\node.exe"):
        if os.path.exists(p):
            return p
    return None


def _find_npm(node):
    cand = shutil.which("npm.cmd") or shutil.which("npm")
    if cand:
        return cand
    if node:
        c = os.path.join(os.path.dirname(node), "npm.cmd")
        if os.path.exists(c):
            return c
    return None


def _node_arch():
    """Pick the Node MSI arch for this machine."""
    m = (platform.machine() or "").lower()
    if "arm64" in m or "aarch64" in m:
        return "arm64"
    if m in ("x86", "i386", "i686") or (platform.architecture()[0] == "32bit"):
        return "x86"
    return "x64"


def _download_node_msi():
    """Resolve the latest Node LTS and download its Windows MSI. Returns path or None."""
    try:
        with urllib.request.urlopen(NODE_INDEX, timeout=30) as r:
            data = json.loads(r.read().decode())
        # Prefer the newest LTS within the pinned major line (reproducible); fall
        # back to the newest LTS overall so installs never break if the line ages out.
        prefix = "v%s." % NODE_MAJOR
        lts = next((v["version"] for v in data
                    if v.get("lts") and v["version"].startswith(prefix)), None)
        if not lts:
            lts = next((v["version"] for v in data if v.get("lts")), None)
        if not lts:
            return None
        arch = _node_arch()
        url = "https://nodejs.org/dist/%s/node-%s-%s.msi" % (lts, lts, arch)
        dst = os.path.join(tempfile.gettempdir(), "node-%s-%s.msi" % (lts, arch))
        if not os.path.exists(dst) or os.path.getsize(dst) < 1024 * 1024:
            _logger.info("Baileys: downloading Node %s (%s) from %s", lts, arch, url)
            urllib.request.urlretrieve(url, dst)
        return dst
    except Exception as e:
        _logger.error("Baileys: Node download failed (offline?): %s", e)
        return None


def _ensure_node():
    """Return a Node executable path, auto-installing Node LTS if it is missing.

    Runs during the module post-init/provision, which executes as the Odoo service
    account (LocalSystem in the bundled Windows install) — so the silent MSI install
    needs no UAC prompt. If Odoo runs as a non-admin user, the machine install will
    fail and we fall back to asking the operator to install Node manually.
    """
    node = _find_node()
    if node:
        return node
    _logger.info("Baileys: Node.js not found — attempting silent auto-install of Node LTS...")
    msi = _download_node_msi()
    if not msi:
        return None
    try:
        subprocess.run(["msiexec", "/i", msi, "/qn", "/norestart"],
                       capture_output=True, timeout=600)
    except Exception as e:
        _logger.error("Baileys: Node silent install failed (need admin/SYSTEM?): %s", e)
        return None
    node = _find_node()  # re-check the standard install paths
    if node:
        _logger.info("Baileys: Node.js auto-installed at %s", node)
    else:
        _logger.error("Baileys: Node install ran but node.exe still not found.")
    return node


def _status_ok():
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=4) as r:
            return bool(json.loads(r.read().decode()).get("ok"))
    except Exception:
        return False


def _task_exists():
    try:
        return subprocess.run(["schtasks", "/Query", "/TN", TASK],
                              capture_output=True).returncode == 0
    except Exception:
        return False


def ensure_running():
    """Start the helper task if the service is not answering (self-heal at first use)."""
    if _status_ok():
        return True
    if _task_exists():
        try:
            subprocess.run(["schtasks", "/Run", "/TN", TASK], capture_output=True, timeout=20)
            return True
        except Exception as e:
            _logger.warning("Baileys: could not start task: %s", e)
    return False


def provision_baileys(module_dir, force=False):
    """Set up the Baileys helper. Skips quietly if already running (won't disturb a live session)."""
    if not force and _task_exists():
        # Already provisioned -> never re-provision on a live machine; just ensure it is running.
        ensure_running()
        _logger.info("Baileys: already provisioned; ensured running (no re-provision).")
        return True

    runtime = _runtime_dir()
    try:
        os.makedirs(runtime, exist_ok=True)
    except Exception as e:
        _logger.error("Baileys: cannot create %s: %s", runtime, e)
        return False

    src = os.path.join(module_dir, "baileys")
    for f in ("server.js", "package.json"):
        try:
            shutil.copy2(os.path.join(src, f), os.path.join(runtime, f))
        except Exception as e:
            _logger.error("Baileys: copy %s failed: %s", f, e)

    # migrate an existing login so no re-scan is needed
    dst_auth = os.path.join(runtime, "auth")
    if not os.path.exists(os.path.join(dst_auth, "creds.json")):
        for old in (r"C:\Users\sriba\wa_baileys\auth",):
            if os.path.exists(os.path.join(old, "creds.json")):
                try:
                    shutil.copytree(old, dst_auth, dirs_exist_ok=True)
                    _logger.info("Baileys: migrated existing login from %s", old)
                except Exception as e:
                    _logger.warning("Baileys: auth migrate failed: %s", e)
                break

    node = _ensure_node()
    if not node:
        _logger.error("Baileys: Node.js not found and auto-install failed (offline, or Odoo not "
                      "running as admin/SYSTEM). Install Node.js LTS, then upgrade the module.")
        return False
    npm = _find_npm(node)

    if npm and not os.path.isdir(os.path.join(runtime, "node_modules", "@whiskeysockets", "baileys")):
        _logger.info("Baileys: running npm install (first-time, ~1 min)...")
        # Ensure the freshly-installed Node dir is on PATH for npm's child node calls.
        env = dict(os.environ)
        env["PATH"] = os.path.dirname(node) + os.pathsep + env.get("PATH", "")
        try:
            subprocess.run([npm, "install", "--no-audit", "--no-fund"],
                           cwd=runtime, capture_output=True, timeout=600, env=env)
        except Exception as e:
            _logger.error("Baileys: npm install failed: %s", e)
            return False

    tr = '"%s" "%s"' % (node, os.path.join(runtime, "server.js"))
    try:
        subprocess.run(["schtasks", "/Create", "/TN", TASK, "/TR", tr,
                        "/SC", "ONSTART", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F"],
                       capture_output=True, timeout=30)
        subprocess.run(["schtasks", "/Run", "/TN", TASK], capture_output=True, timeout=20)
        _logger.info("Baileys: helper provisioned at %s and task '%s' started.", runtime, TASK)
    except Exception as e:
        _logger.error("Baileys: task setup failed: %s", e)
        return False
    return True


# --- Background / self-heal helpers -------------------------------------------
_provision_lock = threading.Lock()
_provisioning = {"running": False}


def _module_dir():
    """Module root (…/pos_loyalty_card); this file lives in …/models/."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def provision_in_background(force=False):
    """Run provisioning in a daemon thread (one at a time) so callers never block.
    Used by the install hook (fast install) and the health-check cron (self-heal)."""
    with _provision_lock:
        if _provisioning["running"]:
            return
        _provisioning["running"] = True

    def _run():
        try:
            provision_baileys(_module_dir(), force=force)
        except Exception as e:
            _logger.warning("Baileys: background provision failed: %s", e)
        finally:
            _provisioning["running"] = False

    threading.Thread(target=_run, name="OdooWABaileysProvision", daemon=True).start()
