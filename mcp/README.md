# BregSurv MCP server (developer notes)

A FastMCP server that exposes `BregSurv` R functions as MCP tools so
Claude Desktop (or any MCP client) can fit Cox / NCC models on the
user's machine without round-tripping through hand-written R code.

> **End users — start here:** [`INSTALL.md`](./INSTALL.md). The rest of
> this document is for people editing the server.

## Which document do I want?

| I want to… | Read |
|---|---|
| Install the packaged agent into Claude Desktop (`.mcpb`) | [`INSTALL.md`](./INSTALL.md) |
| Self-host the agent with Docker (local Qwen 7B, GPU) | [`DEPLOY.md`](./DEPLOY.md) |
| Configure or redeploy the public HuggingFace Space | [`HF_SPACE_DEPLOY.md`](./HF_SPACE_DEPLOY.md) |
| Edit this MCP server's code | this file (below) |

The Space's own landing page is `../hf_space_README.md`; HuggingFace requires it
to be named `README.md` on the Space itself, which is why it sits at the repo
root rather than here.

## Directory layout

```
mcp/
├── server.py           FastMCP server: all @mcp.tool definitions, Rscript bridge.
├── manifest.json       MCPB extension manifest (server.type=uv, manifest_version=0.4).
├── pyproject.toml      Runtime deps for the bundle (uv reads this at install).
├── .mcpbignore         Excludes tests/cache from `mcpb pack`.
├── r_scripts/          One .R per tool — receives a temp JSON, writes a temp JSON.
├── test_*.py           E2E harnesses (NCC, highdim, wizard).
├── INSTALL.md          End-user install guide (release body for distribution).
└── README.md           This file.
```

## Local dev workflow (fastest iteration)

1. Restore the direct-mount entries to Claude Desktop's
   `claude_desktop_config.json` (saved as `*.before-mcpb-2026-04-28.bak`
   the first time we packaged a bundle). Direct mount points
   `claude_desktop_config.json` at `server.py` directly, so changes only
   require a Claude Desktop restart — no repack, no reinstall.
2. The direct-mount config and an installed `.mcpb` extension share the
   server name `bregsurv` and conflict — disable / uninstall the
   extension while developing.
3. Edit `server.py` (or the relevant `r_scripts/*.R`).
4. Quit Claude Desktop fully (tray icon → Quit), reopen.

The tool descriptions seen by the AI are the `@mcp.tool` docstrings —
keep them user-side actionable, not implementation notes.

## Building a release bundle

```bash
mcpb validate manifest.json          # schema check
mcpb pack . bregsurv-<version>.mcpb
```

The Anthropic `mcpb` CLI is npm-distributed:
`npm install -g @anthropic-ai/mcpb`. End users do not need it.

## Running tests

```bash
python test_ncc_e2e.py
python test_highdim_e2e.py
python test_wizard_e2e.py
```

Each test spawns a fresh Rscript per call; the suites take a few minutes
on this machine.

## A note on comments

Design invariants are documented inline, next to the code they constrain —
look for the `DESIGN INVARIANT` and `Architecture invariants` comments in
`server.py` and the `r_scripts/`. Each states what must not change and why,
so the rationale travels with the code rather than living in a separate
document that can drift out of sync.
