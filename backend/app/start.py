
import os
import signal
import subprocess
import sys
import time


processes = []
stop_requested = False


def handle_shutdown(signum, frame):
    global stop_requested
    stop_requested = True


def stop_processes():
    for process in processes:
        if process.poll() is None:
            process.terminate()

    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    global stop_requested

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    port = os.environ.get("PORT", "8000")

    worker = subprocess.Popen([
        sys.executable,
        "-m",
        "backend.app.workers.run",
    ])
    processes.append(worker)

    web = subprocess.Popen([
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host", "0.0.0.0",
        "--port", port,
        "--proxy-headers",
    ])
    processes.append(web)

    print("Started LUCENT worker and API server.", flush=True)

    exit_code = 0

    try:
        while not stop_requested:
            worker_code = worker.poll()
            web_code = web.poll()

            if worker_code is not None:
                print(
                    f"Background worker exited with code {worker_code}.",
                    flush=True,
                )
                exit_code = worker_code if worker_code != 0 else 1
                break

            if web_code is not None:
                print(
                    f"API server exited with code {web_code}.",
                    flush=True,
                )
                exit_code = web_code if web_code != 0 else 1
                break

            time.sleep(1)

    finally:
        stop_processes()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
