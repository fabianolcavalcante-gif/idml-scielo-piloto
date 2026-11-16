"""Remove only four authorized remote candidate copies after completed H1 runs."""

from pathlib import Path

ROOT = Path("/opt/idml-platform/qualification/h1-real-20260929")


def main():
    cases = ("esa-e20240086", "esa-e20240135")
    paths = [ROOT / case / name for case in cases for name in ("candidate.xml", "candidate.zip")]
    if ROOT.is_symlink() or any(
        not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(ROOT.resolve())
        for p in paths
    ):
        raise ValueError("unexpected cleanup target")
    if any(
        (ROOT / c / "broker.sock").exists() or any((ROOT / c / "work").iterdir()) for c in cases
    ):
        raise ValueError("qualification still active or scratch not empty")
    for path in paths:
        path.unlink()
    if any(p.exists() for p in paths):
        raise RuntimeError("cleanup incomplete")
    print("private_candidate_copies_removed=4; local_originals_preserved=true")


if __name__ == "__main__":
    main()
