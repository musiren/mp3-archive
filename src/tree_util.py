"""
tree_util.py - Build a flat, virtualizable directory tree from file paths.

GUI-independent (os.path only) so the folder-tree logic can be unit-tested
without Kivy. The Android UI feeds the returned rows to a RecycleView.
"""

import os


def _relative(path: str, base: str) -> str:
    """
    Return *path* relative to *base* with "/" separators.

    Backslashes are normalised to "/" BEFORE the relpath computation: a POSIX
    host treats "\\" as an ordinary character, so a Windows-style path (e.g. a
    `.list` written on a PC) would otherwise never match *base* and the whole
    path would come back as one opaque component.

    Args:
        path: The file path (either separator style).
        base: The scanned-root path, or empty/None to keep the full path.

    Returns:
        The (possibly relative) path using "/" separators only.
    """
    path = (path or "").replace("\\", "/")
    base = (base or "").replace("\\", "/")
    try:
        return os.path.relpath(path, base) if base else path
    except ValueError:
        return path


def build_tree_rows(files: list, base: str, expanded: set) -> list:
    """
    Flatten the directory hierarchy of *files* into RecycleView tree rows.

    Convenience wrapper that builds a throw-away :class:`TreeIndex` and asks
    it for the rows. Callers that re-render the tree repeatedly (expand /
    collapse / selection) should hold on to a TreeIndex instead, so the
    indexing cost is paid once per file list rather than once per tap.

    Args:
        files:    List of record dicts, each with a "path" key.
        base:     Absolute path of the scanned root (paths are shown relative
                  to it). May be empty/None to use the full path.
        expanded: Set of folder keys (slash-joined relative dir paths) that are
                  currently expanded.

    Returns:
        The visible row dicts (see :meth:`TreeIndex.rows`).
    """
    return TreeIndex(files, base).rows(expanded)


class TreeIndex:
    """
    A pre-indexed folder tree for fast expand/collapse/selection updates.

    Building the nested folder structure (with children pre-sorted) and the
    per-folder descendant-path lists costs one O(N) pass over the files; every
    subsequent render then only walks the VISIBLE rows. The previous approach
    rebuilt the whole tree — plus one O(N) folder scan per visible folder row —
    on every tap, which froze the UI on large libraries.
    """

    def __init__(self, files: list, base: str) -> None:
        """
        Index *files* into a nested folder tree.

        Args:
            files: List of record dicts, each with a "path" key.
            base:  Absolute path of the scanned root (paths are shown relative
                   to it). May be empty/None to use the full path.
        """
        self._root = {"dirs": {}, "files": []}
        self._paths: dict = {}    # folder key -> descendant file paths
        for f in files:
            rel = _relative(f.get("path", ""), base)
            parts = [p for p in rel.split("/") if p and p != "."]
            if not parts:
                continue
            node = self._root
            for part in parts[:-1]:
                node = node["dirs"].setdefault(part,
                                               {"dirs": {}, "files": []})
            node["files"].append((parts[-1], f.get("path", "")))
        self._finalise(self._root, "")

    def _finalise(self, node: dict, key: str) -> list:
        """
        Sort *node*'s children and aggregate its descendant file paths.

        Args:
            node: The tree node to finalise (its subtree is finalised too).
            key:  The node's folder key ("" for the root).

        Returns:
            Every file path under *node*, folders first (tree display order).
        """
        node["files"].sort(key=lambda pair: pair[0].lower())
        node["dir_names"] = sorted(node["dirs"])
        paths = []
        for dname in node["dir_names"]:
            child_key = (key + "/" + dname) if key else dname
            paths.extend(self._finalise(node["dirs"][dname], child_key))
        paths.extend(path for _name, path in node["files"])
        if key:
            self._paths[key] = paths
        return paths

    def paths_under(self, key: str) -> list:
        """
        Return every file path under a folder key, recursively (precomputed).

        Args:
            key: The folder key emitted by :meth:`rows` (e.g. "a/live").

        Returns:
            The cached list of descendant file paths (empty for an unknown or
            empty key). The list is shared — callers must not mutate it.
        """
        return self._paths.get(key, []) if key else []

    def rows(self, expanded: set, selected=frozenset()) -> list:
        """
        Build the visible tree rows, walking only the expanded folders.

        Args:
            expanded: Set of folder keys that are currently expanded.
            selected: Set of selected file paths; folder rows are flagged
                      selected when every file under them is selected.

        Returns:
            A list of row dicts, each with:
              "text"     - indented label with a ▶/▼ (folder) or ♪ (file) glyph,
              "is_dir"   - True for a folder row,
              "path"     - the file path (files only; "" for folders),
              "key"      - the folder key (folders only; "" for files),
              "level"    - the indentation depth (0 = top level),
              "selected" - the row's selection flag.
        """
        rows: list = []

        def _walk(node: dict, level: int, prefix: str) -> None:
            """Depth-first emit folder rows (recursing if expanded) then files."""
            indent = "    " * level
            for dname in node["dir_names"]:
                key = (prefix + "/" + dname) if prefix else dname
                is_expanded = key in expanded
                glyph = "▼ " if is_expanded else "▶ "
                paths = self._paths.get(key, ())
                sel = bool(paths) and all(p in selected for p in paths)
                rows.append({"text": indent + glyph + dname, "is_dir": True,
                             "path": "", "key": key, "level": level,
                             "selected": sel})
                if is_expanded:
                    _walk(node["dirs"][dname], level + 1, key)
            for fname, fpath in node["files"]:
                rows.append({"text": indent + "♪ " + fname, "is_dir": False,
                             "path": fpath, "key": "", "level": level,
                             "selected": fpath in selected})

        _walk(self._root, 0, "")
        return rows


def refresh_selection_flags(rows, start: int, selected,
                            paths_under) -> None:
    """
    Recompute the "selected" flags affected by one selection change, in place.

    After toggling the row at *rows[start]* only three groups of rows can have
    changed: the row itself, its visible descendants (when it is a folder),
    and its ancestor folder rows. Updating just those — instead of rebuilding
    the whole row list — keeps selection taps O(affected rows) on big trees.
    The caller re-renders the mutated rows (e.g. RecycleView's
    ``refresh_from_data``).

    Args:
        rows:        The visible row dicts (as produced by TreeIndex.rows),
                     mutated in place.
        start:       Index of the toggled row (a no-op when out of range).
        selected:    The set of selected file paths (already updated).
        paths_under: Callable mapping a folder key to its descendant file
                     paths (e.g. ``TreeIndex.paths_under``).
    """
    if not 0 <= start < len(rows):
        return

    def _dir_selected(key: str) -> bool:
        """Return True when every file under *key* is selected."""
        paths = paths_under(key)
        return bool(paths) and all(p in selected for p in paths)

    row = rows[start]
    level = row.get("level", 0)
    if row.get("is_dir"):
        row["selected"] = _dir_selected(row.get("key", ""))
        # Visible descendants form a contiguous block of deeper rows.
        i = start + 1
        while i < len(rows) and rows[i].get("level", 0) > level:
            d = rows[i]
            d["selected"] = (_dir_selected(d.get("key", ""))
                             if d.get("is_dir")
                             else d.get("path", "") in selected)
            i += 1
    else:
        row["selected"] = row.get("path", "") in selected
    # Ancestors: scanning backwards, the nearest row of each shallower level.
    walk_level = level
    for i in range(start - 1, -1, -1):
        if walk_level <= 0:
            break
        d = rows[i]
        if d.get("is_dir") and d.get("level", 0) < walk_level:
            walk_level = d.get("level", 0)
            d["selected"] = _dir_selected(d.get("key", ""))


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
        rel = _relative(record.get("path", ""), base)
        # Normalise exactly like build_tree_rows (split on "/", drop empty/"."
        # segments, rejoin) so the folder keys agree in BOTH cases: a real
        # relative base, and an empty base where rel is the full path (e.g.
        # after an app relaunch with no scan dir) — otherwise the leading "/"
        # of an absolute path makes the prefix never match.
        parts = [p for p in rel.split("/") if p and p != "."]
        rel = "/".join(parts)
        if rel.startswith(prefix):
            matched.append((rel, record))
    matched.sort(key=lambda pair: pair[0].lower())
    return [record for _, record in matched]
