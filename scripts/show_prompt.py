"""Print the triage prompt template currently stored in the registry under an alias.

    python -m scripts.show_prompt            # champion (default)
    python -m scripts.show_prompt challenger

Answers "what text is actually in the registry?" by asking the registry itself — read-only,
no LLM call, $0. Needs the MLflow server up (`make up`) and the prompt registered
(`python -m scripts.register_prompt`).
"""

from __future__ import annotations

import json
import sys

from app.persistence.prompts import CHAMPION, load_triage_prompt, open_registry


def main(argv: list[str]) -> int:
    alias = argv[0] if argv else CHAMPION
    client = open_registry()
    prompt = load_triage_prompt(client, alias)
    print(f"prompts:/triage@{alias} -> v{prompt.version}")
    print(json.dumps(prompt.template, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
