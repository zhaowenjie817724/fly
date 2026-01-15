from __future__ import annotations

from pathlib import Path


def read_git_commit(repo_root: Path) -> str:
    head_path = repo_root / ".git" / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "unknown"

    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        ref_path = repo_root / ".git" / ref
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip()

        packed_refs = repo_root / ".git" / "packed-refs"
        if packed_refs.exists():
            for line in packed_refs.read_text(encoding="utf-8").splitlines():
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                sha, ref_name = line.split(" ", 1)
                if ref_name.strip() == ref:
                    return sha

        return "unknown"

    return head
