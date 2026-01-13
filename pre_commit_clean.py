#!/usr/bin/env python3
"""Pre-commit housekeeping script for Overlord11.

This script handles:
- Cleaning temporary files (tmpclaude-*, *-cwd, etc.)
- Running checks and tests (TODO)
- Generating reports (TODO)
- Other housekeeping tasks (TODO)

Usage:
    python pre_commit_clean.py [options]

Options:
    --dry-run       Show what would be deleted without deleting
    --verbose, -v   Show detailed output
    --all           Clean all temporary files across all subdirectories
    --help, -h      Show this help message
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple


# Patterns for temporary files to clean
TEMP_PATTERNS = [
    "tmpclaude-*",      # Claude temporary files
    "*-cwd",            # Working directory temp files
    "*.tmp",            # Generic temp files
    "*.pyc",            # Python bytecode
    "__pycache__",      # Python cache directories
    ".pytest_cache",    # Pytest cache
    ".mypy_cache",      # Mypy cache
    ".ruff_cache",      # Ruff cache
    "*.log",            # Log files (be careful with this one)
]

# Directories to skip during cleaning
SKIP_DIRS = [
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
]


class PreCommitCleaner:
    """Handles pre-commit cleaning and housekeeping tasks."""

    def __init__(self, root_dir: Path, dry_run: bool = False, verbose: bool = False):
        """Initialize the cleaner.

        Args:
            root_dir: Root directory to clean
            dry_run: If True, only show what would be deleted
            verbose: If True, show detailed output
        """
        self.root_dir = root_dir
        self.dry_run = dry_run
        self.verbose = verbose
        self.deleted_count = 0
        self.deleted_size = 0

    def log(self, message: str, force: bool = False) -> None:
        """Log a message if verbose mode is enabled.

        Args:
            message: Message to log
            force: If True, always print regardless of verbose setting
        """
        if self.verbose or force:
            print(message)

    def get_file_size(self, path: Path) -> int:
        """Get file size, returning 0 for directories or errors.

        Args:
            path: Path to get size of

        Returns:
            Size in bytes
        """
        try:
            if path.is_file():
                return path.stat().st_size
            return 0
        except (OSError, PermissionError):
            return 0

    def find_temp_files(self, patterns: List[str] = None) -> List[Tuple[Path, int]]:
        """Find all temporary files matching patterns.

        Args:
            patterns: List of glob patterns to match

        Returns:
            List of (path, size) tuples (deduplicated)
        """
        if patterns is None:
            patterns = TEMP_PATTERNS

        found_paths = set()
        found_files = []

        for pattern in patterns:
            for path in self.root_dir.rglob(pattern):
                # Skip if in a directory we should skip
                if any(skip_dir in path.parts for skip_dir in SKIP_DIRS):
                    continue

                # Skip if already found (deduplicate)
                if path in found_paths:
                    continue

                found_paths.add(path)
                size = self.get_file_size(path)
                found_files.append((path, size))
                self.log(f"  Found: {path} ({self._format_size(size)})")

        return found_files

    def clean_temp_files(self, patterns: List[str] = None) -> Tuple[int, int]:
        """Clean temporary files matching patterns.

        Args:
            patterns: List of glob patterns to match

        Returns:
            Tuple of (files_deleted, bytes_deleted)
        """
        if patterns is None:
            patterns = TEMP_PATTERNS

        print(f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning temporary files...")
        self.log(f"Root directory: {self.root_dir}")
        self.log(f"Patterns: {patterns}")

        found_files = self.find_temp_files(patterns)

        if not found_files:
            print("No temporary files found.")
            return 0, 0

        deleted_count = 0
        deleted_size = 0

        for path, size in found_files:
            try:
                if self.dry_run:
                    self.log(f"  Would delete: {path}")
                else:
                    if path.is_dir():
                        import shutil
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    self.log(f"  Deleted: {path}")

                deleted_count += 1
                deleted_size += size

            except (OSError, PermissionError) as e:
                print(f"  Error deleting {path}: {e}")

        action = "Would delete" if self.dry_run else "Deleted"
        print(f"{action} {deleted_count} files/directories ({self._format_size(deleted_size)})")

        return deleted_count, deleted_size

    def clean_tmpclaude_files(self) -> Tuple[int, int]:
        """Clean specifically tmpclaude temporary files.

        Returns:
            Tuple of (files_deleted, bytes_deleted)
        """
        return self.clean_temp_files(["tmpclaude-*", "*-cwd"])

    def _format_size(self, size_bytes: int) -> str:
        """Format size in human-readable format.

        Args:
            size_bytes: Size in bytes

        Returns:
            Human-readable size string
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def run_checks(self) -> bool:
        """Run pre-commit checks.

        Returns:
            True if all checks pass

        TODO: Implement actual checks
        """
        print("\n[TODO] Running checks...")
        # Future: Add linting, type checking, etc.
        return True

    def run_tests(self) -> bool:
        """Run test suite.

        Returns:
            True if all tests pass

        TODO: Implement actual test running
        """
        print("\n[TODO] Running tests...")
        # Future: Add pytest execution
        return True

    def generate_report(self) -> None:
        """Generate pre-commit report.

        TODO: Implement actual reporting
        """
        print("\n[TODO] Generating report...")
        # Future: Add report generation

    def run_all(self) -> bool:
        """Run all pre-commit tasks.

        Returns:
            True if all tasks succeed
        """
        print("=" * 60)
        print("Overlord11 Pre-Commit Housekeeping")
        print("=" * 60)

        # Clean temporary files
        self.clean_tmpclaude_files()

        # Run checks (TODO)
        checks_passed = self.run_checks()

        # Run tests (TODO)
        tests_passed = self.run_tests()

        # Generate report (TODO)
        self.generate_report()

        print("\n" + "=" * 60)
        print("Pre-commit tasks completed.")
        print("=" * 60)

        return checks_passed and tests_passed


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Pre-commit housekeeping script for Overlord11",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clean all temporary files (not just tmpclaude)"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).parent,
        help="Root directory to clean (default: script directory)"
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Only run cleaning, skip checks and tests"
    )

    args = parser.parse_args()

    # Initialize cleaner
    cleaner = PreCommitCleaner(
        root_dir=args.root.resolve(),
        dry_run=args.dry_run,
        verbose=args.verbose
    )

    if args.clean_only:
        if args.all:
            cleaner.clean_temp_files()
        else:
            cleaner.clean_tmpclaude_files()
    else:
        success = cleaner.run_all()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
