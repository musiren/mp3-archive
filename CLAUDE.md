# Claude Code Instructions

## Planning

- All plans must be created and managed as `.md` files under the `skills/` directory.
- Naming convention: `skills/<topic>-plan.md`
- Plans must be written in English.

## Coding Rules

See `skills/coding-guide.md` for full coding conventions. Key rules:

- All source code must be placed in `src/`.
- Every method/function must have a docstring or comment explaining its purpose.
- All test code must be placed in `test/`.
- **[MANDATORY]** Run all tests before every commit to `src/`. Do not commit if any test fails.
- **[MANDATORY]** When `src/main_window.ui` or `src/main_window.py` changes, regenerate `docs/ui-preview.jpg` and include it in the same commit. Never commit UI changes without updating the preview image.
- **[MANDATORY]** When any method/function in `src/` is added, removed, or modified, update the corresponding tests in `test/` in the same commit and confirm all tests pass. Never commit implementation changes without matching test updates.

## Git Rules

See `skills/git-guide.md` for full git conventions. Key rules:

- **[MANDATORY]** Always ask the user before pushing. Never push without explicit user approval.
- Commit messages must follow Linux kernel style.
- All commit messages and documentation must be written in English.
