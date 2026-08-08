import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "iteration.py")


def test_next_respects_max(tmp_path):
    docs = tmp_path / "docs"
    for i in range(1, 5):
        (docs / str(i)).mkdir(parents=True)

    result = subprocess.run(
        [sys.executable, SCRIPT, "next", "--max", "4"],
        capture_output=True, text=True, cwd=str(tmp_path)
    )
    assert result.returncode == 1
    assert "maximum" in result.stderr.lower()


def test_next_allows_below_max(tmp_path):
    docs = tmp_path / "docs"
    for i in range(1, 3):
        (docs / str(i)).mkdir(parents=True)

    result = subprocess.run(
        [sys.executable, SCRIPT, "next", "--max", "4"],
        capture_output=True, text=True, cwd=str(tmp_path)
    )
    assert result.returncode == 0
    assert "3" in result.stdout


def test_next_without_max_has_no_cap(tmp_path):
    docs = tmp_path / "docs"
    for i in range(1, 20):
        (docs / str(i)).mkdir(parents=True)

    result = subprocess.run(
        [sys.executable, SCRIPT, "next"],
        capture_output=True, text=True, cwd=str(tmp_path)
    )
    assert result.returncode == 0
