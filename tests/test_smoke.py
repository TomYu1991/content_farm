"""Smoke tests confirming the Python package and test toolchain are wired up."""

import sys

import httpx
import respx
from hypothesis import given, settings
from hypothesis import strategies as st

import content_pipeline


def test_python_version_is_supported() -> None:
    assert sys.version_info >= content_pipeline.MIN_PYTHON


def test_package_exposes_version() -> None:
    assert content_pipeline.__version__ == "0.1.0"


@settings(max_examples=100)
@given(st.text())
def test_hypothesis_runs(value: str) -> None:
    assert value.encode("utf-8").decode("utf-8") == value


def test_http_mock_blocks_real_network() -> None:
    with respx.mock(assert_all_mocked=True) as router:
        route = router.get("https://gateway.invalid/health").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        response = httpx.get("https://gateway.invalid/health")
    assert route.called
    assert response.json() == {"ok": True}
