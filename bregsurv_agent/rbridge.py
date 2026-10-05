"""The R dispatch layer: find Rscript, hand it JSON, read JSON back.

`_run_r` runs one script from `mcp/r_scripts/` with a JSON payload and returns its
JSON result; `_find_rscript` locates the R interpreter. The agent needs nothing
beyond R and these scripts to reach the estimator library.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Duplicated as `DEFAULT_CV_SEED` in every mcp/r_scripts/cv_*.R, so the R
# side has a default even when called directly. Moved here from tools.py when
# the V2 tool layer was retired: the seed is a property of the R dispatch, and
# test_reproducibility_e2e checks that the two copies still agree.
DEFAULT_CV_SEED = 20260818

_HERE = Path(__file__).resolve().parent

# The R scripts live beside the package. `SURVBREGDIV_R_SCRIPTS` overrides it,
# which is how a deployed container or a cluster job points at its own copy.
R_SCRIPTS = Path(os.environ.get("SURVBREGDIV_R_SCRIPTS",
                                str(_HERE.parent / "mcp" / "r_scripts")))


def _find_rscript() -> str:
    """Locate an Rscript executable.

    Resolution order:
      1. $SURVBREGDIV_RSCRIPT (explicit override)
      2. "Rscript" / "Rscript.exe" on PATH
      3. Windows: highest-versioned R-x.y.z under C:\\Program Files\\R\\
         (and the x86 sibling)
      4. macOS / Linux: well-known install locations (CRAN framework,
         /usr/local/bin, Homebrew, distro defaults)

    Step 4 is not belt-and-braces. A GUI-launched process on macOS does not
    inherit the user's shell PATH, so step 2 misses an Rscript that "works in
    Terminal" -- which is exactly the report that gets filed as "the extension
    is broken".
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
        "Rscript not found. Install R (https://cran.r-project.org/), or set "
        "the SURVBREGDIV_RSCRIPT environment variable to the full path of "
        "Rscript (or Rscript.exe on Windows)."
    )


def _run_r(script_name: str, payload: dict, timeout_s: int = 600) -> dict:
    """Invoke an R script via a temp-file JSON handshake.

    Writes `payload` to a temp input.json, runs

        Rscript --no-save --no-restore --no-init-file <script> <in.json> <out.json>

    and returns the parsed contents of output.json. A failure NEVER raises: it
    comes back as a structured ``{"status": "error", ...}`` dict, because every
    caller is either a tool that must answer or a pipeline stage that turns the
    message into a refusal the analyst can read.

    Three flag choices that are not arbitrary:

    * ``--no-save --no-restore --no-init-file``, NOT ``--vanilla``. `--vanilla`
      also implies `--no-environ`, which suppresses ``R_LIBS_USER`` -- and on
      Windows (and on shared clusters) jsonlite and BregSurv are usually installed
      ONLY in the user library. Under `--vanilla` R cannot find its own packages.
    * ``stdin=subprocess.DEVNULL``. An inherited stdin makes R stall waiting for
      input that will never come, which presents as a hang rather than an error.
    * a temp FILE rather than a pipe, because R's output can exceed pipe buffers
      and because the file survives long enough to be inspected when something
      goes wrong.
    """
    script_path = R_SCRIPTS / script_name
    if not script_path.exists():
        return {
            "status": "error",
            "message": f"R script not found: {script_path}",
            "class": "FileNotFoundError",
            "where": "rbridge:_run_r",
        }

    try:
        rscript = _find_rscript()
    except FileNotFoundError as e:
        return {
            "status": "error",
            "message": str(e),
            "class": "FileNotFoundError",
            "where": "rbridge:_find_rscript",
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
        # Under SLURM, pin R's BLAS/OpenMP threads to the allocation unless the
        # job already did. (job 60965056 vs 60965940, same
        # node): unpinned, R's BLAS spawned a thread per node core inside a
        # 4-core cgroup and a 260-row elastic-net fit took 25 CPU-minutes and
        # timed out; pinned, the whole suite took 5. Outside SLURM nothing changes.
        env = os.environ.copy()
        if env.get("SLURM_CPUS_PER_TASK"):
            for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
                env.setdefault(k, env["SLURM_CPUS_PER_TASK"])
        # : the discrete row's network members run in Python, called back
        # from R through mcp/py_scripts/run_diskd.py -- with THIS interpreter,
        # the one that has numpy and torch, unless the caller named another
        import sys as _sys
        env.setdefault("BREGSURV_PYTHON", _sys.executable)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            env=env,
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
            "where": f"rbridge:_run_r -> {script_name}",
        }
    finally:
        for p in (in_path, out_path):
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass


# Public aliases. The leading underscores are historical -- these were private
# helpers inside the MCP server -- and the old names are kept so the nine call
# sites did not all have to change in the same commit as the move.
find_rscript = _find_rscript
run_r = _run_r

__all__ = ["run_r", "find_rscript", "_run_r", "_find_rscript",
           "R_SCRIPTS", "DEFAULT_CV_SEED"]
