import sys
from pathlib import Path

import pytest

# Make the backend package importable regardless of invocation directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="module")
def code3():
    """d=3 rotated surface code (shared across milestone-12 QEC tests)."""
    from app.qec.rotated_surface_code import RotatedSurfaceCode
    return RotatedSurfaceCode.build(3)


@pytest.fixture(scope="module")
def code5():
    """d=5 rotated surface code."""
    from app.qec.rotated_surface_code import RotatedSurfaceCode
    return RotatedSurfaceCode.build(5)


@pytest.fixture(scope="module")
def code7():
    """d=7 rotated surface code."""
    from app.qec.rotated_surface_code import RotatedSurfaceCode
    return RotatedSurfaceCode.build(7)
