# Install with an agent

This is an executable workflow for a coding agent, not a request for the user to do
manual setup. Complete the steps, verify the result, and report the local URL.

## 1. Identify the product and existing installation

Use the current working project unless the user names another. It must already have
working screens and established workflows. Read its AGENTS.md and relevant design or
browser instructions. Do not copy its source or private documents into this repository.

Use an existing checkout of this repository if present; otherwise clone it into the
user's normal repositories directory. Do not clone it inside the target product.
Resolve all paths to absolute paths. Check Python 3.11+, an authenticated Claude Code
CLI or desktop-bundled runtime, and whether port 4317 is available. Do not print auth
files or secrets. If the CLI is missing, the review app can still run without workers;
report that dependency clearly rather than claiming autonomous design is ready.

Check for an existing workspace before running init or seed. If it contains settings
and reviews, preserve them and its current work window. Never reset its database to
repair an installation. Use `director.py --home <path> status` for inspection; keep its
private paths and data out of public logs and commits.

## 2. Configure a private workspace

On macOS the default is `~/Library/Application Support/Redesign Harness/`.
For additional projects, choose another private `--home`, a free port, and a unique
`--service` name. For example, `install --service project-two --port 4318` creates
`app.redesign-harness.project-two` alongside the default service. Do not replace a
different project's service. Named services keep workspaces and queues independent.

Write a private `project-brief.md` inside the workspace, covering:

- Existing project source path and where its important screens live.
- Validated workflows and capabilities that must remain intact.
- Available approved reference designs, with local paths.
- Target product dimensions (default 1920 × 1080).
- Allowed research sources and the project's browser/access rules.
- Any user taste, approval, or veto already given.

Do not put credentials in the brief. Do not invent analytics, product requirements,
or a visual preference the user has not expressed. Missing analytics does not block
source-grounded redesign. Use the current project context before asking questions.

Configure using paths you resolved above (replace the placeholders):

```sh
python3 scripts/director.py --home "$PRIVATE_WORKSPACE" init \
  --project "$PRODUCT_REPOSITORY" \
  --name "$PRODUCT_NAME" \
  --instructions "$PRIVATE_WORKSPACE/project-brief.md" \
  --timezone "$USER_TIMEZONE"
python3 scripts/director.py --home "$PRIVATE_WORKSPACE" seed
```

Use a valid IANA timezone such as `Europe/London` or `America/New_York`. Infer it from
the user's environment where possible. Add `--model` only for an account-supported
model preference. Do not assume access to an account-specific model. `init` preserves
existing jobs, feedback, and the active time window. `seed` is idempotent.

Claude is the default. If the user wants Pen, configure `--canvas` with the expected
existing `.pen` file and verify Codex has the Pen MCP tools. Do not hijack another open
canvas. Do not edit either app's conversation database.

## 3. Start the review service

On macOS:

```sh
python3 scripts/director.py --home "$PRIVATE_WORKSPACE" install --port 4317
```

This creates `~/Library/LaunchAgents/app.redesign-harness.plist`. For another project,
add `--service project-two --port 4318` and use its private `--home`. It restarts on login,
but does not keep the computer awake. It does not grant work time.

For a foreground server or another OS:

```sh
python3 scripts/server.py --home "$PRIVATE_WORKSPACE" --port 4317
```

On platforms without `fcntl` or POSIX process groups, the current supervisor is not
supported. macOS is the supported installation target; do not claim cross-platform
worker support without testing it. The bundled renderer expects Google Chrome on macOS.

If this is a new workspace, leave it paused. If the user explicitly requested a work
window, grant exactly that duration using `director.py --home ... run --hours N`.
Never silently enable daily schedules or add more time during installation.

## 4. Verify the actual result

1. Confirm `http://127.0.0.1:4317/health` returns `ok: true`.
2. Open the local UI using the user's allowed browser tooling. Confirm the product
   label, selected engine, work controls, and queue state match local configuration.
3. Confirm a new installation is paused and no AI job was launched unintentionally.
4. If UI testing needs feedback, use a separate temporary workspace with `--no-worker`.
   Do not submit fake feedback to the user's board.
5. Report the live URL and whether work is paused or running. Name any missing runtime
   clearly. Do not claim a normal Claude desktop chat exists: jobs are background CLI
   sessions, visible through the activity panel and local transcripts.

## 5. Make future invocation easy

If the user asked for a reusable skill in their coding agent, install or link this
repository's SKILL.md using that agent's supported skill convention. A project-specific
adapter can point at this checkout and its private workspace. Keep project references
in that adapter, not in the public repository. Do not overwrite an existing skill with
the same name; inspect it first and preserve user customizations.

For agents that discover skills in `~/.agents/skills/`, link the whole checkout (not
just SKILL.md) so relative reference files remain available:

```sh
mkdir -p "$HOME/.agents/skills"
# Run only when this destination does not already exist.
ln -s "$HARNESS_CHECKOUT" "$HOME/.agents/skills/redesign-harness"
```

Use the project's normal installation conventions. No root privileges, package
manager dependencies, cloud deployment, or API-key copying are needed for the app.
