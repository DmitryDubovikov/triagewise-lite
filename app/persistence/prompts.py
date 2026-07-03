"""MLflow Prompt Registry repository — prompt-as-artifact + champion/challenger aliases.

This is the ONLY module that touches the MLflow prompt API (CLAUDE.md rule 6: persistence
owns the registry; domain/workflow never import mlflow). The registry handle (MlflowClient)
is opened here at the transport boundary and passed down as an argument — never a global.

The chat templates below are the desired content for the champion/challenger roles. `sync_prompts`
pushes them into the registry: a new version is created only when a template actually changes, so
re-running is idempotent (no duplicate identical versions). The champion template is byte-identical
to iter-0's inline prompt so the committed cassette key stays stable ($0, no re-record).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple, cast

if TYPE_CHECKING:
    from mlflow import MlflowClient
    from mlflow.entities.model_registry import PromptVersion

    from app.domain.triage import Ticket

from app.config import Settings, get_settings


class SyncedPrompt(NamedTuple):
    """Outcome of syncing one alias: which version it points at, and whether that version was
    freshly registered (True) or the existing one already matched the template (False)."""

    version: int
    created: bool


TRIAGE_PROMPT_NAME = "triage"
CHAMPION = "champion"
CHALLENGER = "challenger"

_SYSTEM = (
    "You triage Driftwood (a SaaS task-tracker) support tickets. "
    "Reply with ONLY a JSON object with keys: "
    "category (string), priority (low|medium|high|urgent), "
    "sentiment (negative|neutral|positive), needs_human (boolean), "
    "draft_reply (string). Reply in friendly prose, no JSON."
)

# Chat templates with {{subject}}/{{body}} placeholders (MLflow double-brace form).
# champion: iter-0 prompt verbatim. challenger: a variant that flags the golden-set "jokers"
# (polite-but-negative, ambiguous category) — a distinct version so champion != challenger is
# demonstrable now; the actual promotion/swap is iter 6.
_USER = "Subject: {{subject}}\n\n{{body}}"

TRIAGE_CHAMPION_TEMPLATE = [
    {"role": "system", "content": _SYSTEM},
    {"role": "user", "content": _USER},
]

TRIAGE_CHALLENGER_TEMPLATE = [
    {
        "role": "system",
        "content": (
            _SYSTEM + " Watch for tickets that are polite on the surface but negative "
            "underneath, and for ambiguous categories — escalate (needs_human=true) when unsure."
        ),
    },
    {"role": "user", "content": _USER},
]


def open_registry(settings: Settings | None = None) -> MlflowClient:
    """Open the registry handle at the boundary. Both URIs point at the same MLflow server."""
    from mlflow import MlflowClient

    settings = settings or get_settings()
    uri = settings.mlflow_tracking_uri
    return MlflowClient(tracking_uri=uri, registry_uri=uri)


def _current_version(client: MlflowClient, alias: str) -> PromptVersion | None:
    """The prompt version the alias points at, or None if the prompt/alias doesn't exist yet.

    Queries the store directly (not the cached load_prompt, whose cache is keyed only by the
    prompt URI and would bleed across registries in a multi-registry process like the test suite).
    """
    from mlflow.exceptions import MlflowException

    try:
        return client.get_prompt_version_by_alias(TRIAGE_PROMPT_NAME, alias)
    except MlflowException:
        return None


def sync_prompts(client: MlflowClient) -> dict[str, SyncedPrompt]:
    """Make the registry reflect the champion/challenger templates defined in code.

    Idempotent: registers a new version only when a template differs from the one the alias
    currently points at; otherwise it leaves versions untouched and just confirms the alias.
    The single source of truth shared by the register script, the cassette author, and tests —
    so the registered prompt that drives cassette keys can't drift between them.
    """
    desired = ((CHAMPION, TRIAGE_CHAMPION_TEMPLATE), (CHALLENGER, TRIAGE_CHALLENGER_TEMPLATE))
    synced: dict[str, SyncedPrompt] = {}
    for alias, template in desired:
        current = _current_version(client, alias)
        if current is not None and current.template == template:
            synced[alias] = SyncedPrompt(version=current.version, created=False)
            continue
        pv = client.register_prompt(
            name=TRIAGE_PROMPT_NAME, template=template, commit_message=f"sync {alias}"
        )
        client.set_prompt_alias(TRIAGE_PROMPT_NAME, alias, pv.version)
        synced[alias] = SyncedPrompt(version=pv.version, created=True)
    return synced


def load_triage_prompt(client: MlflowClient, alias: str) -> PromptVersion:
    """Load the triage prompt version an alias points to (verify in the store, not the UI)."""
    return client.load_prompt(f"prompts:/{TRIAGE_PROMPT_NAME}@{alias}")


def format_for_ticket(prompt: PromptVersion, ticket: Ticket) -> list[dict[str, Any]]:
    """Render a loaded chat-template prompt into messages for a ticket.

    The single home for this step, shared by the live flow and the offline cassette author —
    so the messages that drive the cassette key can't drift between them.
    """
    return cast("list[dict[str, Any]]", prompt.format(subject=ticket.subject, body=ticket.body))
