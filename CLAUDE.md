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

## Android App Rules

### **[MANDATORY] Android On-Device Verification Routine**

Whenever a change affects the Android app — i.e. `buildozer.spec`,
`.github/workflows/build.yml`, `src/main_window_android.py`, or any
`src/` module bundled into the APK — **always** run this full routine after the
change is pushed (push itself still requires explicit user approval per the Git
Rules):

1. **Watch the build.** Monitor the `Build` workflow's `android` job (file
   `.github/workflows/build.yml`) for the pushed commit until it finishes
   (e.g. `gh run watch <run-id>`).
2. **Install on the connected device.** When the build succeeds, download the
   `mp3-archive-debug` artifact (`bin/*.apk`) and install it on the
   ADB-connected phone:
   ```bash
   gh run download <run-id> -n mp3-archive-debug -D build/ci-apk
   adb install -r build/ci-apk/*.apk
   ```
3. **Test on the device.** Launch the app (`org.musiren.mp3archive`) and verify
   the change is actually reflected on-device — not just that unit tests pass.
   Capture a screenshot of the relevant screen as evidence.
   - **List/scan tests:** use the real library at
     `/storage/emulated/0/MyMusic/Single` (≈244 real mp3 files). Pick this
     folder in the in-app file manager rather than creating throwaway stub
     files.

Unit tests passing is **never** a substitute for this on-device check: the Kivy
UI tests are skipped off-device, so the APK is the only place the Android UI is
exercised.

---

## Git Rules

### **[MANDATORY] Git Rules**

1. **Always ask the user before pushing. Never push without explicit user approval.** Only push when the user directly says so (e.g. "푸시해줘"). Never push automatically or implicitly as part of the workflow.
   - After committing, ask **once**: "푸시할까요?"
   - Only push when the user's message **explicitly** contains an approval word such as "ㅇㅇ", "푸시해줘", "push", or "yes".
   - The stop hook firing (even with no user text) is **never** approval to push — do not push in response to it.
   - If the stop hook fires without explicit user approval, simply wait for the user to respond.

2. **When any UI file in `src/` changes, regenerate the corresponding preview image under `docs/` before committing.** Do not push UI changes without updating the preview image.

### **[MANDATORY] Branch Workflow on New Requests**

When a **new request** arrives, decide the branch before starting work:

1. **Same line of work?** If the request is related to — or a direct
   extension of — what the current working branch already covers, **keep
   working on the current branch**; do not create a new one.
   - **Exception:** if that branch has already been **opened as a PR or
     merged**, do not silently keep committing to it. **Ask the user**
     whether to create a new branch.

2. **Unrelated / new line of work?** Create a **new development branch** for
   it. But first, **check the existing branches** for any that still need to
   go to `main` (committed/pushed work with no merged PR yet), and **ask the
   user** whether to open a PR for those before branching off.

Always surface what you found (which branches are unmerged, whether the
current branch is already PR'd/merged) and let the user decide — never open a
PR or switch branches on your own.


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
