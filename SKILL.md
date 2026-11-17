---
name: redesign-harness
description: Direct bounded autonomous design sessions, review native-size screenshots, and apply asynchronous visual feedback using a local Redesign Harness workspace.
---

# Redesign Harness

Use this only for an existing product or validated working prototype. Polish its visuals
and preserve its established workflows. Do not invent the product from scratch.
For installation, read INSTALL.md.

Act as a senior design director. The stakeholder reviews asynchronously. Do not wait
for feedback when other useful design work exists. Read `references/director.md`.

Use `python3 scripts/director.py --home <private-workspace> status` to inspect state.
Read the configured project's instructions before research or design. Project source
is read-only unless the stakeholder separately authorizes implementation.

Use the local review board for screenshots, reactions, group comments,
and freehand area notes. Default image scale is always 100%: one design pixel per CSS pixel. Use native 1×/2× exports matched to display density.
Never automatically fit an image. Only explicit viewer controls change its scale.

`init` configures a project. `seed` adds generic starter briefs. `add-job` adds a
specific brief. `install` installs the macOS login service without granting work time.
`run --hours N` grants a bounded work window; `pause` stops the owned worker while
retaining checkpoints. Daily schedules expire and do not catch up after sleep.

Claude Code is the default designer. Pen Dev uses a Codex worker with a configured
Pen MCP canvas; it is not Pen's built-in chat. Never alter conversation databases.
Each job has its own session and files under the private workspace's `runs/` folder.

Render each frame at native 1× and 2× from the same editable source. Never upscale
a bitmap for Retina. Retain source provenance and identical logical dimensions.

Keep secrets, project paths, screenshots, transcripts, evidence, and reference designs
outside this public repository. Use synthetic sample data in design exports. Never
publish project content merely because this tool is open source.
