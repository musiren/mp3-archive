"""
tree_util.py - Build a flat, virtualizable directory tree from file paths.

GUI-independent (os.path only) so the folder-tree logic can be unit-tested
without Kivy. The Android UI feeds the returned rows to a RecycleView.
"""

import os


def build_tree_rows(files: list, base: str, expanded: set) -> list:
    """
    Flatten the directory hierarchy of *files* into RecycleView tree rows.

    Each file's path is taken relative to *base* (the scanned root). Folders are
    emitted before files at each level; a folder's children are only emitted
    when the folder's key is in *expanded* (collapsed otherwise), which keeps
    the row list small for large trees.

    Args:
        files:    List of record dicts, each with a "path" key.
        base:     Absolute path of the scanned root (paths are shown relative
                  to it). May be empty/None to use the full path.
        expanded: Set of folder keys (slash-joined relative dir paths) that are
                  currently expanded.

    Returns:
        A list of row dicts, each with:
          "text"   - indented label with a ▶/▼ (folder) or ♪ (file) glyph,
          "is_dir" - True for a folder row,
          "path"   - the file path (files only; "" for folders),
          "key"    - the folder key (folders only; "" for files).
    """
    tree: dict = {}
    for f in files:
        path = f["path"]
        try:
            rel = os.path.relpath(path, base) if base else path
        except ValueError:
            rel = path
        parts = [p for p in rel.replace("\\", "/").split("/") if p and p != "."]
        if not parts:
            continue
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault("__files__", []).append((parts[-1], path))

    rows: list = []

    def _walk(node: dict, level: int, prefix: str) -> None:
        """Depth-first emit folder rows (recursing if expanded) then file rows."""
        indent = "    " * level
        for dname in sorted(k for k in node if k != "__files__"):
            key = (prefix + "/" + dname) if prefix else dname
            is_expanded = key in expanded
            glyph = "▼ " if is_expanded else "▶ "
            rows.append({"text": indent + glyph + dname,
                         "is_dir": True, "path": "", "key": key})
            if is_expanded:
                _walk(node[dname], level + 1, key)
        for fname, fpath in sorted(node.get("__files__", []),
                                   key=lambda x: x[0].lower()):
            rows.append({"text": indent + "♪ " + fname,
                         "is_dir": False, "path": fpath, "key": ""})

    _walk(tree, 0, "")
    return rows


def files_under_folder(files: list, base: str, key: str) -> list:
    """
    Return the file records that live under a tree folder, recursively.

    Used by the 트리 view's "재생목록에 추가" folder action: *key* is the
    slash-joined relative folder path emitted by build_tree_rows (e.g.
    "260419" or "260419/live"), and this returns every record whose path is
    inside that folder (including nested subfolders), ordered by relative path
    so the result matches the tree's grouped display order.

    Args:
        files: Record dicts each with a "path" key.
        base:  Absolute scanned-root path the keys are relative to (matches the
               *base* passed to build_tree_rows). May be empty/None.
        key:   The folder key to collect files under.

    Returns:
        The matching records, ordered by their case-folded relative path. Empty
        when *key* is empty or no file lies under it.
    """
    if not key:
        return []
    prefix = key.replace("\\", "/") + "/"
    matched = []
    for record in files:
        path = record.get("path", "")
        try:
            rel = os.path.relpath(path, base) if base else path
        except ValueError:
            rel = path
        # Normalise exactly like build_tree_rows (split on "/", drop empty/"."
        # segments, rejoin) so the folder keys agree in BOTH cases: a real
        # relative base, and an empty base where rel is the full path (e.g.
        # after an app relaunch with no scan dir) — otherwise the leading "/"
        # of an absolute path makes the prefix never match.
        parts = [p for p in rel.replace("\\", "/").split("/") if p and p != "."]
        rel = "/".join(parts)
        if rel.startswith(prefix):
            matched.append((rel, record))
    matched.sort(key=lambda pair: pair[0].lower())
    return [record for _, record in matched]
