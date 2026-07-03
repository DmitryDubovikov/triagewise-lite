"""Generate the committed promptfoo assets in eval/ from the golden set.

    uv run python -m scripts.build_eval

Thin adapter: the actual recipe lives in app/workflow/eval_assets.py (shared with the
sync tests). Offline, deterministic, $0.
"""

from __future__ import annotations

from app.config import get_settings
from app.workflow.eval_assets import build_from_settings


def main() -> int:
    settings = get_settings()
    assets = build_from_settings(settings)
    for rel, content in assets.items():
        target = settings.eval_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        print(f"wrote {target.relative_to(settings.eval_dir.parent)}")
    print(f"{len(assets)} assets rebuilt into {settings.eval_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
