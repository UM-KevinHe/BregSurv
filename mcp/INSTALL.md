# Install SurvBregDiv for Claude Desktop

This extension lets you run survival-analysis models from the **SurvBregDiv** R package directly inside Claude Desktop. You describe your data and your question in plain English (or Chinese); Claude picks the right model, runs it on your machine, and explains the results.

**Your data never leaves your computer.** The extension only sends file paths and analysis results back to Claude — never the raw data file.

---

## Before you install — two prerequisites you need on your computer

Check off both of these before downloading the extension. Skipping these is the #1 cause of installation problems.

### Prerequisite 1 — R (≥ version 4.0)

**What it is.** R is a free statistical computing language. SurvBregDiv is written in R, so you need R installed for the extension to do any computing.

**How to check whether you already have R installed:**

- **Windows.** Open the Start menu and type "R". If you see "R x64 4.x.x" or "RStudio" in the results, you have it.
- **macOS.** Open Finder → Applications. Look for an "R" application. Or open Terminal and type `R --version`. If you see a version number, you have it.
- **Linux.** Open a terminal and type `R --version`. If you see a version number, you have it.

**If you don't have it (or your version is < 4.0):**

Download R from the official site: <https://cran.r-project.org/>

- **Windows users:** click "Download R for Windows" → "base" → click the big "Download R 4.x.x for Windows" link. Run the installer. Accept all defaults.
- **macOS users:** click "Download R for macOS" → pick the `.pkg` matching your Mac (Apple Silicon = M1/M2/M3, Intel = older Macs). Run the installer. Accept all defaults.
- **Linux users:** follow the distribution-specific instructions on the CRAN page (Ubuntu/Debian/Fedora each have their own).

**After installing, verify it worked:** open R (or RStudio if you have it), and you should see a `>` prompt. Type `R.version.string` and press Enter — it should print something like `"R version 4.5.2 (2025-10-31)"`. As long as the number is 4.0 or higher, you're good.

### Prerequisite 2 — The `SurvBregDiv` R package

**What it is.** R itself is just the language. The actual SurvBregDiv functions (`coxkl`, `cox_MDTL`, etc.) live in a separate package you install into R.

**How to install it.** Open R (or RStudio), and at the `>` prompt, paste this single line and press Enter:

```r
install.packages("SurvBregDiv")
```

R will download from CRAN and compile the package. **The first install takes 2–5 minutes** (it compiles C++ code). You'll see progress messages — that's normal. When it ends with something like `* DONE (SurvBregDiv)`, it's installed.

If you want the latest development version instead (newer features, less battle-tested):

```r
install.packages("remotes")  # one-time, if you don't have it
remotes::install_github("UM-KevinHe/SurvBregDiv")
```

**Verify it worked.** Still in R, type:

```r
library(SurvBregDiv)
```

If it returns to the `>` prompt with no errors, you're done. If it says "there is no package called 'SurvBregDiv'", the install didn't finish — re-run `install.packages("SurvBregDiv")` and watch for errors.

### What you do NOT need to install

- ❌ **Python** — not needed. Claude Desktop manages Python automatically for this extension.
- ❌ **Node.js** — not needed (also automatic).
- ❌ **Conda / Anaconda** — not needed.
- ❌ **A C++ compiler** — only `install.packages` needs it, and on Windows + macOS R will offer to install it for you if needed (Rtools on Windows, Xcode CLT on macOS).

---

## Install the extension

1. Download the `.mcpb` file from the [Releases page](https://github.com/UM-KevinHe/SurvBregDiv/releases/latest). Pick the file named `survbregdiv-<version>.mcpb`.
2. Open **Claude Desktop**.
3. Click the **Settings** icon (gear) in the bottom-left.
4. Click **Extensions** in the sidebar.
5. Click **Advanced settings** at the top of the Extensions page.
6. Find the **Extension Developer** section and click **Install Extension…**.
7. In the file picker, select the `.mcpb` file you downloaded in step 1.
8. Claude Desktop will show an install dialog with a form (the `user_config` form). See the next section for what to enter.

> **Note:** double-clicking the `.mcpb` file in your file manager is **not** documented to work. Always install through Settings → Extensions.

---

## During install — point the extension at R

The install dialog asks one question:

> **Path to your Rscript executable**

This is the program that runs R from the command line. The extension uses it to call SurvBregDiv. **`Rscript` is installed automatically when you install R** — you don't need to install anything extra, you just need to tell the extension where to find it.

**Click the file picker button and navigate to the path below for your OS:**

- **Windows:** typically `C:\Program Files\R\R-4.x.x\bin\Rscript.exe` (replace `4.x.x` with your version — e.g. `R-4.5.2`).
- **macOS:** typically `/Library/Frameworks/R.framework/Resources/bin/Rscript`. (Apple Silicon Macs may have an additional copy at `/opt/homebrew/bin/Rscript` if you installed via Homebrew — either works.)
- **Linux:** typically `/usr/bin/Rscript` or `/usr/local/bin/Rscript`.

**If you don't know your exact R version**, open R and type `R.version.string` to see it.

**Stuck finding it?**

- **Windows:** open File Explorer → `C:\Program Files\R\` → you'll see one or more folders like `R-4.5.2`. Open the latest one → `bin` → `Rscript.exe`.
- **macOS / Linux:** open Terminal and type `which Rscript`. The output is the exact path to paste/select.

After you confirm, click **Install**. Claude Desktop will set up Python and the extension's dependencies in the background (this takes 30 seconds to a couple of minutes the first time).

---

## After install — turn the extension ON

**This step is easy to miss and is the #1 cause of "I installed it but Claude can't see it".**

When the install finishes, you'll be back on the Extensions page with **SurvBregDiv** in the list. **By default the extension is installed but disabled** — there is a toggle switch on the right side of its row that starts in the OFF (gray) position.

Click the toggle so it turns ON (blue/green). Claude Desktop will then start the extension's server in the background; you may briefly see a "starting…" indicator. Once the toggle is on and steady, you're ready to use it.

If you skip this step, Claude in a new chat will not see any of the SurvBregDiv tools — the extension is sitting dormant.

---

## Verify the extension works

1. Open a new chat in Claude Desktop.
2. Type: **"Use SurvBregDiv to help me start a survival analysis."**
3. Claude should respond by walking you through a short questionnaire about your data (the guided wizard).

If Claude asks what file your data is in and runs analysis steps without errors, you're set.

---

## Troubleshooting

### "Claude doesn't see SurvBregDiv even though I installed it"

The extension is almost certainly installed but **not enabled**. Open Settings → Extensions, find SurvBregDiv in the list, and click the toggle on its row so it turns ON (blue/green). New extensions are disabled by default — installing only puts them in the list; the toggle is what actually starts the server. After enabling, open a *new* chat (existing chats need to be reopened to see freshly enabled tools).

### "Rscript not found" or "Could not find R"

- The path you entered during install is wrong. Open Settings → Extensions → SurvBregDiv → and re-enter the path. Use the OS-specific paths in the install section above.
- On Windows: make sure the path ends in `Rscript.exe` (with the `.exe`), not just `Rscript`.

### "there is no package called 'SurvBregDiv'"

The R package didn't install (or installed under a different R version than the one Claude is using). Open the same R version that you pointed the extension at, and re-run:

```r
install.packages("SurvBregDiv")
library(SurvBregDiv)  # should return cleanly
```

If you have multiple R versions installed, the extension uses whichever `Rscript.exe` you selected — make sure SurvBregDiv is installed in *that* R, not a different one.

### "package 'jsonlite' is not available" (or similar dependency error)

Open R and run:

```r
install.packages("jsonlite")
```

`jsonlite` is the only Python↔R bridge dependency the extension needs that isn't auto-installed by SurvBregDiv. (SurvBregDiv's own dependencies like `survival`, `RcppArmadillo` install automatically.)

### The extension runs the wrong tool

Claude sometimes loads tools lazily and may pick a not-quite-right tool. If the analysis Claude proposes doesn't match what you described, say:

> "Please use the start_analysis wizard first."

That forces Claude through the guided questionnaire, which deterministically picks the right tool.

### Plot doesn't appear inline after cross-validation

This is a known Claude Desktop quirk. Just say:

> "Please draw the cross-validation curve as an inline artifact."

Claude will render the plot via its built-in artifact tool.

### Something else

Open an issue at <https://github.com/UM-KevinHe/SurvBregDiv/issues> with:

- Your OS + version (e.g. "Windows 11", "macOS 14.5")
- Your R version (`R.version.string` in R)
- The exact error message Claude showed
- What you typed when the error happened

---

## Privacy and what gets sent where

- **Your data files stay on your computer.** The extension passes only a file path string to R; R reads the file locally on your machine.
- **Analysis results (model coefficients, cross-validation scores, plots) are sent back to Claude** so Claude can explain them to you. These travel through Anthropic's API like any other Claude conversation.
- **Tool names and arguments transit Anthropic's API** as part of normal MCP operation.
- If your data files contain PHI or other sensitive information that is *only* safe on disk, that's fine — those bytes stay on disk. But the analysis results derived from them (e.g. "coefficient for variable Age = 0.31") will appear in Claude's response and therefore in Anthropic's logs. Plan accordingly.

For the full privacy model, see the project README.

---

## Uninstall

Settings → Extensions → SurvBregDiv → Uninstall. This removes the extension from Claude Desktop. It does **not** uninstall R or the SurvBregDiv R package — those stay on your system.
