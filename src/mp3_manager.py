"""
mp3_manager.py - Scan a directory for MP3 files and manage their info in SQLite.

Usage:
    python src/mp3_manager.py <directory_path> [--db <db_path>] [--list]
"""

import argparse
import os
import sqlite3

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, ID3NoHeaderError


DB_DEFAULT = "mp3_archive.db"


def create_table(conn: sqlite3.Connection) -> None:
    """
    Create the mp3_files table if it does not already exist.

    Args:
        conn: Active SQLite connection.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mp3_files (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            path     TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            title    TEXT,
            artist   TEXT,
            album    TEXT,
            duration REAL,
            filesize INTEGER
        )
    """)
    conn.commit()


def get_mp3_info(file_path: str) -> dict:
    """
    Extract metadata from an MP3 file.

    Args:
        file_path: Absolute path to the MP3 file.

    Returns:
        A dictionary with keys: path, filename, title, artist,
        album, duration, filesize.
    """
    info = {
        "path": file_path,
        "filename": os.path.basename(file_path),
        "title": None,
        "artist": None,
        "album": None,
        "duration": None,
        "filesize": os.path.getsize(file_path),
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

    return info


def save_to_db(conn: sqlite3.Connection, info: dict) -> None:
    """
    Insert or replace an MP3 record in the database.

    Args:
        conn: Active SQLite connection.
        info: Dictionary returned by get_mp3_info().
    """
    conn.execute("""
        INSERT OR REPLACE INTO mp3_files
            (path, filename, title, artist, album, duration, filesize)
        VALUES
            (:path, :filename, :title, :artist, :album, :duration, :filesize)
    """, info)
    conn.commit()


def scan_directory(conn: sqlite3.Connection, directory: str) -> int:
    """
    Recursively scan a directory for MP3 files and save each to the database.

    Args:
        conn:      Active SQLite connection.
        directory: Root directory path to scan.

    Returns:
        Number of MP3 files found and saved.
    """
    count = 0
    for root, _, files in os.walk(directory):
        for filename in files:
            if filename.lower().endswith(".mp3"):
                file_path = os.path.join(root, filename)
                info = get_mp3_info(file_path)
                save_to_db(conn, info)
                count += 1
    return count


def list_files(conn: sqlite3.Connection) -> list[dict]:
    """
    Retrieve all MP3 records from the database.

    Args:
        conn: Active SQLite connection.

    Returns:
        List of row dictionaries ordered by artist and title.
    """
    cursor = conn.execute("""
        SELECT id, filename, title, artist, album, duration, filesize
        FROM mp3_files
        ORDER BY artist, title
    """)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def open_db(db_path: str) -> sqlite3.Connection:
    """
    Open a SQLite database and ensure the schema is ready.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An active SQLite connection.
    """
    conn = sqlite3.connect(db_path)
    create_table(conn)
    return conn


def main() -> None:
    """Parse CLI arguments and run the scan or list operation."""
    parser = argparse.ArgumentParser(description="MP3 file manager using SQLite")
    parser.add_argument("directory", nargs="?", help="Directory to scan for MP3 files")
    parser.add_argument("--db", default=DB_DEFAULT, help="SQLite database file path")
    parser.add_argument("--list", action="store_true", help="List all stored MP3 files")
    args = parser.parse_args()

    conn = open_db(args.db)

    if args.directory:
        if not os.path.isdir(args.directory):
            print(f"Error: '{args.directory}' is not a valid directory.")
            return
        count = scan_directory(conn, args.directory)
        print(f"Scanned and saved {count} MP3 file(s) to '{args.db}'.")

    if args.list:
        files = list_files(conn)
        if not files:
            print("No MP3 files in database.")
        else:
            print(f"{'ID':<4} {'Filename':<40} {'Artist':<20} {'Title':<30} {'Duration':>8}")
            print("-" * 106)
            for f in files:
                duration = f"{f['duration']:.1f}s" if f["duration"] else "-"
                print(f"{f['id']:<4} {f['filename']:<40} {str(f['artist'] or '-'):<20} "
                      f"{str(f['title'] or '-'):<30} {duration:>8}")

    conn.close()


if __name__ == "__main__":
    main()
