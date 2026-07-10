# Legacy implementation archive

`legacy/v0.1.0/` preserves the minimum semantic evidence from the former 0.1.0 implementation.

- Source commit: `42c0709`
- Annotated tag: `legacy/v0.1.0`
- Baseline verified on 2026-07-10: 28 tests passed; Ruff passed.
- Preserved here: core Python source, the old entry point, bilingual README files, the old CI workflow, and selected behavior tests.
- Full historical project metadata, lock file, unselected tests, and exact dependency environment remain available from the Git tag.

Inherit behavior and lessons, not structure. New code must not import this directory, and root build, test, lint, type-check, and package commands must exclude it.
