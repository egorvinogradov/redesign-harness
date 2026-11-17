# Redesign Harness — agent entry point

If asked to install this tool, follow **INSTALL.md** end to end. Do not stop after
cloning the repository. Verify the running local UI. Do not grant design work time
unless the user requests it or chooses it in the UI.

This tool redesigns an existing working product or validated prototype. Preserve its
workflows. It is not a greenfield product-design or requirements-discovery tool.

Keep all project configuration, reference designs, screenshots, evidence, sessions,
credentials, and runtime state outside this public repository. Never copy the user's
source into it. Follow the target project's own rules for reading and browser access.

For coding, use the existing Python standard-library server and static frontend.
Run `python3 -m unittest discover -s scripts -p 'test_*.py'` and
`node --check assets/app.js` after changes. Verify visual changes in a real browser.
Preserve default 100% logical image scale, native 1×/2× display switching in both directions,
durable feedback, scoped annotations, and work limits. Never upscale a bitmap as a Retina export.
Never test feedback or worker controls against someone's real workspace: use a separate
`--home` and `--port`, with `--no-worker` for UI tests.
