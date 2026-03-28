# Coding Guide

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| `src/`    | All source code (modules, classes, utilities) |
| `test/`   | All test code |
| `skills/` | Project documentation and guides |

## Source Code (`src/`)

- All implementation files go under `src/`.
- File naming: `snake_case.py` (e.g., `mp3_parser.py`, `file_manager.py`)

## Method-Level Comments

Every method and function must have a docstring describing:
- What the method does
- Parameters
- Return value

### Python Docstring Example

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

### One-liner for simple methods

```python
def is_mp3(file_path: str) -> bool:
    """Return True if the file has an .mp3 extension."""
    return file_path.endswith(".mp3")
```

## Test Code (`test/`)

- All test files go under `test/`.
- File naming: `test_<module>.py` (e.g., `test_mp3_parser.py`)
- Each test function must have a docstring describing what it verifies.

### Test Example

```python
def test_load_mp3_returns_title():
    """Verify that load_mp3 correctly extracts the title from metadata."""
    result = load_mp3("fixtures/sample.mp3")
    assert result["title"] == "Sample Title"
```

## Summary of Rules

1. Source code → `src/`
2. Test code → `test/`
3. Every method/function must have a docstring or comment
4. All code and comments written in English
5. When modifying any file in `src/`, run the related test script(s) in `test/` and confirm all tests pass before committing.

```bash
# Run all tests
python -m unittest discover -s test -v
```

6. When `src/main_window.ui` or `src/main_window.py` is modified, regenerate `docs/ui-preview.jpg` and commit it before pushing.

```bash
# Regenerate UI preview image
python -c "
from PIL import Image, ImageDraw, ImageFont, ImageFilter
# ... (see ui-preview generation script)
"
# Or simply run the generation script if extracted separately
```
