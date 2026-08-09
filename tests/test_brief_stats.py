import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "brief_stats.py")


def run_stats(*args):
    return subprocess.run([sys.executable, SCRIPT, *args],
                         capture_output=True, text=True)


def test_reports_the_numbers(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("# Brief\n\nWe want a list app. Who uses it? When?\n")
    r = run_stats(str(brief))
    assert r.returncode == 0
    assert "words: 11" in r.stdout
    assert "headings: 1" in r.stdout
    assert "questions already in the brief: 2" in r.stdout
    assert "verdict: thin" in r.stdout


def test_verdict_scales_with_length(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("word " * 200)
    assert "verdict: normal" in run_stats(str(brief)).stdout
    brief.write_text("word " * 500)
    assert "verdict: detailed" in run_stats(str(brief)).stdout


def test_missing_file_is_a_plain_error(tmp_path):
    r = run_stats(str(tmp_path / "nope.md"))
    assert r.returncode == 1
    assert "cannot read" in r.stderr


def test_usage_error_without_a_path():
    r = run_stats()
    assert r.returncode == 2
    assert "usage" in r.stderr
