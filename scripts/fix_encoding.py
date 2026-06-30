#!/usr/bin/env python3
"""
Script to scan and fix the encoding of all .py and .json files in the project.
It ensures that all files are saved in UTF-8 and have the required coding header.
"""

import os
from pathlib import Path
import shutil

# Project root is the parent of the scripts folder
ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {".py", ".json", ".txt"}
EXCLUDE_DIRS = {".git", ".venv", "__pycache__", "build", "dist", ".pytest_cache", ".claude"}

ENCODING_HEADER = "# -*- coding: utf-8 -*-\n"


def fix_file_encoding(path: Path):
    """Detects and fixes the encoding of a file, converting it to UTF-8 if needed."""
    try:
        # Read the file as binary first
        with open(path, "rb") as f:
            raw_data = f.read()

        if not raw_data:
            return  # Skip empty files

        modified = False
        # Try decoding as UTF-8
        try:
            # Use 'utf-8-sig' to automatically strip the BOM if present
            content = raw_data.decode("utf-8-sig")
            source_encoding = "utf-8"
            # Explicitly remove any remaining \ufeff characters just in case
            # they are not at the very beginning
            if "\ufeff" in content:
                content = content.replace("\ufeff", "")
                modified = True
        except UnicodeDecodeError:
            # If UTF-8 fails, try CP949 (Korean Windows default)
            try:
                content = raw_data.decode("cp949")
                source_encoding = "cp949"
            except UnicodeDecodeError:
                # If both fail, report and skip
                print(f"ERROR: Could not decode {path.relative_to(ROOT)}. Skipping.")
                return

        # For Python files, ensure the encoding header exists at line 1 or 2
        if path.suffix == ".py":
            lines = content.splitlines(keepends=True)
            has_header = False
            for i in range(min(2, len(lines))):
                if "coding:" in lines[i] or "-*- coding:" in lines[i]:
                    has_header = True
                    # If it's not utf-8 header, update it
                    if "utf-8" not in lines[i].lower():
                        lines[i] = ENCODING_HEADER
                        modified = True
                    break

            if not has_header:
                # Add header at the top
                # If there's a shebang, put it after the shebang
                if lines and lines[0].startswith("#!"):
                    lines.insert(1, ENCODING_HEADER)
                else:
                    lines.insert(0, ENCODING_HEADER)
                modified = True

            if modified:
                content = "".join(lines)

        # If it was not UTF-8 originally, or if we modified the header, save it
        if source_encoding != "utf-8" or modified:
            # Make a backup first
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)

            # Save as UTF-8
            with open(path, "w", encoding="utf-8", errors="strict") as f:
                f.write(content)

            action = "Converted & Adjusted" if modified else "Converted"
            print(f"FIXED: {path.relative_to(ROOT)} ({source_encoding} -> utf-8) - {action}")
            # Remove backup if it's successful (uncomment if you want auto-cleanup)
            # os.remove(backup_path)
        elif modified:
            # Already UTF-8 but header was missing/wrong
            with open(path, "w", encoding="utf-8", errors="strict") as f:
                f.write(content)
            print(f"ADJUSTED: {path.relative_to(ROOT)} (Added/Fixed UTF-8 header)")

    except Exception as e:
        print(f"FAILED: {path.relative_to(ROOT)}: {e}")


def main():
    print(f"Starting encoding fix in: {ROOT}\n")
    for root, dirs, files in os.walk(ROOT):
        # Filter excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            path = Path(root) / file
            if path.suffix in EXTENSIONS:
                fix_file_encoding(path)

    print("\nScan complete. Backup files (.bak) were created for any converted files.")


if __name__ == "__main__":
    main()
