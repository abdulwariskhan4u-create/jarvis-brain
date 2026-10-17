"""Run the real deploy preflight against isolated fake host commands."""
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "build/deploy-disk-preflight.sh"


@pytest.mark.parametrize(
    "before,after,prune_fails,expected,pruned",
    [(40, 40, False, 0, False), (7, 33, False, 0, True),
     (7, 12, False, 1, True), (7, 33, True, 1, True)],
)
def test_preflight(tmp_path, before, after, prune_fails, expected, pruned):
    commands = tmp_path / "bin"
    commands.mkdir()
    (commands / "docker").write_text(
        '#!/bin/bash\n'
        'if [[ "$1" == info ]]; then echo "$TEST_DIR"; exit 0; fi\n'
        'echo "$*" >> "$TEST_DIR/calls"\n'
        '[[ "$*" == "builder prune -af" ]] || exit 99\n'
        'touch "$TEST_DIR/pruned"\n'
        'exit "$PRUNE_FAILS"\n'
    )
    (commands / "df").write_text(
        '#!/bin/bash\n'
        'free="$BEFORE"\n'
        '[[ ! -f "$TEST_DIR/pruned" ]] || free="$AFTER"\n'
        'echo "Filesystem 1024-blocks Used Available Capacity Mounted on"\n'
        'echo "fake 100000000 1 $((free * 1024 * 1024)) 1% /"\n'
    )
    for command in commands.iterdir():
        command.chmod(0o700)
    env = {**os.environ, "PATH": f"{commands}:{os.environ['PATH']}",
           "TEST_DIR": str(tmp_path), "BEFORE": str(before), "AFTER": str(after),
           "PRUNE_FAILS": str(int(prune_fails)), "GITHUB_WORKSPACE": str(tmp_path),
           "DEPLOY_MIN_FREE_GIB": "30"}
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == expected, result.stdout + result.stderr
    calls = (tmp_path / "calls").read_text() if (tmp_path / "calls").exists() else ""
    assert calls == ("builder prune -af\n" if pruned else "")
    if expected and not prune_fails:
        assert "::error::" in result.stderr
