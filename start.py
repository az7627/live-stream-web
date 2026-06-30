#!/usr/bin/env python3
"""
Start the Live Stream Web service.

Launches:
  1. FastAPI web backend  (HTTPS :443)
  2. Node-Media-Server    (RTMP :1935, internal HTTP :8001)

Press Ctrl+C to stop everything.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CERT_DIR = Path(r"C:\Users\a233d\Documents\cert")

PYTHON = sys.executable
NODE = "node"  # assumes node is on PATH

LOG_DIR = BASE_DIR / "logs"


def check_prerequisites() -> bool:
    print("🔍 Checking prerequisites…\n")

    # SSL certificates
    cert_pem = CERT_DIR / "az7627.top.pem"
    key_pem = CERT_DIR / "az7627.top.key"
    if not cert_pem.exists() or not key_pem.exists():
        print(f"SSL certificates not found in {CERT_DIR}")
        print("  Ensure az7627.top.pem and az7627.top.key exist.")
        return False
    print(f"SSL certs: {cert_pem.name} + {key_pem.name}")

    # Python packages
    try:
        import fastapi  # noqa
        print("✓ Python packages (fastapi)")
    except ImportError:
        print("✗ Missing Python packages. Run:")
        print(f"  pip install -r {BASE_DIR / 'backend' / 'requirements.txt'}")
        return False

    # Node
    try:
        subprocess.run([NODE, "--version"], capture_output=True, check=True)
        print("✓ Node.js is available")

        # Check node_modules
        nms_dir = BASE_DIR / "media-server"
        if not (nms_dir / "node_modules").exists():
            print(f"✗ Media-server dependencies not installed. Run:")
            print(f"  cd {nms_dir} && npm install")
            return False
        print("✓ Media-server dependencies installed")
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("✗ Node.js not found. Install from https://nodejs.org")
        return False

    # Data directories
    os.makedirs(BASE_DIR / "data", exist_ok=True)
    os.makedirs(BASE_DIR / "media" / "hls" / "live", exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(BASE_DIR / "media" / "hls" / "live", exist_ok=True)
    print("✓ Data directories ready")

    return True


def main():
    print("=" * 56)
    print("  🌐  Live Stream Web  🌐")
    print("=" * 56)
    print()

    if not check_prerequisites():
        sys.exit(1)

    print()

    # ── Start media server ───────────────────────────────────────────────
    media_log = open(LOG_DIR / "media-server.log", "w", encoding="utf-8")
    print(f"[Media] Starting Node-Media-Server… (log → {media_log.name})")
    media_proc = subprocess.Popen(
        [NODE, "server.js"],
        cwd=BASE_DIR / "media-server",
        stdout=media_log,
        stderr=subprocess.STDOUT,
    )

    # ── Start web backend ────────────────────────────────────────────────
    web_log = open(LOG_DIR / "backend.log", "w", encoding="utf-8")
    print(f"[Web]   Starting FastAPI on https://0.0.0.0:443 … (log → {web_log.name})")
    web_proc = subprocess.Popen(
        [
            PYTHON, "-m", "uvicorn", "main:app",
            "--host", "::",
            "--port", "443",
            "--ssl-keyfile", str(CERT_DIR / "az7627.top.key"),
            "--ssl-certfile", str(CERT_DIR / "az7627.top.pem"),
            "--log-level", "info",
        ],
        cwd=BASE_DIR / "backend",
        stdout=web_log,
        stderr=subprocess.STDOUT,
    )

    print()
    print(f"  🌍  https://localhost")
    print(f"  📡  RTMP  rtmp://localhost:1935/live")
    print()
    print("  Press Ctrl+C to stop all services.")
    print()

    # ── Monitor processes ────────────────────────────────────────────────
    try:
        while True:
            time.sleep(2)

            if media_proc.poll() is not None:
                print("[Media] Process exited unexpectedly — check logs/media-server.log")
                break
            if web_proc.poll() is not None:
                print("[Web]   Process exited unexpectedly — check logs/backend.log")
                break
    except KeyboardInterrupt:
        print("\n⏳ Shutting down…")
    finally:
        media_proc.terminate()
        web_proc.terminate()
        media_proc.wait(timeout=10)
        web_proc.wait(timeout=10)
        media_log.close()
        web_log.close()
        print("✓ All services stopped.")


if __name__ == "__main__":
    main()
