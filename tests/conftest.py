from datetime import datetime
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from drone_analyst.agent import SecurityAnalystAgent
from drone_analyst.indexer import FrameIndex
from drone_analyst.models import Frame, Telemetry
from drone_analyst.simulator import build_frames


def make_frame(fid, hhmm, text, loc="Main Gate", day="2026-11-24", **tel):
    base = dict(location=loc, x=10.0, y=10.0, altitude_m=25.0, battery_pct=80.0)
    base.update(tel)
    return Frame(fid, datetime.fromisoformat(f"{day}T{hhmm}:00"), Telemetry(**base), text)


@pytest.fixture
def agent():
    return SecurityAnalystAgent(FrameIndex(":memory:"))


@pytest.fixture
def full_run():
    a = SecurityAnalystAgent(FrameIndex(":memory:"))
    results = [a.ingest(f) for f in build_frames()]
    a.index.flush()
    return a, results


@pytest.fixture
def project_tmp_path():
    """Use a fresh workspace temp dir when the Windows user temp folder is restricted."""
    path = Path(__file__).resolve().parents[1] / "output" / f"pytest-{uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
