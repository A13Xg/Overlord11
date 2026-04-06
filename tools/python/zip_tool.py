"""
Overlord11 - Zip Tool
======================
Create, extract, inspect, and manage ZIP archives.

Actions:
  create   – Create a ZIP archive from files or directories.
  extract  – Extract a ZIP archive to a target directory.
  list     – List contents of a ZIP archive with metadata.
  add      – Add files to an existing ZIP archive.
  remove   – Remove a file from a ZIP archive (creates new archive).
  info     – Get metadata about a ZIP archive (size, file count, compression).

Usage (CLI):
    python zip_tool.py --action create --output archive.zip --paths file1.txt dir/
    python zip_tool.py --action extract --file archive.zip --output_dir ./extracted
    python zip_tool.py --action list --file archive.zip
    python zip_tool.py --action info --file archive.zip
"""

import argparse
import io
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import List, Optional


def _collect_files(source_path: Path, base: Optional[Path] = None) -> list:
    """Collect (disk_path, arcname) pairs from a path (file or directory)."""
    pairs = []
    if base is None:
        base = source_path.parent

    if source_path.is_file():
        arcname = str(source_path.relative_to(base)).replace("\\", "/")
        pairs.append((source_path, arcname))
    elif source_path.is_dir():
        for root, dirs, files in os.walk(source_path):
            # Skip hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                fpath = Path(root) / fname
                arcname = str(fpath.relative_to(base)).replace("\\", "/")
                pairs.append((fpath, arcname))
    return pairs


def zip_tool(
    action: str,
    file: Optional[str] = None,
    output: Optional[str] = None,
    output_dir: Optional[str] = None,
    paths: Optional[List[str]] = None,
    compression: str = "deflate",
    overwrite: bool = False,
    password: Optional[str] = None,
) -> dict:
    """
    Create, extract, inspect, or modify ZIP archives.

    Args:
        action:      Operation: create, extract, list, add, remove, info.
        file:        Path to an existing ZIP archive (required for extract/list/add/remove/info).
        output:      Output archive path (for create action).
        output_dir:  Directory to extract files into (for extract action). Defaults to current dir.
        paths:       List of file/directory paths to include (for create/add) or filenames to
                     remove (for remove action).
        compression: Compression method: deflate (default), store (no compression), bzip2, lzma.
        overwrite:   Whether to overwrite existing output file. Defaults to False.
        password:    Password for encrypted archives (extraction only).

    Returns:
        dict with keys:
            status        – "success" or "error"
            action        – action performed
            file          – path to the archive
            entries       – list of file info dicts (for list/create/extract)
            file_count    – number of files
            total_size_bytes – total uncompressed size
            error         – error message (on failure)
            hint          – corrective action (on failure)
    """
    if action not in ("create", "extract", "list", "add", "remove", "info"):
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action: '{action}'",
            "hint": "Use one of: create, extract, list, add, remove, info",
        }

    COMPRESSION_MAP = {
        "deflate": zipfile.ZIP_DEFLATED,
        "store": zipfile.ZIP_STORED,
        "bzip2": zipfile.ZIP_BZIP2,
        "lzma": zipfile.ZIP_LZMA,
    }
    comp_method = COMPRESSION_MAP.get(compression.lower(), zipfile.ZIP_DEFLATED)

    # ── create ─────────────────────────────────────────────────────────────
    if action == "create":
        if not output:
            return {
                "status": "error",
                "action": action,
                "error": "The 'output' parameter is required for create",
                "hint": "Specify the output archive path, e.g., archive.zip",
            }
        if not paths:
            return {
                "status": "error",
                "action": action,
                "error": "The 'paths' parameter is required for create",
                "hint": "Provide a list of file/directory paths to include in the archive.",
            }
        out_path = Path(output)
        if out_path.exists() and not overwrite:
            return {
                "status": "error",
                "action": action,
                "output": str(out_path),
                "error": f"Output file already exists: {output}",
                "hint": "Set overwrite=true to replace the existing file.",
            }
        out_path.parent.mkdir(parents=True, exist_ok=True)

        added = []
        missing = []
        try:
            with zipfile.ZipFile(str(out_path), "w", compression=comp_method) as zf:
                for p_str in paths:
                    p = Path(p_str)
                    if not p.exists():
                        missing.append(p_str)
                        continue
                    base = p.parent
                    for fpath, arcname in _collect_files(p, base):
                        zf.write(str(fpath), arcname)
                        added.append({
                            "name": arcname,
                            "size_bytes": fpath.stat().st_size,
                        })
        except OSError as exc:
            return {
                "status": "error",
                "action": action,
                "output": str(out_path),
                "error": f"Cannot write archive: {exc}",
                "hint": "Check write permissions for the output directory.",
            }

        result = {
            "status": "success",
            "action": "create",
            "file": str(out_path.resolve()),
            "compression": compression,
            "file_count": len(added),
            "entries": added,
            "archive_size_bytes": out_path.stat().st_size,
        }
        if missing:
            result["missing_paths"] = missing
            result["warning"] = f"{len(missing)} path(s) not found and were skipped"
        return result

    # ── All other actions require an existing archive ──────────────────────
    if not file:
        return {
            "status": "error",
            "action": action,
            "error": "The 'file' parameter is required",
            "hint": "Provide the path to the ZIP archive in the 'file' parameter.",
        }
    arc_path = Path(file)
    if not arc_path.exists():
        return {
            "status": "error",
            "action": action,
            "file": file,
            "error": f"Archive not found: {file}",
            "hint": "Check the path with glob_tool or list_directory.",
        }

    if not zipfile.is_zipfile(str(arc_path)):
        return {
            "status": "error",
            "action": action,
            "file": file,
            "error": f"File is not a valid ZIP archive: {file}",
            "hint": "Verify the file is a .zip archive.",
        }

    # ── list ───────────────────────────────────────────────────────────────
    if action in ("list", "info"):
        try:
            with zipfile.ZipFile(str(arc_path), "r") as zf:
                entries = []
                total_uncompressed = 0
                total_compressed = 0
                for info in zf.infolist():
                    entries.append({
                        "name": info.filename,
                        "size_bytes": info.file_size,
                        "compressed_bytes": info.compress_size,
                        "compress_type": info.compress_type,
                        "is_dir": info.is_dir(),
                    })
                    total_uncompressed += info.file_size
                    total_compressed += info.compress_size

            result = {
                "status": "success",
                "action": action,
                "file": str(arc_path.resolve()),
                "archive_size_bytes": arc_path.stat().st_size,
                "file_count": sum(1 for e in entries if not e["is_dir"]),
                "dir_count": sum(1 for e in entries if e["is_dir"]),
                "total_uncompressed_bytes": total_uncompressed,
                "total_compressed_bytes": total_compressed,
                "compression_ratio": round(1 - total_compressed / max(total_uncompressed, 1), 3),
            }
            if action == "list":
                result["entries"] = entries
            return result
        except (zipfile.BadZipFile, OSError) as exc:
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"Cannot read archive: {exc}",
                "hint": "The archive may be corrupted or password-protected.",
            }

    # ── extract ────────────────────────────────────────────────────────────
    if action == "extract":
        dest = Path(output_dir or ".")
        dest.mkdir(parents=True, exist_ok=True)
        try:
            pwd = password.encode() if password else None
            with zipfile.ZipFile(str(arc_path), "r") as zf:
                zf.extractall(str(dest), pwd=pwd)
                extracted = [
                    {"name": info.filename, "size_bytes": info.file_size}
                    for info in zf.infolist()
                ]
            return {
                "status": "success",
                "action": "extract",
                "file": str(arc_path.resolve()),
                "output_dir": str(dest.resolve()),
                "file_count": len(extracted),
                "entries": extracted,
            }
        except RuntimeError as exc:
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"Extraction failed (bad password?): {exc}",
                "hint": "Provide the correct password in the 'password' parameter.",
            }
        except (zipfile.BadZipFile, OSError) as exc:
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"Extraction failed: {exc}",
                "hint": "Archive may be corrupted.",
            }

    # ── add ────────────────────────────────────────────────────────────────
    if action == "add":
        if not paths:
            return {
                "status": "error",
                "action": action,
                "error": "The 'paths' parameter is required for add",
                "hint": "Provide a list of file/directory paths to add to the archive.",
            }
        added = []
        try:
            with zipfile.ZipFile(str(arc_path), "a", compression=comp_method) as zf:
                for p_str in paths:
                    p = Path(p_str)
                    if not p.exists():
                        continue
                    base = p.parent
                    for fpath, arcname in _collect_files(p, base):
                        zf.write(str(fpath), arcname)
                        added.append({"name": arcname, "size_bytes": fpath.stat().st_size})
        except (zipfile.BadZipFile, OSError) as exc:
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"Cannot modify archive: {exc}",
                "hint": "Check file permissions and ensure archive is not corrupted.",
            }
        return {
            "status": "success",
            "action": "add",
            "file": str(arc_path.resolve()),
            "added_count": len(added),
            "entries": added,
        }

    # ── remove ─────────────────────────────────────────────────────────────
    if action == "remove":
        if not paths:
            return {
                "status": "error",
                "action": action,
                "error": "The 'paths' parameter is required for remove (filenames to delete)",
                "hint": "Provide a list of archive-internal filenames to remove.",
            }
        names_to_remove = set(paths)
        try:
            buf = io.BytesIO()
            kept = []
            removed = []
            with zipfile.ZipFile(str(arc_path), "r") as src:
                with zipfile.ZipFile(buf, "w", compression=comp_method) as dst:
                    for item in src.infolist():
                        if item.filename in names_to_remove:
                            removed.append(item.filename)
                        else:
                            dst.writestr(item, src.read(item.filename))
                            kept.append(item.filename)

            # Replace original
            with open(str(arc_path), "wb") as f:
                f.write(buf.getvalue())

            return {
                "status": "success",
                "action": "remove",
                "file": str(arc_path.resolve()),
                "removed": removed,
                "kept_count": len(kept),
                "not_found": [n for n in paths if n not in removed],
            }
        except (zipfile.BadZipFile, OSError) as exc:
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"Cannot modify archive: {exc}",
                "hint": "Check file permissions.",
            }

    return {"status": "error", "action": action, "error": "Internal error"}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Zip Tool")
    parser.add_argument("--action", required=True,
                        choices=["create", "extract", "list", "add", "remove", "info"])
    parser.add_argument("--file", default=None, help="Path to ZIP archive")
    parser.add_argument("--output", default=None, help="Output archive path (create)")
    parser.add_argument("--output_dir", default=None, help="Extraction target directory")
    parser.add_argument("--paths", nargs="+", default=None, help="File/directory paths")
    parser.add_argument("--compression", default="deflate",
                        choices=["deflate", "store", "bzip2", "lzma"])
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--password", default=None)

    args = parser.parse_args()
    result = zip_tool(
        action=args.action,
        file=args.file,
        output=args.output,
        output_dir=args.output_dir,
        paths=args.paths,
        compression=args.compression,
        overwrite=args.overwrite,
        password=args.password,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
