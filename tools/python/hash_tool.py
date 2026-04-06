"""
Overlord11 - Hash Tool
=======================
Compute cryptographic hashes for strings and files. Supports MD5, SHA-1,
SHA-256, SHA-512, and SHA3-256. Useful for verifying file integrity,
deduplication, and generating content fingerprints.

Actions:
  hash_string  – Hash a string value.
  hash_file    – Hash the contents of a file.
  verify_file  – Check that a file matches an expected hash.
  compare      – Compare two strings or files for equality via hash.

Usage (CLI):
    python hash_tool.py --action hash_string --input "Hello, World!"
    python hash_tool.py --action hash_file --file /path/to/file.txt --algorithm sha256
    python hash_tool.py --action verify_file --file /path/to/file.txt --expected abc123...
    python hash_tool.py --action compare --input "text" --input_b "text"
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional


SUPPORTED_ALGORITHMS = ("md5", "sha1", "sha256", "sha512", "sha3_256")
CHUNK_SIZE = 65536  # 64 KB


def _hash_bytes(data: bytes, algorithm: str) -> str:
    """Return hex digest of data using the given algorithm."""
    h = hashlib.new(algorithm.replace("-", "_"))
    h.update(data)
    return h.hexdigest()


def _hash_file_path(path: Path, algorithm: str) -> str:
    """Stream-hash a file to avoid loading large files into memory."""
    alg = algorithm.replace("-", "_")
    h = hashlib.new(alg)
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def hash_tool(
    action: str,
    input: Optional[str] = None,
    input_b: Optional[str] = None,
    file: Optional[str] = None,
    file_b: Optional[str] = None,
    algorithm: str = "sha256",
    expected: Optional[str] = None,
    encoding: str = "utf-8",
) -> dict:
    """
    Compute or verify cryptographic hashes.

    Args:
        action:    Operation: hash_string, hash_file, verify_file, compare.
        input:     String to hash (for hash_string/compare actions).
        input_b:   Second string to compare (for compare action).
        file:      Path to file to hash (for hash_file/verify_file/compare actions).
        file_b:    Path to second file to compare (for compare action).
        algorithm: Hash algorithm: md5, sha1, sha256, sha512, sha3_256. Default sha256.
        expected:  Expected hash hex string (for verify_file action).
        encoding:  String encoding for hash_string. Default utf-8.

    Returns:
        dict with keys:
            status    – "success" or "error"
            action    – action performed
            algorithm – algorithm used
            hash      – computed hex digest (on success)
            match     – bool, whether hashes match (for verify/compare)
            error     – error message (on failure)
            hint      – corrective action (on failure)
    """
    alg = algorithm.lower().replace("-", "_")
    if alg not in SUPPORTED_ALGORITHMS:
        return {
            "status": "error",
            "action": action,
            "algorithm": algorithm,
            "error": f"Unsupported algorithm: '{algorithm}'",
            "hint": f"Use one of: {', '.join(SUPPORTED_ALGORITHMS)}",
        }

    if action not in ("hash_string", "hash_file", "verify_file", "compare"):
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action: '{action}'",
            "hint": "Use one of: hash_string, hash_file, verify_file, compare",
        }

    # ── hash_string ────────────────────────────────────────────────────────
    if action == "hash_string":
        if input is None:
            return {
                "status": "error",
                "action": action,
                "error": "The 'input' parameter is required for hash_string",
                "hint": "Provide the string to hash in the 'input' parameter.",
            }
        try:
            data = input.encode(encoding)
        except LookupError:
            return {
                "status": "error",
                "action": action,
                "error": f"Unknown encoding: '{encoding}'",
                "hint": "Use a standard encoding like utf-8, latin-1, or ascii.",
            }
        digest = _hash_bytes(data, alg)
        return {
            "status": "success",
            "action": "hash_string",
            "algorithm": alg,
            "input_length": len(input),
            "encoding": encoding,
            "hash": digest,
        }

    # ── hash_file ──────────────────────────────────────────────────────────
    if action == "hash_file":
        if not file:
            return {
                "status": "error",
                "action": action,
                "error": "The 'file' parameter is required for hash_file",
                "hint": "Provide the path to the file in the 'file' parameter.",
            }
        p = Path(file)
        if not p.exists():
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"File not found: {file}",
                "hint": "Verify the file path with list_directory or glob_tool.",
            }
        if not p.is_file():
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"Path is not a file: {file}",
                "hint": "Provide a path to a file, not a directory.",
            }
        try:
            digest = _hash_file_path(p, alg)
            return {
                "status": "success",
                "action": "hash_file",
                "algorithm": alg,
                "file": str(p.resolve()),
                "size_bytes": p.stat().st_size,
                "hash": digest,
            }
        except OSError as exc:
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"Cannot read file: {exc}",
                "hint": "Check file permissions.",
            }

    # ── verify_file ────────────────────────────────────────────────────────
    if action == "verify_file":
        if not file:
            return {
                "status": "error",
                "action": action,
                "error": "The 'file' parameter is required for verify_file",
                "hint": "Provide the file path in 'file' and expected hash in 'expected'.",
            }
        if not expected:
            return {
                "status": "error",
                "action": action,
                "error": "The 'expected' parameter is required for verify_file",
                "hint": "Provide the expected hash hex string in 'expected'.",
            }
        p = Path(file)
        if not p.exists():
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"File not found: {file}",
                "hint": "Verify the file path with list_directory.",
            }
        try:
            digest = _hash_file_path(p, alg)
        except OSError as exc:
            return {
                "status": "error",
                "action": action,
                "file": file,
                "error": f"Cannot read file: {exc}",
                "hint": "Check file permissions.",
            }
        match = digest.lower() == expected.lower().strip()
        return {
            "status": "success",
            "action": "verify_file",
            "algorithm": alg,
            "file": str(p.resolve()),
            "hash": digest,
            "expected": expected,
            "match": match,
            "verdict": "PASS" if match else "FAIL",
        }

    # ── compare ────────────────────────────────────────────────────────────
    if action == "compare":
        # Compute hash A
        if file:
            p = Path(file)
            if not p.exists():
                return {
                    "status": "error",
                    "action": action,
                    "error": f"File not found: {file}",
                    "hint": "Check file path for the first item.",
                }
            try:
                hash_a = _hash_file_path(p, alg)
                label_a = str(p.resolve())
            except OSError as exc:
                return {"status": "error", "action": action, "error": str(exc)}
        elif input is not None:
            hash_a = _hash_bytes(input.encode(encoding), alg)
            label_a = f"string ({len(input)} chars)"
        else:
            return {
                "status": "error",
                "action": action,
                "error": "Provide 'input' or 'file' for the first item to compare",
                "hint": "Provide a string in 'input' or a file path in 'file'.",
            }

        # Compute hash B
        if file_b:
            pb = Path(file_b)
            if not pb.exists():
                return {
                    "status": "error",
                    "action": action,
                    "error": f"Second file not found: {file_b}",
                    "hint": "Check file path for the second item.",
                }
            try:
                hash_b = _hash_file_path(pb, alg)
                label_b = str(pb.resolve())
            except OSError as exc:
                return {"status": "error", "action": action, "error": str(exc)}
        elif input_b is not None:
            hash_b = _hash_bytes(input_b.encode(encoding), alg)
            label_b = f"string ({len(input_b)} chars)"
        else:
            return {
                "status": "error",
                "action": action,
                "error": "Provide 'input_b' or 'file_b' for the second item to compare",
                "hint": "Provide a string in 'input_b' or a file path in 'file_b'.",
            }

        match = hash_a == hash_b
        return {
            "status": "success",
            "action": "compare",
            "algorithm": alg,
            "item_a": label_a,
            "item_b": label_b,
            "hash_a": hash_a,
            "hash_b": hash_b,
            "match": match,
            "verdict": "IDENTICAL" if match else "DIFFERENT",
        }

    return {"status": "error", "action": action, "error": "Internal error"}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Hash Tool")
    parser.add_argument("--action", required=True,
                        choices=["hash_string", "hash_file", "verify_file", "compare"])
    parser.add_argument("--input", default=None, help="String to hash")
    parser.add_argument("--input_b", default=None, help="Second string for compare")
    parser.add_argument("--file", default=None, help="Path to file to hash")
    parser.add_argument("--file_b", default=None, help="Path to second file for compare")
    parser.add_argument("--algorithm", default="sha256",
                        choices=list(SUPPORTED_ALGORITHMS), help="Hash algorithm")
    parser.add_argument("--expected", default=None, help="Expected hash for verify_file")
    parser.add_argument("--encoding", default="utf-8", help="String encoding for hash_string")

    args = parser.parse_args()
    result = hash_tool(
        action=args.action,
        input=args.input,
        input_b=args.input_b,
        file=args.file,
        file_b=args.file_b,
        algorithm=args.algorithm,
        expected=args.expected,
        encoding=args.encoding,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
