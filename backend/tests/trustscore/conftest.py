# Fail any test that opens a database session. The v5 adapter performs live
# lookups by default (DOT orders, fleet size); a test that forgets to disable
# them would silently query production.
import pytest
import src.common.config as cfg


@pytest.fixture(autouse=True)
def _forbid_db_access():
    original = cfg.SessionLocal

    def _boom(*args, **kwargs):
        raise AssertionError("test opened a database session")

    cfg.SessionLocal = _boom
    yield
    cfg.SessionLocal = original
