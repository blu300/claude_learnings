import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "iteration.py")


def run(tmp_path, *args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, cwd=str(tmp_path)
    )


def make_folders(tmp_path, n):
    for i in range(1, n + 1):
        (tmp_path / "docs" / str(i)).mkdir(parents=True)


def test_next_stops_at_default_cap(tmp_path):
    # No flag needed: the cap is a constant in the script, not an opt-in.
    make_folders(tmp_path, 4)
    result = run(tmp_path, "next")
    assert result.returncode == 1
    assert "maximum" in result.stderr.lower()
    assert not (tmp_path / "docs" / "5").exists()


def test_next_allows_below_cap(tmp_path):
    make_folders(tmp_path, 2)
    result = run(tmp_path, "next")
    assert result.returncode == 0
    assert "3" in result.stdout


def test_max_flag_cannot_raise_the_cap(tmp_path):
    make_folders(tmp_path, 4)
    result = run(tmp_path, "next", "--max", "99")
    assert result.returncode == 1


def test_max_flag_can_lower_the_cap(tmp_path):
    make_folders(tmp_path, 2)
    result = run(tmp_path, "next", "--max", "2")
    assert result.returncode == 1


def test_invalid_max_is_a_loud_error(tmp_path):
    # A typo must not silently loosen anything.
    for bad in (["--max", "abc"], ["--max", "0"], ["--max"]):
        result = run(tmp_path, "next", *bad)
        assert result.returncode == 2, bad
        assert "--max" in result.stderr


def test_next_writes_the_cursor(tmp_path):
    make_folders(tmp_path, 2)
    run(tmp_path, "next")
    cursor = (tmp_path / "docs" / ".current_iteration").read_text().strip()
    assert cursor == "3"


def test_next_creates_first_folder_and_cursor(tmp_path):
    result = run(tmp_path, "next")
    assert result.returncode == 0
    assert (tmp_path / "docs" / "1").is_dir()
    assert (tmp_path / "docs" / ".current_iteration").read_text().strip() == "1"
