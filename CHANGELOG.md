# Changelog

## 2026-11-16

First standalone release. Project configuration and runtime data live outside the
repository. Added a redesigned review workspace, stable comment editor, draft notes,
direct freehand annotations with Delete-to-clear, a single five-reaction scale,
scoped/group feedback, actual-size previews, bounded background work, and an agent
installation workflow. Intended for redesigning existing products and validated
prototypes, not inventing product behavior from scratch.

## 2026-11-17

Added native standard/Retina image pairs, automatic display-density switching in both
directions, explicit per-frame downloads, and density backfill without losing feedback.
The renderer now verifies the CSS viewport through Chrome's control pipe, and imports
retain source provenance; logical 100% size stays fixed across displays.
Named login services let separate project workspaces run alongside one another without
overwriting an existing project's service.
