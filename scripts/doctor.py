"""kubectl/server version-skew check used by `task doctor`.

Supported skew (Kubernetes policy): kubectl within +/-1 minor of the kube-apiserver.

Why a script and not a one-liner: on Windows two lookups disagree.
  - shutil.which / Get-Command follow the PATH           -> what you THINK runs
  - CreateProcess("kubectl") searches the application dir, System32 and C:\\Windows first,
    then the PATH                                        -> what programs ACTUALLY run
A kubectl.exe left in C:\\Windows is invisible to `Get-Command` yet used by every Python/Go
tool spawning "kubectl". We report both and fail on the one that runs.

Also checks what the lab needs before `task up`: tools on PATH, Docker running with enough
memory, host ports free, Ollama reachable (only a warning: the fake overlay does not need it).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

# Tool -> why the lab needs it. Versions are printed, not enforced (except kubectl skew).
TOOLS = {
    "docker": "runs the k3d nodes and the test backends",
    "k3d": "creates the cluster",
    "kubectl": "talks to the cluster",
    "helm": "installs the platform charts",
    "uv": "Python 3.14 and the virtualenv",
}
PORTS = {8080: "Gateway (all UIs)", 4318: "OTLP/HTTP to the collector", 5001: "image registry"}
MIN_DOCKER_GB = 9.5          # 3 GB + 5 GB node caps, plus Docker's own overhead
problems: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def warn(msg: str) -> None:
    print(f"  warn  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    problems.append(msg)


def run(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def minor(v: str) -> int:
    return int(v.rstrip("+"))


def check_tools() -> None:
    print("tools")
    for tool, why in TOOLS.items():
        if shutil.which(tool):
            ok(f"{tool:<8} {shutil.which(tool)}")
        else:
            fail(f"{tool} not found on PATH ({why})")


def check_docker() -> bool:
    print("docker")
    if not shutil.which("docker"):
        return False
    r = run("docker", "info", "--format", "{{json .}}")
    if r.returncode != 0:
        fail("docker is installed but not running (start Docker Desktop)")
        return False
    gb = json.loads(r.stdout).get("MemTotal", 0) / 2**30
    if gb < MIN_DOCKER_GB:
        fail(f"Docker VM has {gb:.1f} GB, the cluster needs about 10 GB "
             "(Docker Desktop > Settings > Resources, or memory= in %USERPROFILE%\\.wslconfig)")
    else:
        ok(f"Docker VM memory {gb:.1f} GB")
    return True


def cluster_running() -> bool:
    if not shutil.which("k3d"):
        return False
    r = run("k3d", "cluster", "list", "-o", "json")
    clusters = json.loads(r.stdout or "[]") if r.returncode == 0 else []
    return any(c.get("name") == "obslab" and c.get("serversRunning", 0) > 0 for c in clusters)


def check_ports(cluster: bool) -> None:
    print("ports")
    if cluster:
        ok("cluster obslab is running: ports 8080/4318/5001 are its own")
        return
    for port, what in PORTS.items():
        with socket.socket() as s:
            busy = s.connect_ex(("127.0.0.1", port)) == 0
        if busy:
            fail(f"127.0.0.1:{port} is already in use ({what}); stop what listens there "
                 "(docker compose down, another cluster...)")
        else:
            ok(f"{port} free ({what})")


def check_ollama() -> None:
    print("ollama (optional: the fake overlay runs without it)")
    url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=3) as r:
            models = {m["name"].split(":")[0] for m in json.loads(r.read())["models"]}
    except Exception:
        warn(f"Ollama not reachable at {url}: use `task up OVERLAY=fake`, or install Ollama")
        return
    for model in ("llama3.2", "nomic-embed-text"):
        if model in models:
            ok(f"model {model}")
        else:
            warn(f"model {model} missing: ollama pull {model}")


def check_kubectl_skew() -> None:
    print("kubectl")
    if not shutil.which("kubectl"):
        return
    raw = run("kubectl", "version", "-o", "json")
    try:
        info = json.loads(raw.stdout)
    except json.JSONDecodeError:
        fail(raw.stderr.strip() or "kubectl version returned no JSON")
        return
    client = minor(info["clientVersion"]["minor"])
    ok(f"on PATH : {shutil.which('kubectl')}")
    ok(f"spawned : client 1.{client} ({info['clientVersion']['gitVersion']})")

    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        for p in (windir / "System32" / "kubectl.exe", windir / "kubectl.exe"):
            if p.exists():
                warn(f"{p} shadows the PATH for spawned processes. Remove it from an "
                     f"elevated prompt: Remove-Item '{p}'")

    server = info.get("serverVersion")
    if not server:
        ok("server  : not running, skew not checked")
        return
    srv = minor(server["minor"])
    ok(f"server  : 1.{srv} ({server['gitVersion']})")
    if abs(client - srv) > 1:
        fail(f"kubectl/server skew is {abs(client - srv)} minors (supported: 1). Upgrade the lagging side")


def main() -> int:
    check_tools()
    if check_docker():
        check_ports(cluster_running())
    check_ollama()
    check_kubectl_skew()
    if problems:
        print(f"\n{len(problems)} problem(s) to fix before `task up`.")
        return 1
    print("\nAll good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
