"""Security gate for the LiteLLM discipline (CLAUDE.md rule 5) — mechanically checked.

The rule used to live in docstrings; iter 3 makes it a failing test: SDK-only (never Proxy),
one bare acompletion in the access layer, leak channels zeroed before the first call, lazy
import (replay never touches the SDK), version pinned in pyproject.toml + uv.lock.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTER = ROOT / "app" / "llm" / "router.py"

# The whole litellm surface the app may touch: the one call, the leak-channel switches,
# and response pricing. Anything else showing up in app/ fails the gate.
ALLOWED_ATTRS = {
    "acompletion",
    "completion_cost",
    "telemetry",
    "callbacks",
    "success_callback",
    "failure_callback",
}


def _app_sources() -> list[Path]:
    return sorted((ROOT / "app").rglob("*.py"))


def test_no_proxy_and_only_the_allowed_litellm_surface():
    """Never Proxy (CVE surface), and no litellm feature creep past the allowed set."""
    for path in _app_sources():
        src = path.read_text()
        assert "litellm.proxy" not in src, f"{path}: litellm.proxy is forbidden (rule 5)"
        assert "litellm_proxy" not in src, f"{path}: proxy provider prefix is forbidden (rule 5)"
        for attr in re.findall(r"\blitellm\.(\w+)", src):
            assert attr in ALLOWED_ATTRS, f"{path}: litellm.{attr} is outside the allowed surface"


def test_litellm_imported_only_in_the_access_layer():
    """Exactly one import site — the router's live path. No SDK sprawl.

    Both forms count: `import litellm` and `from litellm import ...` — otherwise a
    from-import anywhere in app/ would slip past this gate and the dotted-attr scan.
    """
    import_re = re.compile(r"^\s*(?:import|from)\s+litellm\b", re.M)
    importers = [p for p in _app_sources() if import_re.search(p.read_text())]
    assert importers == [ROUTER]


def test_leak_channels_zeroed_before_the_first_call():
    """telemetry off + all callback hooks emptied strictly before acompletion runs."""
    src = ROUTER.read_text()
    call = src.index("litellm.acompletion(")
    for guard in (
        "litellm.telemetry = False",
        "litellm.callbacks = []",
        "litellm.success_callback = []",
        "litellm.failure_callback = []",
    ):
        assert src.index(guard) < call, f"'{guard}' must precede the acompletion call"


def test_replay_never_imports_the_sdk():
    """Lazy import holds: importing the router does not pull litellm into the process."""
    code = "import sys; import app.llm.router; assert 'litellm' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)


def test_version_is_pinned():
    """Constraint in pyproject.toml, exact resolved version in uv.lock."""
    assert re.search(r'"litellm>=[\d.]+,<\d+"', (ROOT / "pyproject.toml").read_text())
    lock = (ROOT / "uv.lock").read_text()
    assert re.search(r'name = "litellm"\nversion = "[\d.]+"', lock), (
        "litellm must resolve to an exact version in uv.lock"
    )
