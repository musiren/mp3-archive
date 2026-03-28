"""
mp3_manager.py - MP3 file scanner and SQLite manager, usable as a library.

Intended for use with PyQt via the Mp3Manager class.
The class supports context manager usage and an optional progress
callback so it can be driven from a QThread without coupling to Qt.

Example (PyQt):
    class ScanWorker(QThread):
        progress = pyqtSignal(int, int, str)   # current, total, path
        finished = pyqtSignal(int)

        def __init__(self, manager, directory):
            super().__init__()
            self.manager = manager
            self.directory = directory

        def run(self):
            count = self.manager.scan(
                self.directory,
                progress_callback=lambda cur, tot, p: self.progress.emit(cur, tot, p),
            )
            self.finished.emit(count)

    manager = Mp3Manager("mp3_archive.db")
    worker = ScanWorker(manager, "/music")
    worker.start()

CLI usage:
    python src/mp3_manager.py <directory_path> [--db <db_path>] [--list]
"""

import argparse
import datetime
import os
import sqlite3
from typing import Callable

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, ID3NoHeaderError


DB_DEFAULT = "mp3_archive.db"


class Mp3Manager:
    """
    High-level interface for scanning MP3 files and persisting metadata.

    Wraps all SQLite operations and MP3 parsing behind a clean API
    that is easy to use from PyQt widgets or worker threads.

    Supports the context manager protocol for automatic connection cleanup:
        with Mp3Manager("archive.db") as mgr:
            mgr.scan("/music")
            files = mgr.list_files()
    """

    def __init__(self, db_path: str = DB_DEFAULT) -> None:
        """
        Open the SQLite database and ensure the schema exists.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to 'mp3_archive.db' in the working directory.
        """
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        _create_table(self._conn)

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "Mp3Manager":
        """Return self to support 'with Mp3Manager(...) as mgr' usage."""
        return self

    def __exit__(self, *_) -> None:
        """Close the database connection when exiting the with-block."""
        self.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        directory: str,
        progress_callback: Callable[[int, int, str], None] | None = None,
        force: bool = False,
    ) -> tuple[int, int]:
        """
        Recursively scan a directory for MP3 files and update the database.

        By default runs an incremental scan: files already in the database
        whose file_modified_at timestamp has not changed are skipped, so
        only new or modified files are processed.  Pass force=True to
        re-read every file regardless of its stored timestamp.

        All inserts are batched into a single transaction for performance.

        Args:
            directory:         Root directory path to scan.
            progress_callback: Optional callable invoked for each file found.
                               Signature: callback(current, total, file_path)
            force:             When True, ignore cached timestamps and process
                               every file (full rescan).

        Returns:
            A tuple (processed, skipped) where processed is the number of
            files that were read and saved, and skipped is the number of
            unchanged files that were left untouched.
        """
        mp3_paths = [
            os.path.join(root, f)
            for root, _, files in os.walk(directory)
            for f in files
            if f.lower().endswith(".mp3")
        ]
        total = len(mp3_paths)

        # Build a {path: file_modified_at} cache from the DB for quick lookup.
        cached_mtime: dict[str, str] = {}
        if not force:
            cursor = self._conn.execute(
                "SELECT path, file_modified_at FROM mp3_files"
            )
            cached_mtime = {row[0]: row[1] for row in cursor}

        def _current_mtime(file_path: str) -> str:
            """Return the file's mtime as an ISO-8601 string."""
            import datetime as _dt
            return _dt.datetime.fromtimestamp(
                os.path.getmtime(file_path)
            ).strftime("%Y-%m-%d %H:%M:%S")

        processed = 0
        skipped   = 0

        for idx, file_path in enumerate(mp3_paths, start=1):
            if not force:
                mtime = _current_mtime(file_path)
                if cached_mtime.get(file_path) == mtime:
                    skipped += 1
                    if progress_callback:
                        progress_callback(idx, total, file_path)
                    continue

            info = _get_mp3_info(file_path)
            _save_to_db(self._conn, info, commit=False)
            processed += 1

            if progress_callback:
                progress_callback(idx, total, file_path)

        self._conn.commit()
        return processed, skipped

    def list_files(self) -> list[dict]:
        """
        Retrieve all MP3 records from the database.

        Returns:
            List of row dictionaries ordered by artist and title.
            Each dict contains: id, filename, title, artist,
            album, duration, filesize.
        """
        return _list_files(self._conn)

    def search(self, keyword: str) -> list[dict]:
        """
        Search MP3 records by keyword.

        Performs a case-insensitive substring match against filename,
        title, artist, and album fields.

        Args:
            keyword: The search term to look for.

        Returns:
            List of matching row dictionaries ordered by artist and title.
        """
        return _search_files(self._conn, keyword)

    def delete(self, path: str) -> None:
        """
        Remove an MP3 record from the database by its file path.

        Args:
            path: The exact file path stored in the database.
        """
        self._conn.execute("DELETE FROM mp3_files WHERE path = ?", (path,))
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()


# ------------------------------------------------------------------
# Internal helpers (module-private)
# ------------------------------------------------------------------

def _create_table(conn: sqlite3.Connection) -> None:
    """
    Create the mp3_files table if it does not already exist.

    Args:
        conn: Active SQLite connection.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mp3_files (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            path             TEXT UNIQUE NOT NULL,
            filename         TEXT NOT NULL,
            title            TEXT,
            artist           TEXT,
            album            TEXT,
            duration         REAL,
            filesize         INTEGER,
            file_created_at  TEXT,
            file_modified_at TEXT
        )
    """)
    # Migrate existing databases that predate the timestamp columns.
    _migrate_add_column(conn, "file_created_at", "TEXT")
    _migrate_add_column(conn, "file_modified_at", "TEXT")
    conn.commit()


def _migrate_add_column(conn: sqlite3.Connection, column: str, col_type: str) -> None:
    """
    Add a column to mp3_files if it does not already exist.

    Args:
        conn:     Active SQLite connection.
        column:   Column name to add.
        col_type: SQLite type string (e.g. 'TEXT', 'REAL').
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(mp3_files)")}
    if column not in existing:
        conn.execute(f"ALTER TABLE mp3_files ADD COLUMN {column} {col_type}")


def _get_mp3_info(file_path: str) -> dict:
    """
    Extract metadata from a single MP3 file.

    Args:
        file_path: Absolute or relative path to the MP3 file.

    Returns:
        Dictionary with keys: path, filename, title, artist,
        album, duration, filesize. Missing tags are stored as None.
    """
    def _ts(epoch: float) -> str:
        """Convert a POSIX timestamp to an ISO-8601 local-time string."""
        return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")

    info = {
        "path": file_path,
        "filename": os.path.basename(file_path),
        "title": None,
        "artist": None,
        "album": None,
        "duration": None,
        "filesize": os.path.getsize(file_path),
        "file_created_at": _ts(os.path.getctime(file_path)),
        "file_modified_at": _ts(os.path.getmtime(file_path)),
    }

    try:
        audio = MP3(file_path)
        info["duration"] = round(audio.info.length, 2)
    except Exception:
        pass

    try:
        tags = ID3(file_path)
        info["title"] = str(tags.get("TIT2", "")).strip() or None
        info["artist"] = str(tags.get("TPE1", "")).strip() or None
        info["album"] = str(tags.get("TALB", "")).strip() or None
    except ID3NoHeaderError:
        pass

    # Fall back to filename parsing when tags are missing.
    # Expected format: "Artist - Title.mp3"
    if info["title"] is None or info["artist"] is None:
        _parse_filename_fallback(info)

    return info


def _parse_filename_fallback(info: dict) -> None:
    """
    Attempt to extract artist and title from the filename when ID3 tags are absent.

    The expected filename format is "Artist - Title.mp3".
    The separator is " - " (space-hyphen-space).
    If the filename does not contain the separator, only the title is inferred
    from the stem (filename without extension).

    Args:
        info: Metadata dictionary to update in-place.
    """
    stem = os.path.splitext(info["filename"])[0]
    separator = " - "
    if separator in stem:
        parts = stem.split(separator, maxsplit=1)
        if info["artist"] is None:
            info["artist"] = parts[0].strip() or None
        if info["title"] is None:
            info["title"] = parts[1].strip() or None
    else:
        if info["title"] is None:
            info["title"] = stem.strip() or None


def _save_to_db(conn: sqlite3.Connection, info: dict, commit: bool = True) -> None:
    """
    Insert or replace an MP3 record in the database.

    Args:
        conn:   Active SQLite connection.
        info:   Dictionary as returned by _get_mp3_info().
        commit: If True (default), commit immediately after the insert.
                Pass False when batching many inserts; caller must commit.
    """
    conn.execute("""
        INSERT OR REPLACE INTO mp3_files
            (path, filename, title, artist, album, duration, filesize,
             file_created_at, file_modified_at)
        VALUES
            (:path, :filename, :title, :artist, :album, :duration, :filesize,
             :file_created_at, :file_modified_at)
    """, info)
    if commit:
        conn.commit()


def _search_files(conn: sqlite3.Connection, keyword: str) -> list[dict]:
    """
    Search mp3_files rows where keyword appears in filename, title, artist, or album.

    The match is case-insensitive (SQLite LIKE is case-insensitive for ASCII).

    Args:
        conn:    Active SQLite connection.
        keyword: Search term; partial matches are included.

    Returns:
        List of matching row dictionaries ordered by artist and title.
    """
    pattern = f"%{keyword}%"
    cursor = conn.execute("""
        SELECT id, path, filename, title, artist, album, duration, filesize,
               file_created_at, file_modified_at
        FROM mp3_files
        WHERE filename LIKE ?
           OR title    LIKE ?
           OR artist   LIKE ?
           OR album    LIKE ?
        ORDER BY artist, title
    """, (pattern, pattern, pattern, pattern))
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _list_files(conn: sqlite3.Connection) -> list[dict]:
    """
    Retrieve all rows from mp3_files ordered by artist and title.

    Args:
        conn: Active SQLite connection.

    Returns:
        List of row dictionaries.
    """
    cursor = conn.execute("""
        SELECT id, path, filename, title, artist, album, duration, filesize,
               file_created_at, file_modified_at
        FROM mp3_files
        ORDER BY artist, title
    """)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _main() -> None:
    """Parse CLI arguments and run the scan or list operation."""
    parser = argparse.ArgumentParser(description="MP3 file manager using SQLite")
    parser.add_argument("directory", nargs="?", help="Directory to scan for MP3 files")
    parser.add_argument("--db", default=DB_DEFAULT, help="SQLite database file path")
    parser.add_argument("--list", action="store_true", help="List all stored MP3 files")
    args = parser.parse_args()

    with Mp3Manager(args.db) as mgr:
        if args.directory:
            if not os.path.isdir(args.directory):
                print(f"Error: '{args.directory}' is not a valid directory.")
                return

            def on_progress(current: int, total: int, path: str) -> None:
                """Print scan progress to stdout."""
                print(f"[{current}/{total}] {path}")

            count = mgr.scan(args.directory, progress_callback=on_progress)
            print(f"\nSaved {count} MP3 file(s) to '{args.db}'.")

        if args.list:
            files = mgr.list_files()
            if not files:
                print("No MP3 files in database.")
            else:
                print(f"{'ID':<4} {'Filename':<40} {'Artist':<20} {'Title':<30} {'Duration':>8}")
                print("-" * 106)
                for f in files:
                    duration = f"{f['duration']:.1f}s" if f["duration"] else "-"
                    print(
                        f"{f['id']:<4} {f['filename']:<40} {str(f['artist'] or '-'):<20} "
                        f"{str(f['title'] or '-'):<30} {duration:>8}"
                    )


if __name__ == "__main__":
    _main()
