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
import sys
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
    "dependency_isolation": False,
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

        Dependencies install into the current (dedicated) environment; honest limitation:
        no per-run dependency isolation. Recorded in EXECUTION_CAPABILITIES.
        """
        if install_requirements and "requirements.txt" in files:
            installer = Executor(cpu_seconds=240, wall_seconds=300, max_file_mb=512)
            dep = installer.run(files, [sys.executable, "-m", "pip", "install", "-q",
                                        "--disable-pip-version-check", "-r", "requirements.txt"])
            if dep.exit_code != 0:
                return ExecutionResult(command=dep.command, exit_code=dep.exit_code,
                                       stdout=dep.stdout, stderr="dependency install failed: " + dep.stderr,
                                       duration_ms=dep.duration_ms, timed_out=dep.timed_out)
        return self.run(files, [sys.executable, "-m", "pytest", "-q", "--tb=short"])

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
