"""Workspace path confinement and the allowlisted command runner."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from app.tools.registry import ToolError

SENSITIVE_NAMES = {
    ".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519", "id_ecdsa", "credentials",
    "known_hosts", "authorized_keys", "cookies", "login data", "secrets.json",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx", ".sqlite", ".db")
SENSITIVE_DIRS = {".ssh", ".aws", ".gnupg", ".git"}
SENSITIVE_PREFIXES = (".env.",)  # .env.local, .env.production (".env.example" is allowed)


def resolve_in_workspace(workspace: Path, user_path: str) -> Path:
    """Resolve a user/LLM supplied path and refuse anything outside the workspace or sensitive."""
    if "\x00" in user_path:
        raise ToolError("invalid path")
    root = workspace.resolve()
    candidate = (root / user_path).resolve()  # absolute inputs replace root, then fail the check below
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        raise ToolError("path is outside the approved workspace") from None
    for part in rel.parts:
        low = part.lower()
        if low in SENSITIVE_DIRS:
            raise ToolError(f"access to '{part}' is not permitted")
    name = candidate.name.lower()
    if (
        name in SENSITIVE_NAMES
        or name.endswith(SENSITIVE_SUFFIXES)
        or (name.startswith(SENSITIVE_PREFIXES) and not name.endswith((".example", ".sample", ".template")))
    ):
        raise ToolError("access to sensitive files is not permitted")
    return candidate


# Fixed argv prefixes. (prefix, needs_approval). Extra args are validated separately.
ALLOWED_COMMANDS: list[tuple[tuple[str, ...], bool]] = [
    (("git", "status"), False),
    (("git", "diff"), False),
    (("git", "log"), False),
    (("python", "-m", "pytest"), True),
    (("pytest",), True),
    (("npm", "test"), True),
]
_SAFE_ARG = re.compile(r"^[\w./:=,\-\[\]@]+$")
_DENIED_FLAGS = {"-c", "-p", "--rootdir", "--confcutdir", "--pyargs", "--basetemp", "-o", "--override-ini",
                 "--ext-diff", "--output", "--exec", "--config", "-C", "--git-dir", "--work-tree"}


def match_command(argv: list[str]) -> tuple[tuple[str, ...], bool]:
    for prefix, approval in ALLOWED_COMMANDS:
        if tuple(argv[: len(prefix)]) == prefix:
            return prefix, approval
    raise ToolError("command is not on the allowlist")


def validate_command(argv: list[str]) -> bool:
    """Return True if the command needs user approval. Raises ToolError if not permitted."""
    if not argv or len(argv) > 12:
        raise ToolError("invalid command")
    prefix, approval = match_command(argv)
    for arg in argv[len(prefix):]:
        flag = arg.split("=", 1)[0]
        if flag in _DENIED_FLAGS:
            raise ToolError(f"argument '{flag}' is not permitted")
        if not _SAFE_ARG.match(arg) or ".." in arg or arg.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", arg):
            raise ToolError(f"argument '{arg}' is not permitted")
    return approval


def _clean_env() -> dict[str, str]:
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "PATHEXT", "COMSPEC")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CI"] = "1"
    return env


def run_allowlisted(argv: list[str], cwd: Path, timeout: int, cancel: threading.Event, max_chars: int) -> dict:
    validate_command(argv)
    exe_name = argv[0]
    exe = sys.executable if exe_name == "python" else shutil.which(exe_name)
    if not exe:
        raise ToolError(f"'{exe_name}' is not installed on this machine")
    cmd = [exe, *argv[1:]]
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=_clean_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, errors="replace", shell=False,
    )
    out_chunks: list[str] = []
    reader = threading.Thread(target=lambda: out_chunks.append(proc.stdout.read()), daemon=True)
    reader.start()
    timed_out = cancelled = False
    while proc.poll() is None:
        if cancel.is_set():
            cancelled = True
        elif time.monotonic() - started > timeout:
            timed_out = True
        if cancelled or timed_out:
            proc.kill()
            break
        time.sleep(0.05)
    proc.wait()
    reader.join(timeout=2)
    out = "".join(out_chunks)
    truncated = len(out) > max_chars
    return {
        "command": argv,
        "exit_code": proc.returncode,
        "output": out[:max_chars],
        "truncated": truncated,
        "timed_out": timed_out,
        "cancelled": cancelled,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
