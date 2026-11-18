"""Development-only file watcher for the background worker."""

import signal
import subprocess
import sys
from pathlib import Path
from threading import Event

from watchfiles import watch

API_ROOT = Path(__file__).resolve().parent.parent


def start_worker() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "app.worker"], cwd=API_ROOT)


def stop_worker(worker: subprocess.Popen) -> None:
    if worker.poll() is not None:
        return
    worker.send_signal(signal.SIGINT)
    try:
        worker.wait(timeout=5)
    except subprocess.TimeoutExpired:
        worker.kill()
        worker.wait()


def main() -> int:
    stopping = Event()

    def request_stop(signum, frame):
        stopping.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker = start_worker()
    try:
        for changes in watch(
            API_ROOT / "app", stop_event=stopping, rust_timeout=500, yield_on_timeout=True
        ):
            status = worker.poll()
            if status is not None:
                return status
            if changes and not stopping.is_set():
                print("[worker reload] API files changed; restarting worker", flush=True)
                stop_worker(worker)
                if not stopping.is_set():
                    worker = start_worker()
    finally:
        stop_worker(worker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
