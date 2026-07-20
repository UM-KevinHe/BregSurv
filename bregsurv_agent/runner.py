"""R subprocess bridge.

Mirror of ``mcp/server.py``'s ``_find_rscript`` and ``_run_r`` — kept here
so ``bregsurv_agent`` does not depend on the ``mcp`` library (which
requires Python >= 3.10). Both files implement the same R-bridge logic;
keep them in sync.

Invariants (do NOT change without re-verifying against a real MCP client):
  1. ``subprocess.run(..., stdin=subprocess.DEVNULL)`` on every Rscript
     call. Without DEVNULL, Rscript can inherit a never-writing stdin
     and stall on TTY probes (readline).
  2. Rscript flags ``--no-save --no-restore --no-init-file`` (NOT
     ``--vanilla``). ``--vanilla`` implies ``--no-environ`` → suppresses
     ``R_LIBS_USER`` → user-installed packages unreachable on Windows.
  3. R scripts are read from ``mcp/r_scripts/`` directly. Do NOT copy
     them to ``%TEMP%`` at startup.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# Locate the R-script directory. We expect the canonical r_scripts/ to
# live under mcp/r_scripts at the repo root, but allow override via env.
_DEFAULT_R_SCRIPTS = Path(__file__).resolve().parent.parent / "mcp" / "r_scripts"
R_SCRIPTS = Path(os.environ.get("SURVBREGDIV_R_SCRIPTS", _DEFAULT_R_SCRIPTS))


def find_rscript() -> str:
    """Locate an Rscript executable.

    Resolution order:
      1. ``$SURVBREGDIV_RSCRIPT`` (explicit override).
      2. ``Rscript`` / ``Rscript.exe`` on PATH.
      3. Windows: highest-versioned ``R-x.y.z`` under
         ``C:\\Program Files\\R\\`` (and the x86 sibling).
      4. macOS / Linux: well-known install locations (CRAN framework,
         ``/usr/local/bin``, Homebrew, distro defaults).

    The macOS fallback matters because Gradio / Docker / GUI parents do
    not always inherit the user's shell PATH when spawning subprocesses.
    """
    override = os.environ.get("SURVBREGDIV_RSCRIPT")
    if override and Path(override).exists():
        return override

    on_path = shutil.which("Rscript") or shutil.which("Rscript.exe")
    if on_path:
        return on_path

    for base in (Path(r"C:\Program Files\R"), Path(r"C:\Program Files (x86)\R")):
        if not base.exists():
            continue
        candidates = sorted(
            (d for d in base.iterdir() if d.is_dir() and d.name.startswith("R-")),
            key=lambda d: d.name,
            reverse=True,
        )
        for d in candidates:
            exe = d / "bin" / "Rscript.exe"
            if exe.exists():
                return str(exe)

    for cand in (
        Path("/Library/Frameworks/R.framework/Resources/bin/Rscript"),
        Path("/usr/local/bin/Rscript"),
        Path("/opt/homebrew/bin/Rscript"),
        Path("/usr/bin/Rscript"),
    ):
        if cand.exists():
            return str(cand)

    raise FileNotFoundError(
        "Rscript not found. Install R (https://cran.r-project.org/), or "
        "set the SURVBREGDIV_RSCRIPT environment variable to the full "
        "path of Rscript (or Rscript.exe on Windows)."
    )


def run_r(script_name: str, payload: dict, timeout_s: int = 600) -> dict:
    """Invoke an R script via temp-file JSON handshake.

    Writes ``payload`` to a temp ``input.json``, runs::

        Rscript --no-save --no-restore --no-init-file <script> <in.json> <out.json>

    and returns the parsed contents of ``output.json``. On failure
    returns a structured ``{status: "error", ...}`` dict so callers never
    see a raw exception traceback.
    """
    script_path = R_SCRIPTS / script_name
    if not script_path.exists():
        return {
            "status": "error",
            "message": f"R script not found: {script_path}",
            "class": "FileNotFoundError",
            "where": "bregsurv_agent.runner.run_r",
        }

    try:
        rscript = find_rscript()
    except FileNotFoundError as e:
        return {
            "status": "error",
            "message": str(e),
            "class": "FileNotFoundError",
            "where": "bregsurv_agent.runner.find_rscript",
        }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".in.json", delete=False, encoding="utf-8"
    ) as fin:
        json.dump(payload, fin, ensure_ascii=False)
        in_path = fin.name
    out_path = in_path.replace(".in.json", ".out.json")

    try:
        cmd = [rscript, "--no-save", "--no-restore", "--no-init-file",
               str(script_path), in_path, out_path]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
        )

        if Path(out_path).exists():
            try:
                with open(out_path, encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "message": f"R output was not valid JSON: {e}",
                    "class": "JSONDecodeError",
                    "where": script_name,
                    "stderr": proc.stderr.strip()[:2000],
                }

        return {
            "status": "error",
            "message": (proc.stderr.strip() or
                        "Rscript exited without producing output"),
            "class": "RscriptCrash",
            "where": script_name,
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip()[:2000],
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": f"Rscript timed out after {timeout_s}s",
            "class": "TimeoutExpired",
            "where": script_name,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"{type(e).__name__}: {e}",
            "class": type(e).__name__,
            "where": f"bregsurv_agent.runner.run_r -> {script_name}",
        }
    finally:
        for p in (in_path, out_path):
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass
