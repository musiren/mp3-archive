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

## ⚠️ 반드시 지켜야 할 규칙

> 아래 규칙들은 예외 없이 항상 적용된다.

### 1. UI 파일 변경 시 반드시 ui-preview.jpg 를 업데이트한다

`src/main_window.ui` 또는 `src/main_window.py` 가 변경된 경우,
커밋 및 푸시 **전에** `docs/ui-preview.jpg` 를 재생성하고 함께 커밋해야 한다.
프리뷰 이미지 업데이트 없이 UI 변경을 커밋하지 않는다.

```bash
# 프리뷰 이미지 재생성
python -c "
from PIL import Image, ImageDraw, ImageFont
# ... current UI layout rendering logic
"
```

### 2. 커밋 전 반드시 테스트를 통과한다

`src/` 의 파일을 수정한 경우, 커밋 전에 반드시 전체 테스트를 실행하고
모든 테스트가 통과하는지 확인한다.

```bash
python -m unittest discover -s test -v
```

### 3. 메서드 변경 시 반드시 테스트 코드도 함께 수정한다

`src/` 의 메서드·함수를 **추가·삭제·수정**한 경우,
반드시 `test/` 의 관련 테스트 코드도 같은 커밋에 함께 수정해야 한다.
테스트 코드 수정 없이 구현 코드만 커밋하지 않는다.

- 메서드 **추가** → 해당 동작을 검증하는 테스트 추가
- 메서드 **삭제** → 해당 테스트 삭제 또는 관련 케이스 제거
- 시그니처·동작 **변경** → 영향받는 테스트 업데이트

---

## Summary of Rules

1. Source code → `src/`
2. Test code → `test/`
3. Every method/function must have a docstring or comment
4. All code and comments written in English
5. **[MANDATORY]** Run all tests and confirm they pass before every commit to `src/`.
6. **[MANDATORY]** Regenerate `docs/ui-preview.jpg` and include it in the commit whenever `src/main_window.ui` or `src/main_window.py` changes.
7. **[MANDATORY]** When any method/function in `src/` is added, removed, or changed, update the corresponding tests in `test/` in the same commit. Never commit implementation changes without matching test updates.
