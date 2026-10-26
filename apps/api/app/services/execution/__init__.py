"""Phase 4 - Restricted code execution worker.

Runs generated code in an isolated subprocess with OS resource limits.
HONESTY NOTE (spec 2.106): this is a restricted child process, NOT a secure
sandbox/VM. It limits CPU time, address space, file count and wall-clock time,
scrubs environment variables, and confines writes to a temp workspace. It does
NOT block network access or syscall-level abuse; do not run untrusted hostile
code here. That limitation is surfaced via EXECUTION_CAPABILITIES.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field

EXECUTION_CAPABILITIES = {
    "isolation": "restricted-subprocess",
    "secure_sandbox": False,
    "network_blocked": False,
    "dependency_isolation": "per-run-venv",
    "limits": ["cpu_seconds", "memory_bytes", "wall_seconds", "max_files", "max_file_bytes"],
    "note": "Not a secure sandbox; suitable only for model-generated code in this system.",
}

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FILES = 200


@dataclass
class ExecutionResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    artifact_path: str | None = None
    artifact_sha256: str | None = None


def _limits(cpu_seconds: int, memory_bytes: int, max_file_bytes: int) -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_bytes, max_file_bytes))
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
    except (ValueError, OSError):
        pass


def _failure_summary(stdout: str, stderr: str, limit: int = 1200) -> str:
    """Extract the decision-relevant lines from pytest output.

    Pytest prints the failure details long before the trailing warnings summary, so a
    plain tail of the output shows only warnings - which is exactly what blinded the
    test_repair loop. Key error/FAILED lines come first so they survive truncation to
    the 500-char error_summary stored on the task.
    """
    combined = (stdout or "") + "\n" + (stderr or "")
    lines = combined.splitlines()
    key = [l for l in lines
           if l.startswith(("E ", "E\t", "FAILED", "ERROR", "ImportError", "Traceback"))]
    parts = []
    if key:
        parts.append("\n".join(key[-12:]))
    parts.append("--- output tail ---")
    parts.append("\n".join(lines[-12:]))
    return "\n".join(parts)[-limit:]


def _sanitize_requirements(files: dict[str, str]) -> dict[str, str]:
    """Drop hallucinated packages, impossible pins and sdist-only packages.

    Models sometimes invent package names (seen: "pcrypt==3.2.0") or versions that
    were never published; pip then fails the whole install and the run dies before a
    single test runs. Installs use --only-binary :all: (source builds hit free-tier
    process limits), so sdist-only packages are unusable too. Check each requirement
    against PyPI (fail-open on network errors): unknown or wheel-less packages are
    removed, unknown versions are unpinned, each change recorded as a comment. If the
    code truly imports a removed package the test run fails with a clear ImportError
    the repair loop can fix.
    """
    reqs = files.get("requirements.txt")
    if not reqs:
        return files

    def _wheel_listing(name: str) -> tuple[bool, set[str], set[str]]:
        """(exists, versions_with_wheels, latest_version_tags) via PyPI JSON."""
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=6) as resp:
            data = json.loads(resp.read())
        wheeled = {v for v, fs in (data.get("releases") or {}).items()
                   if any(f.get("packagetype") == "bdist_wheel" for f in fs)}
        return True, wheeled, set()

    kept: list[str] = []
    changed = False
    for line in reqs.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            kept.append(line)
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.!+\-]+)", stripped)
        name = m.group(1) if m else re.split(r"[<>=!~\[ ;]", stripped, 1)[0]
        pin = m.group(2) if m else None
        try:
            _, wheeled, _ = _wheel_listing(name)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                kept.append(f"# godmode: removed {stripped} (package not on PyPI)")
                changed = True
                continue
            kept.append(line)
            continue
        except Exception:
            kept.append(line)  # fail-open: never block an install on a check outage
            continue
        if not wheeled:
            kept.append(f"# godmode: removed {stripped} (no binary wheel on PyPI; "
                        f"source builds are not supported in this environment)")
            changed = True
        elif pin and pin not in wheeled:
            kept.append(f"# godmode: unpinned {stripped} (no such version/wheel on PyPI)")
            kept.append(name)
            changed = True
        else:
            kept.append(line)
    if not changed:
        return files
    files = dict(files)
    files["requirements.txt"] = "\n".join(kept) + "\n"
    return files


def _ensure_implicit_requirements(files: dict[str, str]) -> dict[str, str]:
    """Add packages the generated code implicitly needs but the model forgot to declare.

    Currently: pydantic's EmailStr requires the email-validator package at import time;
    generated backends use EmailStr often enough that relying on the model to declare it
    makes test_repair burn repair attempts on a deterministic gap.
    """
    reqs = files.get("requirements.txt", "")
    uses_email = any(
        "EmailStr" in content
        for name, content in files.items()
        if name.endswith(".py")
    )
    if uses_email and "email-validator" not in reqs and "pydantic[email]" not in reqs:
        files = dict(files)
        files["requirements.txt"] = reqs.rstrip("\n") + "\nemail-validator\n"
    return files


class Executor:
    def __init__(self, cpu_seconds: int = 60, memory_mb: int = 512, wall_seconds: int = 120,
                 max_file_mb: int = 5):
        self.cpu_seconds = cpu_seconds
        self.memory_bytes = memory_mb * 1024 * 1024
        self.wall_seconds = wall_seconds
        self.max_file_bytes = max_file_mb * 1024 * 1024

    def _write_files(self, workspace: str, files: dict[str, str]) -> None:
        if len(files) > MAX_FILES:
            raise ValueError(f"too many files ({len(files)} > {MAX_FILES})")
        for rel, content in files.items():
            path = os.path.normpath(os.path.join(workspace, rel))
            if not path.startswith(os.path.abspath(workspace) + os.sep):
                raise ValueError(f"path escapes workspace: {rel}")
            data = content.encode()
            if len(data) > MAX_FILE_BYTES:
                raise ValueError(f"file too large: {rel}")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)

    def run(self, files: dict[str, str], command: list[str]) -> ExecutionResult:
        """Write files to a fresh workspace and run command there."""
        workspace = tempfile.mkdtemp(prefix="gmexec-")
        try:
            self._write_files(workspace, files)
            env = {"PATH": os.environ.get("PATH", ""), "HOME": workspace,
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
            start = time.monotonic()
            proc = subprocess.Popen(
                command, cwd=workspace, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
                preexec_fn=lambda: _limits(self.cpu_seconds, self.memory_bytes, self.max_file_bytes),
            )
            timed_out = False
            try:
                out, err = proc.communicate(timeout=self.wall_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                out, err = proc.communicate()
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecutionResult(command=command, exit_code=proc.returncode or 0,
                                   stdout=out[-20000:], stderr=err[-20000:],
                                   duration_ms=duration_ms, timed_out=timed_out)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def run_tests(self, files: dict[str, str], install_requirements: bool = True) -> ExecutionResult:
        """Write a generated app, install its declared requirements, run its real pytest suite.

        When the app declares requirements, they install into a per-run virtualenv
        (isolated from the API's own environment, so generated pins can never downgrade
        the service). Tooling (pytest, httpx) is installed first and the generated
        requirements second, so the generated app's pins always win. Apps without a
        requirements.txt run against the current environment (recorded in
        EXECUTION_CAPABILITIES).
        """
        has_reqs = install_requirements and "requirements.txt" in files
        if not has_reqs:
            result = self.run(files, [sys.executable, "-m", "pytest", "-q", "--tb=short", "-rf"])
            return result

        files = _ensure_implicit_requirements(files)
        files = _sanitize_requirements(files)
        venv_dir = tempfile.mkdtemp(prefix="gmvenv-")
        try:
            mk = subprocess.run([sys.executable, "-m", "venv", venv_dir],
                                capture_output=True, text=True, timeout=180)
            if mk.returncode != 0:
                return ExecutionResult(command=["python", "-m", "venv"], exit_code=mk.returncode,
                                       stdout=mk.stdout, stderr="venv creation failed: " + mk.stderr,
                                       duration_ms=0, timed_out=False)
            vpy = os.path.join(venv_dir, "bin", "python")
            tooling = Executor(cpu_seconds=240, wall_seconds=240, max_file_mb=512)
            tool = tooling.run({}, [vpy, "-m", "pip", "install", "-q",
                                    "--disable-pip-version-check", "--only-binary", ":all:",
                                    "pytest", "httpx<0.28"])
            if tool.exit_code != 0:
                return ExecutionResult(command=tool.command, exit_code=tool.exit_code,
                                       stdout=tool.stdout,
                                       stderr="test tooling install failed: " + tool.stderr,
                                       duration_ms=tool.duration_ms, timed_out=tool.timed_out)
            installer = Executor(cpu_seconds=240, wall_seconds=300, max_file_mb=512)
            dep = installer.run({"requirements.txt": files["requirements.txt"]},
                                [vpy, "-m", "pip", "install", "-q",
                                 "--disable-pip-version-check", "--only-binary", ":all:",
                                 "-r", "requirements.txt"])
            if dep.exit_code != 0:
                return ExecutionResult(command=dep.command, exit_code=dep.exit_code,
                                       stdout=dep.stdout,
                                       stderr="dependency install failed: "
                                              + _failure_summary(dep.stdout, dep.stderr),
                                       duration_ms=dep.duration_ms, timed_out=dep.timed_out)
            return self.run(files, [vpy, "-m", "pytest", "-q", "--tb=short", "-rf"])
        finally:
            shutil.rmtree(venv_dir, ignore_errors=True)

    def package(self, files: dict[str, str], out_zip: str) -> tuple[str, str]:
        """Zip the workspace files; returns (path, sha256)."""
        workspace = tempfile.mkdtemp(prefix="gmpack-")
        try:
            self._write_files(workspace, files)
            with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, names in os.walk(workspace):
                    for name in names:
                        full = os.path.join(root, name)
                        zf.write(full, os.path.relpath(full, workspace))
            digest = hashlib.sha256(open(out_zip, "rb").read()).hexdigest()
            return out_zip, digest
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
