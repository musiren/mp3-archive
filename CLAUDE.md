# Claude Code Instructions

## Planning

- All plans must be created and managed as `.md` files under the `skills/` directory.
- Naming convention: `skills/<topic>-plan.md`
- Plans must be written in English.

---

## Coding Rules

### Directory Structure

| Directory | Purpose |
|-----------|---------|
| `src/`    | All source code (modules, classes, utilities) |
| `test/`   | All test code |
| `skills/` | Project documentation and guides |

### Source Code (`src/`)

- All implementation files go under `src/`.
- File naming: `snake_case.py` (e.g., `mp3_parser.py`, `file_manager.py`)

### Method-Level Comments

Every method and function must have a docstring describing what it does, its parameters, and return value.

```python
def load_mp3(file_path: str) -> dict:
    """
    Load an MP3 file and return its metadata.

    Args:
        file_path: Absolute or relative path to the MP3 file.

    Returns:
        A dictionary containing metadata fields such as title,
        artist, album, and duration.
    """
    ...
```

### Test Code (`test/`)

- All test files go under `test/`.
- File naming: `test_<module>.py` (e.g., `test_mp3_parser.py`)
- Each test function must have a docstring describing what it verifies.

### **[MANDATORY] Coding Rules**

1. **Run all tests before every commit to `src/`.** Do not commit if any test fails.
   ```bash
   python -m unittest discover -s test -v
   ```

2. **When any UI file in `src/` changes (including `main_window.ui`, `main_window.py`, or any `*_dialog.py`), regenerate the corresponding preview image under `docs/` and include it in the same commit.** Never commit UI changes without updating the preview image.
   - `src/main_window.ui` / `src/main_window.py` → `docs/ui-preview.jpg`
   - `src/<name>_dialog.py` → `docs/<name>-dialog-preview.jpg`

3. **When any method/function in `src/` is added, removed, or modified, update the corresponding tests in `test/` in the same commit.** Never commit implementation changes without matching test updates.
   - Method **added** → add tests verifying the new behaviour
   - Method **removed** → remove or update the related tests
   - Signature/behaviour **changed** → update affected tests

---

## Git Rules

### **[MANDATORY] Git Rules**

1. **Always ask the user before pushing. Never push without explicit user approval.** Only push when the user directly says so (e.g. "푸시해줘"). Never push automatically or implicitly as part of the workflow.
   - After committing, ask **once**: "푸시할까요?"
   - When the stop hook fires about unpushed commits, do **not** ask again — just wait for the user's response.

2. **When any UI file in `src/` changes, regenerate the corresponding preview image under `docs/` before committing.** Do not push UI changes without updating the preview image.

### Commit Message Style

- Follow Linux kernel style.
- Subject line: 50 chars or fewer, imperative mood (e.g. `Fix bug`, `Add feature`)
- Blank line between subject and body.
- Body: wrap at 72 chars, explain *why* not *what*.
- All commit messages and documentation must be written in English.

```
subsystem: short summary of the change

More detailed explanation of why this change is needed,
what problem it solves, and any side effects.
```

### PR and Merge Rules

- **Before opening a PR to main:** update `NEWS` file with the list of changes on the branch.
- **Before opening a PR to main:** update `README.md` to reflect any usage changes.
- **After merging to main:** create a tag in `v년월일` format (e.g. `v20260407`).
  ```bash
  git tag v$(date +%Y%m%d)
  git push origin v$(date +%Y%m%d)
  ```
