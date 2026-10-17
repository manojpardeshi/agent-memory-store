"""Kaggle GPU runner: Supermemory Local on single LongMemEval-S questions, pinned to the M2 setup.

Generated into a single kernel script by build_kernel.py, which embeds the MemoryBench patch, the
provider file, the ingest/search script, and the question list. Everything runs on the Kaggle
machine: Ollama on the GPU for extraction, Supermemory's own local embeddings, no hosted model,
no paid API, no secrets. Results land in /kaggle/working/out.
"""

import base64
import hashlib
import json
import os
import queue
import threading
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

PINS = {
    "memorybench_repo": "https://github.com/supermemoryai/memorybench.git",
    "memorybench_commit": "118209a746d97d0d85e5a7234267f0b6962857e9",
    "bun_version": "1.4.2",
    "ollama_version": "0.32.1",
    "model": "qwen2.5:7b",
    "model_digest": "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e",
    "supermemory_cli": "supermemory@5.0.1",
    "supermemory_server_version": "0.0.8",
    "supermemory_server_sha256_linux_x64": (
        "87f32433d0179be80bb9d8a1bafbac65af4128324342a27ecb8bd1a77b5506f3"
    ),
    "dataset_url": (
        "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/"
        "longmemeval_s_cleaned.json"
    ),
    "dataset_sha256": "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442",
}
QUESTIONS = __QUESTIONS__
RUN_PREFIX = __RUN_PREFIX__
FILES = __FILES__  # relative path -> base64 content
QUESTION_TIMEOUT_S = 3 * 3600
WORKERS = 2  # one Ollama + Supermemory pair per Tesla T4
DEADLINE = time.time() + 11.5 * 3600  # Kaggle sessions end at 12 hours

WORK = Path("/kaggle/working")
OUT = WORK / "out"
HOME = Path.home()
BENCH = Path("/kaggle/tmp/memorybench") if Path("/kaggle/tmp").exists() else HOME / "memorybench"
LOG = OUT / "run.log"
TMP = Path("/kaggle/tmp") if Path("/kaggle/tmp").exists() else HOME / "sm-tmp"


def log(message: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {message}"
    print(line, flush=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def sh(command: str, *, cwd: Path | None = None, env: dict | None = None, check: bool = True):
    log(f"$ {command[:200]}")
    result = subprocess.run(
        command, shell=True, cwd=cwd, env=env, text=True, capture_output=True, executable="/bin/bash"
    )
    tail = (result.stdout + result.stderr)[-2000:]
    if tail.strip():
        log(tail.strip())
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {command[:120]}")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wait_port(port: int, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(2)
    return False


def setup() -> dict:
    sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv", check=False)
    # Ollama: the official installer needs zstd to unpack; without systemd it installs the
    # binary only.
    sh("apt-get install -y -qq zstd >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq zstd)")
    sh(f"curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION={PINS['ollama_version']} sh")
    for gpu in range(WORKERS):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), OLLAMA_HOST=f"127.0.0.1:{11434 + gpu}")
        handle = (OUT / f"ollama-{gpu}.log").open("w")
        subprocess.Popen(["ollama", "serve"], env=env, stdout=handle, stderr=subprocess.STDOUT)
    for gpu in range(WORKERS):
        if not wait_port(11434 + gpu, 120):
            raise RuntimeError(f"ollama on GPU {gpu} did not start")
    sh(f"ollama pull {PINS['model']}")
    tags = json.loads(urllib.request.urlopen("http://127.0.0.1:11434/api/tags").read())
    digest = next(m["digest"] for m in tags["models"] if m["name"] == PINS["model"])
    if digest != PINS["model_digest"]:
        raise RuntimeError(f"model digest {digest} does not match the M2's")
    Path("Modelfile").write_text(
        f"FROM {PINS['model']}\nPARAMETER num_ctx 16384\nPARAMETER temperature 0\n"
    )
    sh("ollama create qwen2.5-7b-16k -f Modelfile")
    # Warm the model on each GPU so the first extraction does not pay the load time.
    for gpu in range(WORKERS):
        sh(
            f"curl -s http://127.0.0.1:{11434 + gpu}/api/generate "
            "-d '{\"model\":\"qwen2.5-7b-16k\",\"prompt\":\"ok\",\"stream\":false}' | head -c 120"
        )
        sh(f"OLLAMA_HOST=127.0.0.1:{11434 + gpu} ollama ps", check=False)

    sh(f"curl -fsSL https://bun.sh/install | bash -s bun-v{PINS['bun_version']}")
    os.environ["PATH"] = f"{HOME}/.bun/bin:{os.environ['PATH']}"

    if BENCH.exists():
        shutil.rmtree(BENCH)
    sh(f"git clone -q {PINS['memorybench_repo']} {BENCH}")
    sh(f"git checkout -q {PINS['memorybench_commit']}", cwd=BENCH)
    for relative, encoded in FILES.items():
        target = WORK / "embedded" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(encoded))
    sh(f"git apply {WORK}/embedded/patches/memorybench-local.patch", cwd=BENCH)
    (BENCH / "src/providers/llm-memory-store").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        WORK / "embedded/patches/llm-memory-store-provider/index.ts",
        BENCH / "src/providers/llm-memory-store/index.ts",
    )
    (BENCH / "scripts").mkdir(exist_ok=True)
    shutil.copy(
        WORK / "embedded/scripts/hosted-search-manifest.ts",
        BENCH / "scripts/hosted-search-manifest.ts",
    )
    sh("bun install --frozen-lockfile", cwd=BENCH)

    dataset_dir = BENCH / "data/benchmarks/longmemeval/datasets"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset = dataset_dir / "longmemeval_s_cleaned.json"
    urllib.request.urlretrieve(PINS["dataset_url"], dataset)
    if sha256(dataset) != PINS["dataset_sha256"]:
        raise RuntimeError("dataset checksum mismatch")
    for worker in range(WORKERS):
        target = Path(f"{BENCH}-{worker}")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(BENCH, target, symlinks=True)

    sh(
        f"bunx {PINS['supermemory_cli']} local install "
        f"--version {PINS['supermemory_server_version']} </dev/null"
    )
    server = HOME / ".supermemory/bin/supermemory-server"
    if sha256(server) != PINS["supermemory_server_sha256_linux_x64"]:
        raise RuntimeError("supermemory-server checksum mismatch")
    return {"server": str(server)}


def start_server(server: str, data_dir: Path, worker: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(
        {
            "SUPERMEMORY_DATA_DIR": str(data_dir),
            "SUPERMEMORY_HOST": "127.0.0.1",
            "SUPERMEMORY_DISABLE_TELEMETRY": "1",
            "PORT": str(6767 + worker),
            "OPENAI_BASE_URL": f"http://127.0.0.1:{11434 + worker}/v1",
            "OPENAI_API_KEY": "ollama",
            "OPENAI_MODEL": "qwen2.5-7b-16k",
        }
    )
    handle = (OUT / f"server-{worker}.raw.log").open("a")
    process = subprocess.Popen(
        [server], env=env, stdout=handle, stderr=subprocess.STDOUT, cwd=str(data_dir.parent)
    )
    if not wait_port(6767 + worker, 240):
        process.kill()
        raise RuntimeError(f"supermemory server {worker} did not start")
    return process


def stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(30)


def attempt_question(qid: str, server: str, worker: int, attempt: int) -> dict:
    bench = Path(f"{BENCH}-{worker}")
    data_dir = TMP / f"sm-{worker}-{qid}-{attempt}"
    data_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{RUN_PREFIX}-{qid}"
    manifest = bench / "manifests" / f"{qid}.json"
    manifest.parent.mkdir(exist_ok=True)
    manifest.write_text(json.dumps({"question_ids": [qid]}))
    remaining = DEADLINE - time.time() - 600
    timeout = max(600, min(QUESTION_TIMEOUT_S, remaining))
    summary = {"qid": qid, "worker": worker, "attempt": attempt, "gpu": f"Tesla T4 #{worker}"}
    process = start_server(server, data_dir, worker)
    started = time.time()
    try:
        env = dict(os.environ)
        env["SUPERMEMORY_BASE_URL"] = f"http://127.0.0.1:{6767 + worker}"
        env["SUPERMEMORY_API_KEY"] = (data_dir / "api-key").read_text().strip()
        args = ["bun", "scripts/hosted-search-manifest.ts", "supermemory", run_id, str(manifest), "1"]
        if attempt > 1:
            args.append("--force")
        try:
            harness = subprocess.run(
                args, cwd=bench, env=env, text=True, capture_output=True, timeout=timeout
            )
            (OUT / f"{run_id}.attempt{attempt}.harness.log").write_text(
                (harness.stdout + harness.stderr)[-20000:]
            )
            summary["outcome"] = "done" if harness.returncode == 0 else f"exit {harness.returncode}"
        except subprocess.TimeoutExpired:
            summary["outcome"] = "timeout"
        if process.poll() is not None:
            summary["outcome"] += " (server died)"
    finally:
        summary["seconds"] = round(time.time() - started)
        stop(process)
    run_dir = bench / "data/runs" / run_id
    if (run_dir / "checkpoint.json").exists():
        shutil.copytree(run_dir, OUT / run_id, dirs_exist_ok=True)
        phases = json.loads((run_dir / "checkpoint.json").read_text())["questions"][qid]["phases"]
        indexing = phases.get("indexing", {})
        summary.update(
            {
                "indexed_ok": len(indexing.get("completedIds") or []),
                "indexed_failed": len(indexing.get("failedIds") or []),
                "search_status": phases.get("search", {}).get("status"),
                "search_results": len(phases.get("search", {}).get("results") or []),
            }
        )
    log(f"worker {worker} question {qid} attempt {attempt}: {summary}")
    return summary


RESULTS: dict = {"pins": PINS, "runner": "kaggle-gpu-2xT4", "attempts": []}
LOCK = threading.Lock()


def save() -> None:
    with LOCK:
        (OUT / "summary.json").write_text(json.dumps(RESULTS, indent=2))


def worker_loop(worker: int, server: str, todo: "queue.Queue[str]") -> None:
    while True:
        try:
            qid = todo.get_nowait()
        except queue.Empty:
            return
        if time.time() > DEADLINE - 3600:
            log(f"worker {worker}: stopping, too close to the session limit; {qid} not started")
            with LOCK:
                RESULTS.setdefault("not_started", []).append(qid)
            save()
            continue
        for attempt in (1, 2):
            try:
                summary = attempt_question(qid, server, worker, attempt)
            except Exception as error:  # noqa: BLE001
                summary = {"qid": qid, "worker": worker, "attempt": attempt, "outcome": repr(error)}
                log(f"worker {worker} question {qid} attempt {attempt} error: {error!r}")
            with LOCK:
                RESULTS["attempts"].append(summary)
            save()
            if summary.get("search_status") == "completed":
                break


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        info = setup()
        todo: "queue.Queue[str]" = queue.Queue()
        for qid in QUESTIONS:
            todo.put(qid)
        threads = [
            threading.Thread(target=worker_loop, args=(w, info["server"], todo))
            for w in range(WORKERS)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    except Exception as error:  # record and keep outputs
        RESULTS["error"] = repr(error)
        log(f"ERROR {error!r}")
    finally:
        import re

        for raw in OUT.glob("server-*.raw.log"):
            text = re.sub(r"sm_[A-Za-z0-9_-]+", "sm_<redacted>", raw.read_text(errors="replace"))
            raw.with_name(raw.name.replace(".raw", "")).write_text(text)
            raw.unlink()
        save()
        log("finished")


main()
