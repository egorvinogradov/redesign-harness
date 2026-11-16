# Redesign Harness

Make a working product beautiful, without reinventing how it works.

Redesign Harness is a local workspace for autonomous visual redesign. Start with an
existing product or a rough prototype whose workflows have been tested with people.
Give the design director a bounded work window, then review visuals whenever you have
a moment. Your feedback becomes shared design context across screens.

**Build rough → validate the workflow → redesign beautifully.**

It is not a tool for inventing a product from scratch. Establish what the product does
and how people use it first, even in an intentionally ugly prototype. This harness then
improves visual hierarchy, typography, spacing, controls, and consistency. Small,
well-explained interaction improvements are welcome; speculative features and wholesale
workflow invention are outside its scope. It produces design artifacts and editable
prototypes; implementing those designs into your product is a separate step.

## Install with your coding agent

Give your agent this repository link, or paste:

> Install Redesign Harness from https://github.com/egorvinogradov/redesign-harness
> for the existing product in my current project. Follow INSTALL.md. Keep all project
> data and credentials outside the public repository. Reuse my installed Claude Code
> login, configure the project, seed the review queue, start the local review service,
> and verify it opens. Leave design work paused until I choose a work window.

See [INSTALL.md](INSTALL.md) for the complete agent workflow. Agents entering the
repository find the same instructions in [AGENTS.md](AGENTS.md).

## Review at your own pace

- Screenshots open at **100%**: one image pixel per browser CSS pixel.
- One feedback scale: five reactions, plus optional short comments.
- Draw directly on screenshots, delete unsent marks, group selection, and side-by-side comparison.
- Style and component feedback carries into later revisions.
- Interaction sequences explain workflow changes in a few frames.
- Separate unseen, viewed, and reviewed queues. Unfinished notes stay in the tab.
- Bounded work sessions, expiring daily schedules, checkpoints, and limited retries.
- Switch between Claude Code and a Codex worker using a Pen Dev canvas.

The app stores project information locally. This repository contains only the tool.
AI workers still send their prompts and selected project context to their configured
model provider. A local web server does not mean local model inference.

## Requirements

Python 3.11+, a modern browser, and an installed/authenticated Claude Code runtime.
The macOS login service and local PNG renderer are designed for macOS. The web app
and store use Python's standard library; there is no package install or frontend build.

Claude uses its existing authentication. No API keys belong in this repository.
The app prefers the installed desktop-bundled Claude runtime when available, otherwise
`claude` on PATH. Choose a model available to your account, or omit it to use the default.
Workers use Claude's `auto` permission mode: use a trusted, scoped project directory.

Pen mode additionally requires Codex CLI, Pen Dev running, its MCP tools configured in
Codex, and an explicit local canvas path. This mode uses Codex automatic approval review
(`--approve-for-me`) and may still block on actions that require review. It does not drive
Pen's built-in chat. It is an optional integration, not a bundled model or editor.

## Start a project

```sh
git clone https://github.com/egorvinogradov/redesign-harness.git
cd redesign-harness
python3 scripts/director.py init \
  --project /absolute/path/to/your-product \
  --name "Your product" \
  --timezone America/New_York
python3 scripts/director.py seed
python3 scripts/director.py install
```

Open **http://127.0.0.1:4317**. Expand **Work session**, set a duration, and start.
Installation alone never grants work time.

Add `--instructions /absolute/path/to/private-design-brief.md` to `init` to supply
project conventions, reference source paths, visual direction, and research limits.
Use `--model` for an account-supported Claude model, `--canvas` for a Pen document,
and `--width` / `--height` for the product's screen dimensions (default 1920 × 1080).
Do not put private design briefs inside this repository.

Without a login service, run the server directly:

```sh
python3 scripts/server.py
```

Use `--no-worker` to inspect a board without starting AI work. A missing CLI is not a
problem for review-only use. The generic starter queue is finite. Add specific briefs
as you learn about the product:

```sh
python3 scripts/director.py add-job "Simplify the filters" \
  --brief "Preserve all existing operators. Show a focused open, edit, apply sequence." \
  --priority 30
python3 scripts/director.py run --hours 2
python3 scripts/director.py status
python3 scripts/director.py pause
```

## Workspaces and privacy

Default state: `~/Library/Application Support/Redesign Harness/`. Use
`REDESIGN_HARNESS_HOME` or `--home /absolute/private/workspace` to choose another.
A workspace represents one project. Run another server with a separate `--home` and
`--port` for another project. The macOS installer manages one login service; installing
again replaces that service's workspace and port.

The private workspace contains:

- `review.sqlite`: settings, queue, reviews, and feedback.
- `assets/`: immutable, content-addressed PNGs.
- `runs/`: per-job prompts, checkpoints, results, editable sources, and event logs.
- `evidence/`: project research.
- `workspace/`: working directory for AI sessions.

The server binds only to loopback. Writes require same-origin requests and a local
session token. Do not expose it through a public tunnel or reverse proxy: it is a
personal desktop tool, not a multi-user hosted service. Never commit runtime state,
credentials, private source, or screenshots from a real project.

The director launches a separate background session for each job. These are not
messages in an existing Claude desktop conversation. **Director's desk** shows the
active job and its local session/log details. It is an activity view, not a live chat.

Worker prompts restrict source edits and production actions, but this is not an OS
sandbox. Existing CLI permissions and account access still apply. Use project
instructions and the CLI's controls to define the intended access.

## What the director does

Read [`references/director.md`](references/director.md) for the design process.
Workers inspect existing capabilities, choose meaningful directions, produce editable
sources, visually inspect PNGs, and publish focused review artifacts. They use feedback
from the whole style family, not just the current screenshot.

The supervisor runs one job at a time. It stops at the granted deadline, retries a
failed or stalled job at most twice, and caps each attempt at 25 minutes. Pausing
preserves the queue and checkpoints. Sleep does not extend a work window. Daily
schedules expire within 30 days and never catch up missed hours.

Workers submit the JSON result contract embedded in `scripts/supervisor.py`. You can
also import an artifact manifest with `scripts/director.py import manifest.json`.
PNG inputs must be inside the private workspace. A minimal manifest is:

```json
{
  "title": "A clearer filter panel",
  "style": "warm-light",
  "page": "overview",
  "component": "filters",
  "node": "filters-v1",
  "image": "/absolute/private/workspace/assets/filters.png",
  "caption": "Change filters without losing context."
}
```

For locally owned HTML mockups, `scripts/render.py` uses a temporary headless Chrome
profile at device scale 1. It accepts only HTML inside the workspace's `runs/` tree.
It is not a tool for logged-in website research.

## Development

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
node --check assets/app.js
```

Assets are served directly, so refresh the browser after changes. Review drafts are
stored in session storage; they survive refresh and navigation in the same tab.
Tests use temporary workspaces and fake workers; they do not call paid AI services.

## License

MIT. See [LICENSE](LICENSE).
