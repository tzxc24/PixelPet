"""Keep test artifacts on D while isolating simultaneous pytest invocations."""
from pathlib import Path
from uuid import uuid4


def pytest_configure(config):
    if config.option.basetemp is None:
        root = Path(__file__).resolve().parents[1]
        config.option.basetemp = str(root / "tmp" / "pytest" / f"run-{uuid4().hex}")
