"""
main.py - Entry point for the MP3 Archive Manager desktop application.

Usage:
    python main.py [--db <db_path>]
"""

import sys
import os

# Add src/ to the module search path so imports resolve correctly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from main_window import main  # noqa: E402

if __name__ == "__main__":
    main()
