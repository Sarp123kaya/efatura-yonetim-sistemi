#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Start the local web panel and worker, then open the browser."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOST = os.getenv("WEB_HOST", "127.0.0.1")
PORT = int(os.getenv("WEB_PORT", "8000"))
URL = f"http://{HOST}:{PORT}"


def is_web_ready() -> bool:
    try:
        with urlopen(f"{URL}/health", timeout=1.5) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def start_process(command: list[str], log_name: str) -> subprocess.Popen:
    log_dir = PROJECT_ROOT / "data" / "logs" / "web_panel"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_name
    log_file = log_path.open("a", encoding="utf-8")
    log_file.write(f"\n\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_file.flush()
    return subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> int:
    processes: list[subprocess.Popen] = []
    try:
        if not is_web_ready():
            print("Web panel başlatılıyor...")
            processes.append(
                start_process(
                    [sys.executable, "-m", "flask", "--app", "backend.web.app", "run", "--host", HOST, "--port", str(PORT)],
                    "server.log",
                )
            )
        else:
            print("Web panel zaten çalışıyor.")

        print("Worker başlatılıyor...")
        processes.append(start_process([sys.executable, "scripts/run_web_worker.py"], "worker.log"))

        for _ in range(30):
            if is_web_ready():
                break
            time.sleep(0.5)
        else:
            print("Web panel zamanında açılmadı. Log: data/logs/web_panel/server.log")
            return 1

        print(f"Tarayıcı açılıyor: {URL}")
        webbrowser.open(URL)
        print("Panel hazır. Bu pencere açık kaldığı sürece worker çalışır.")
        print("Kapatmak için Ctrl+C kullanın.")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nKapatılıyor...")
    finally:
        for process in processes:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
        time.sleep(1)
        for process in processes:
            if process.poll() is None:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
