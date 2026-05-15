#!/usr/bin/env python3

import argparse
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEFAULT_BATCH_SIZE = 25
DEFAULT_OLLAMA_MODEL = "neural-chat"
OLLAMA_URL = "http://127.0.0.1:11434/"
REPORT_MODES = ("weekly", "ai_radar", "cloud_vendor_radar")


def info(message):
    print(f"[info] {message}")


def warn(message):
    print(f"[warn] {message}")


def fail(message, exit_code=1):
    print(f"[error] {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def load_env_file():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return False

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
    return True


def run_command(command, *, capture_output=False, env=None):
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=capture_output,
        env=env,
        check=False,
    )


def ensure_python_requirements(python_bin):
    try:
        importlib.import_module("psycopg")
        info("Python dependency check passed: psycopg is available")
        return
    except ModuleNotFoundError:
        info("Installing Python dependencies from requirements.txt")

    result = run_command([python_bin, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    if result.returncode != 0:
        fail("Failed to install Python requirements")

    try:
        importlib.import_module("psycopg")
    except ModuleNotFoundError as exc:
        fail(f"psycopg is still unavailable after installation: {exc}")


def ensure_database_connection():
    sys.path.insert(0, str(SRC))
    try:
        from db import get_conn

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except Exception as exc:
        fail(f"PostgreSQL connectivity check failed: {exc}")
    finally:
        if str(SRC) in sys.path:
            sys.path.remove(str(SRC))

    info("PostgreSQL connectivity check passed")


def ollama_server_responding():
    request = urllib.request.Request(OLLAMA_URL, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def ensure_ollama_binary():
    if shutil.which("ollama") is None:
        fail("Ollama executable was not found on PATH")
    info("Ollama CLI is available")


def ensure_ollama_server():
    if ollama_server_responding():
        info("Ollama server is already running")
        return False

    info("Starting Ollama server in the background")
    subprocess.Popen(
        ["ollama", "serve"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.time() + 30
    while time.time() < deadline:
        if ollama_server_responding():
            info("Ollama server started successfully")
            return True
        time.sleep(1)

    fail("Ollama server did not become ready within 30 seconds")


def ensure_ollama_model(model_name):
    result = run_command(["ollama", "list"], capture_output=True)
    if result.returncode != 0:
        fail(f"Unable to inspect Ollama models: {result.stderr.strip()}")

    if model_name in result.stdout:
        info(f"Ollama model is available: {model_name}")
        return False

    info(f"Pulling missing Ollama model: {model_name}")
    pull_result = run_command(["ollama", "pull", model_name])
    if pull_result.returncode != 0:
        fail(f"Unable to pull Ollama model '{model_name}'")

    return True


def prompt_batch_size(default_value):
    if not sys.stdin.isatty():
        info(f"No interactive terminal detected; using default batch size {default_value}")
        return default_value

    raw = input(f"Batch size for each mode [{default_value}]: ").strip()
    if not raw:
        return default_value

    try:
        batch_size = int(raw)
    except ValueError:
        fail("Batch size must be an integer")

    if batch_size < 0:
        fail("Batch size must be zero or greater")
    return batch_size


def build_risk_advice(batch_size, env_loaded, server_started, model_pulled):
    risks = []
    if not env_loaded:
        risks.append(
            "No .env file was found. The run will rely on existing shell variables or PostgreSQL peer auth defaults."
        )
    if server_started:
        risks.append(
            "Ollama had to be started now. The first live request will be slower while the model warms up."
        )
    if model_pulled:
        risks.append(
            "The Ollama model was downloaded during this run. Disk use and first-run latency will be higher than normal."
        )
    if batch_size == 0:
        risks.append(
            "Batch size 0 means no limit. That can process the full backlog and may take a long time on local hardware."
        )
    elif batch_size > 50:
        risks.append(
            "Large batches can increase runtime and expose more live-model JSON formatting misses before fallback logic recovers."
        )
    elif batch_size > 25:
        risks.append(
            "This batch is larger than the recent validated smoke runs. Expect a longer pass and more GPU/model churn."
        )
    return risks


def run_report_mode(mode, batch_size, model_name):
    info(f"Running report mode: {mode}")
    env = os.environ.copy()
    env["USE_OLLAMA"] = "true"
    env["REPORT_MODE"] = mode
    env["MAX_CLASSIFICATIONS_PER_RUN"] = str(batch_size)
    env.setdefault("OLLAMA_MODEL", model_name)

    result = run_command([sys.executable, str(SRC / "main.py")], env=env)
    if result.returncode != 0:
        fail(f"Report mode '{mode}' failed with exit code {result.returncode}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check runtime dependencies and run weekly, AI radar, and cloud vendor reports."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Maximum classifications per mode. If omitted, the script prompts when interactive.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        help="Ollama model name to use. Default: neural-chat",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.batch_size is not None and args.batch_size < 0:
        fail("Batch size must be zero or greater")

    os.environ.setdefault("PYTHONPATH", str(SRC))
    env_loaded = load_env_file()
    ensure_python_requirements(sys.executable)
    ensure_database_connection()
    ensure_ollama_binary()
    server_started = ensure_ollama_server()
    model_pulled = ensure_ollama_model(args.model)

    batch_size = args.batch_size if args.batch_size is not None else prompt_batch_size(DEFAULT_BATCH_SIZE)
    risk_advice = build_risk_advice(batch_size, env_loaded, server_started, model_pulled)
    if risk_advice:
        print("\nRisk advice:")
        for item in risk_advice:
            print(f"- {item}")
        print()

    for mode in REPORT_MODES:
        run_report_mode(mode, batch_size, args.model)

    print("\nCompleted weekly, ai_radar, and cloud_vendor_radar runs.")


if __name__ == "__main__":
    main()