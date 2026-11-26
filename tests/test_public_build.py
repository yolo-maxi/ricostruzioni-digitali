"""The sanitized source still rebuilds both active faces without private inputs."""
import hashlib
import subprocess
import sys

import pytest
from test_site import ROOT, LAB
from test_public_release import FONT_SHA


@pytest.mark.parametrize('builder,stem', [
    ('build_font.py', 'Balilla-Reconstructed'),
    ('build_panel.py', 'Balilla-Panel-Reconstructed'),
])
def test_active_font_rebuild_from_public_inputs(tmp_path, builder, stem):
    for run in ('first', 'second'):
        output = tmp_path / run
        result = subprocess.run([sys.executable, str(LAB / builder), '--out', str(output)],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        for extension in ('.ttf', '.woff2'):
            name = stem + extension
            assert hashlib.sha256((output / name).read_bytes()).hexdigest() == FONT_SHA[name]
