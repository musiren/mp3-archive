"""
mp3_manager.py - Audio file scanner and SQLite manager, usable as a library.

Supports MP3, FLAC, OGG, WAV, AAC, M4A, WMA, and Opus files.
Intended for use with PyQt via the Mp3Manager class.

Example (PyQt):
    class ScanWorker(QThread):
        progress = pyqtSignal(int, int, str)   # current, total, path
        finished = pyqtSignal(int, int)        # processed, skipped

        def __init__(self, manager, directory, force=False):
            super().__init__()
            self.manager = manager
            self.directory = directory
            self.force = force

        def run(self):
            processed, skipped = self.manager.scan(
                self.directory,
                progress_callback=lambda cur, tot, p: self.progress.emit(cur, tot, p),
                force=self.force,
            )
            self.finished.emit(processed, skipped)

    manager = Mp3Manager("archive.db")
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

from mutagen import File as MutagenFile

from audio_meta import fix_mojibake


DB_DEFAULT = "mp3_archive.db"

# All file extensions this manager recognises.
SUPPORTED_EXTENSIONS = {
    ".mp3", ".flac", ".ogg", ".wav",
    ".aac", ".m4a", ".wma", ".opus",
}


class Mp3Manager:
    """
    High-level interface for scanning audio files and persisting metadata.

    Supports MP3, FLAC, OGG, WAV, AAC, M4A, WMA, and Opus formats.
    Wraps all SQLite operations and tag parsing behind a clean API
    suitable for PyQt widgets and worker threads.

    Supports the context manager protocol for automatic cleanup:
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
    ) -> tuple[int, int, int]:
        """
        Recursively scan a directory for audio files and update the database.

        Recognises: .mp3 .flac .ogg .wav .aac .m4a .wma .opus

        By default runs an incremental scan: files already in the database
        whose file_modified_at timestamp has not changed are skipped.
        Pass force=True to re-read every file regardless of timestamp and
        to remove DB records for files that no longer exist on disk.

        All inserts are batched into a single transaction for performance.

        Args:
            directory:         Root directory path to scan.
            progress_callback: Optional callable(current, total, file_path).
            force:             When True, ignore cached timestamps and remove
                               stale records for missing files.

        Returns:
            A tuple (processed, skipped, removed).
        """
        audio_paths = [
            os.path.join(root, f)
            for root, _, files in os.walk(directory)
            for f in files
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
        ]
        total = len(audio_paths)

        cached_mtime: dict[str, str] = {}
        if not force:
            cursor = self._conn.execute(
                "SELECT path, file_modified_at FROM audio_files"
            )
            cached_mtime = {row[0]: row[1] for row in cursor}

        def _current_mtime(file_path: str) -> str:
            """Return the file's mtime as an ISO-8601 string."""
            return datetime.datetime.fromtimestamp(
                os.path.getmtime(file_path)
            ).strftime("%Y-%m-%d %H:%M:%S")

        processed = 0
        skipped   = 0

        for idx, file_path in enumerate(audio_paths, start=1):
            if not force:
                mtime = _current_mtime(file_path)
                if cached_mtime.get(file_path) == mtime:
                    skipped += 1
                    if progress_callback:
                        progress_callback(idx, total, file_path)
                    continue

            info = _get_audio_info(file_path)
            _save_to_db(self._conn, info, commit=False)
            processed += 1

            if progress_callback:
                progress_callback(idx, total, file_path)

        # On a full scan, remove DB records whose files no longer exist
        # under the scanned directory.
        removed = 0
        if force:
            scanned_set = set(audio_paths)
            dir_prefix = os.path.normpath(directory) + os.sep
            cursor = self._conn.execute("SELECT path FROM audio_files")
            stale = [
                row[0] for row in cursor
                if os.path.normpath(row[0]).startswith(dir_prefix)
                and row[0] not in scanned_set
            ]
            for path in stale:
                self._conn.execute(
                    "DELETE FROM audio_files WHERE path = ?", (path,)
                )
                removed += 1

        self._conn.commit()
        return processed, skipped, removed

    def list_files(self) -> list[dict]:
        """
        Retrieve all audio records from the database.

        Returns:
            List of row dictionaries ordered by artist and title.
        """
        return _list_files(self._conn)

    def search(self, keyword: str, filename_only: bool = False) -> list[dict]:
        """
        Search audio records by keyword.

        Performs a case-insensitive substring match.  By default searches
        all tag fields (filename, title, artist, album, genre, year, comment).
        Pass filename_only=True to restrict the match to the filename column.

        Args:
            keyword:       The search term to look for.
            filename_only: When True, only the filename column is searched.

        Returns:
            List of matching row dictionaries ordered by artist and title.
        """
        return _search_files(self._conn, keyword, filename_only=filename_only)

    def get_by_path(self, path: str) -> dict | None:
        """
        Return the DB record for a single file path, or None if not found.

        Args:
            path: Absolute path of the audio file.

        Returns:
            Row dictionary with the same keys as list_files(), or None.
        """
        cursor = self._conn.execute(
            """
            SELECT id, path, filename, title, artist, album, genre, year, comment,
                   duration, filesize, file_created_at, file_modified_at
            FROM audio_files
            WHERE path = ?
            """,
            (path,),
        )
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row else None

    def update_file_tags(
        self,
        path: str,
        title: str | None,
        artist: str | None,
        album: str | None,
    ) -> None:
        """
        Write tags to an audio file and update the corresponding DB record.

        Uses mutagen's generic File() interface so the write works for all
        supported formats.  Only fields with non-None values are written.

        Args:
            path:   Absolute path to the audio file.
            title:  New title value, or None to leave unchanged.
            artist: New artist value, or None to leave unchanged.
            album:  New album value, or None to leave unchanged.
        """
        try:
            audio = MutagenFile(path, easy=True)
            if audio is not None:
                if title  is not None: audio["title"]  = [title]
                if artist is not None: audio["artist"] = [artist]
                if album  is not None: audio["album"]  = [album]
                audio.save()
        except Exception:
            pass  # File may be read-only, corrupt, or unsupported format

        fields = {k: v for k, v in
                  {"title": title, "artist": artist, "album": album}.items()
                  if v is not None}
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            self._conn.execute(
                f"UPDATE audio_files SET {set_clause} WHERE path = ?",
                list(fields.values()) + [path],
            )
            self._conn.commit()

    def update_tags(self, path: str, tags: dict[str, str]) -> None:
        """
        Write arbitrary easy-tag key/value pairs to a file and sync the DB.

        All keys must use the mutagen easy-tag naming convention (e.g.
        'title', 'artist', 'album', 'genre', 'date', 'comment').
        The DB columns title, artist, album, genre, year, and comment are
        updated automatically; the easy-tag key 'date' maps to the 'year'
        DB column.

        Args:
            path: Absolute path to the audio file.
            tags: Mapping of easy-tag key → new string value.
        """
        if not tags:
            return

        # Write to the audio file first; raise on any error so the DB
        # is never updated when the file write fails.
        audio = MutagenFile(path, easy=True)
        if audio is None:
            raise ValueError(f"mutagen could not open file: {path}")
        for key, val in tags.items():
            audio[key] = [val]
        audio.save()

        # Map easy-tag keys to DB column names
        _KEY_TO_COL = {
            "title":   "title",
            "artist":  "artist",
            "album":   "album",
            "genre":   "genre",
            "date":    "year",
            "comment": "comment",
        }
        db_fields = {
            _KEY_TO_COL[k]: v
            for k, v in tags.items()
            if k in _KEY_TO_COL
        }
        if db_fields:
            set_clause = ", ".join(f"{col} = ?" for col in db_fields)
            self._conn.execute(
                f"UPDATE audio_files SET {set_clause} WHERE path = ?",
                list(db_fields.values()) + [path],
            )
            self._conn.commit()

    def delete(self, path: str) -> None:
        """
        Remove an audio record from the database by its file path.

        Args:
            path: The exact file path stored in the database.
        """
        self._conn.execute("DELETE FROM audio_files WHERE path = ?", (path,))
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()


# ------------------------------------------------------------------
# Internal helpers (module-private)
# ------------------------------------------------------------------

def _create_table(conn: sqlite3.Connection) -> None:
    """
    Ensure the audio_files table exists, migrating from mp3_files if needed.

    Args:
        conn: Active SQLite connection.
    """
    # Migrate: rename legacy mp3_files table to audio_files.
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "mp3_files" in tables and "audio_files" not in tables:
        conn.execute("ALTER TABLE mp3_files RENAME TO audio_files")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS audio_files (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            path             TEXT UNIQUE NOT NULL,
            filename         TEXT NOT NULL,
            title            TEXT,
            artist           TEXT,
            album            TEXT,
            genre            TEXT,
            year             TEXT,
            comment          TEXT,
            duration         REAL,
            filesize         INTEGER,
            file_created_at  TEXT,
            file_modified_at TEXT
        )
    """)
    _migrate_add_column(conn, "file_created_at", "TEXT")
    _migrate_add_column(conn, "file_modified_at", "TEXT")
    _migrate_add_column(conn, "genre", "TEXT")
    _migrate_add_column(conn, "year", "TEXT")
    _migrate_add_column(conn, "comment", "TEXT")
    conn.commit()


def _migrate_add_column(conn: sqlite3.Connection, column: str, col_type: str) -> None:
    """
    Add a column to audio_files if it does not already exist.

    Args:
        conn:     Active SQLite connection.
        column:   Column name to add.
        col_type: SQLite type string (e.g. 'TEXT', 'REAL').
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(audio_files)")}
    if column not in existing:
        conn.execute(f"ALTER TABLE audio_files ADD COLUMN {column} {col_type}")


def _get_audio_info(file_path: str) -> dict:
    """
    Extract metadata from a single audio file using mutagen.

    Supports ID3 (MP3), VorbisComment (FLAC/OGG/Opus), MP4 (M4A/AAC),
    ASF (WMA), and falls back to filename parsing when tags are absent.

    Args:
        file_path: Absolute or relative path to the audio file.

    Returns:
        Dictionary with keys: path, filename, title, artist,
        album, duration, filesize, file_created_at, file_modified_at.
    """
    def _ts(epoch: float) -> str:
        """Convert a POSIX timestamp to an ISO-8601 local-time string."""
        return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")

    info = {
        "path":             file_path,
        "filename":         os.path.basename(file_path),
        "title":            None,
        "artist":           None,
        "album":            None,
        "genre":            None,
        "year":             None,
        "comment":          None,
        "duration":         None,
        "filesize":         os.path.getsize(file_path),
        "file_created_at":  _ts(os.path.getctime(file_path)),
        "file_modified_at": _ts(os.path.getmtime(file_path)),
    }

    try:
        # easy=True normalises tag keys to lowercase across all formats.
        audio = MutagenFile(file_path, easy=True)
        if audio is not None:
            if hasattr(audio, "info") and hasattr(audio.info, "length"):
                info["duration"] = round(audio.info.length, 2)
            if audio.tags:
                info["title"]   = _first_tag(audio.tags, "title")
                info["artist"]  = _first_tag(audio.tags, "artist")
                info["album"]   = _first_tag(audio.tags, "album")
                info["genre"]   = _first_tag(audio.tags, "genre")
                info["year"]    = _first_tag(audio.tags, "date")
                info["comment"] = _first_tag(audio.tags, "comment")
    except Exception:
        pass

    if info["title"] is None or info["artist"] is None:
        _parse_filename_fallback(info)

    return info


def _first_tag(tags, key: str) -> str | None:
    """
    Return the first string value for a tag key, or None if absent.

    mutagen's easy=True interface returns list values for all formats.

    Args:
        tags: mutagen tags object.
        key:  Lowercase tag key (e.g. 'title', 'artist', 'album').

    Returns:
        Stripped string value or None.
    """
    val = tags.get(key)
    if not val:
        return None
    text = str(val[0]).strip() if isinstance(val, list) else str(val).strip()
    # Repair CP949/EUC-KR tags that mutagen decoded as Latin-1 (old Korean MP3s).
    return fix_mojibake(text) or None


def _parse_filename_fallback(info: dict) -> None:
    """
    Attempt to extract artist and title from the filename when tags are absent.

    The expected filename format is "Artist - Title.ext".
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
    Insert or replace an audio record in the database.

    Args:
        conn:   Active SQLite connection.
        info:   Dictionary as returned by _get_audio_info().
        commit: If True (default), commit immediately after the insert.
                Pass False when batching; caller must commit.
    """
    conn.execute("""
        INSERT OR REPLACE INTO audio_files
            (path, filename, title, artist, album, genre, year, comment,
             duration, filesize, file_created_at, file_modified_at)
        VALUES
            (:path, :filename, :title, :artist, :album, :genre, :year, :comment,
             :duration, :filesize, :file_created_at, :file_modified_at)
    """, info)
    if commit:
        conn.commit()


def _search_files(
    conn: sqlite3.Connection,
    keyword: str,
    filename_only: bool = False,
) -> list[dict]:
    """
    Search audio_files rows where keyword appears in the selected fields.

    Args:
        conn:          Active SQLite connection.
        keyword:       Search term; partial matches are included.
        filename_only: When True, only the filename column is matched.
                       When False (default), all tag fields are searched.

    Returns:
        List of matching row dictionaries ordered by artist and title.
    """
    pattern = f"%{keyword}%"
    if filename_only:
        cursor = conn.execute("""
            SELECT id, path, filename, title, artist, album, genre, year, comment,
                   duration, filesize, file_created_at, file_modified_at
            FROM audio_files
            WHERE filename LIKE ?
            ORDER BY artist, title
        """, (pattern,))
    else:
        cursor = conn.execute("""
            SELECT id, path, filename, title, artist, album, genre, year, comment,
                   duration, filesize, file_created_at, file_modified_at
            FROM audio_files
            WHERE filename LIKE ?
               OR title    LIKE ?
               OR artist   LIKE ?
               OR album    LIKE ?
               OR genre    LIKE ?
               OR year     LIKE ?
               OR comment  LIKE ?
            ORDER BY artist, title
        """, (pattern, pattern, pattern, pattern, pattern, pattern, pattern))
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _list_files(conn: sqlite3.Connection) -> list[dict]:
    """
    Retrieve all rows from audio_files ordered by artist and title.

    Args:
        conn: Active SQLite connection.

    Returns:
        List of row dictionaries.
    """
    cursor = conn.execute("""
        SELECT id, path, filename, title, artist, album, genre, year, comment,
               duration, filesize, file_created_at, file_modified_at
        FROM audio_files
        ORDER BY artist, title
    """)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _main() -> None:
    """Parse CLI arguments and run the scan or list operation."""
    parser = argparse.ArgumentParser(description="Audio file manager using SQLite")
    parser.add_argument("directory", nargs="?", help="Directory to scan for audio files")
    parser.add_argument("--db", default=DB_DEFAULT, help="SQLite database file path")
    parser.add_argument("--list", action="store_true", help="List all stored audio files")
    args = parser.parse_args()

    with Mp3Manager(args.db) as mgr:
        if args.directory:
            if not os.path.isdir(args.directory):
                print(f"Error: '{args.directory}' is not a valid directory.")
                return

            def on_progress(current: int, total: int, path: str) -> None:
                """Print scan progress to stdout."""
                print(f"[{current}/{total}] {path}")

            processed, skipped = mgr.scan(args.directory, progress_callback=on_progress)
            print(f"\nProcessed {processed}, skipped {skipped} in '{args.db}'.")

        if args.list:
            files = mgr.list_files()
            if not files:
                print("No audio files in database.")
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
