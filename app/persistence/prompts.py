"""MLflow Prompt Registry repository — prompt-as-artifact + champion/challenger aliases.

This is the ONLY module that touches the MLflow prompt API (CLAUDE.md rule 6: persistence
owns the registry; domain/workflow never import mlflow). The registry handle (MlflowClient)
is opened here at the transport boundary and passed down as an argument — never a global.

The chat templates below are the desired content for the champion/challenger roles. `sync_prompts`
seeds them into the registry idempotently: each template is registered at most once (matched
against the store's existing versions), the challenger alias is code-owned, and the champion
alias belongs to the promotion loop (iter 6a) once it exists — a re-sync never rolls a swap
back. The champion template is byte-identical to iter-0's inline prompt so the committed
cassette key stays stable ($0, no re-record).
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
    "draft_reply (string). No prose, no code fences."
)

# Chat templates with {{subject}}/{{body}} placeholders (MLflow double-brace form).
# champion: iter-0 prompt verbatim. challenger: a variant that flags the golden-set "jokers"
# (polite-but-negative, ambiguous category) — the promotion loop (iter 6a, promotion_flow)
# is what actually swaps the champion alias onto it.
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
    """The prompt version the alias points at, or None if the prompt/alias doesn't exist yet."""
    from mlflow.exceptions import MlflowException

    try:
        return load_triage_prompt(client, alias)
    except MlflowException:
        return None


def _all_versions(client: MlflowClient) -> list[PromptVersion]:
    """Every stored version of the triage prompt ([] when the prompt doesn't exist yet)."""
    from mlflow.exceptions import MlflowException

    try:
        return list(client.search_prompt_versions(TRIAGE_PROMPT_NAME))
    except MlflowException:
        return []


def sync_prompts(client: MlflowClient) -> dict[str, SyncedPrompt]:
    """Seed the registry from the code templates — without fighting the promotion loop.

    Idempotent: a template is registered at most once, matched against the store's existing
    versions, so re-running never piles up duplicates. The challenger alias is code-owned and
    always points at the challenger template. The champion alias is bootstrap-only: once it
    exists it belongs to the promotion flow (iter 6a) — a re-sync neither rolls a swap back
    nor registers a changed champion template (that would just dangle; new candidates enter
    life as challengers). The single source of truth shared by the register script, the
    cassette author, and tests — so the prompt that drives cassette keys can't drift.
    """
    desired = ((CHAMPION, TRIAGE_CHAMPION_TEMPLATE), (CHALLENGER, TRIAGE_CHALLENGER_TEMPLATE))
    existing = _all_versions(client)
    synced: dict[str, SyncedPrompt] = {}
    for alias, template in desired:
        current = _current_version(client, alias)
        if alias == CHAMPION and current is not None:
            synced[alias] = SyncedPrompt(version=current.version, created=False)
            continue
        version = next((pv for pv in existing if pv.template == template), None)
        created = version is None
        if version is None:
            version = client.register_prompt(
                name=TRIAGE_PROMPT_NAME, template=template, commit_message=f"seed {alias}"
            )
        if current is None or current.version != version.version:
            client.set_prompt_alias(TRIAGE_PROMPT_NAME, alias, version.version)
        synced[alias] = SyncedPrompt(version=version.version, created=created)
    return synced


def promote_challenger(client: MlflowClient, version: int) -> None:
    """The swap of the promotion loop (iter 6a): point champion at the winning version.

    Alias assignment is idempotent, and the strict gate upstream never picks a winner once
    both aliases sit on the same version — so a re-run of the loop is a natural no-op.
    """
    client.set_prompt_alias(TRIAGE_PROMPT_NAME, CHAMPION, version)


def load_triage_prompt(client: MlflowClient, alias: str) -> PromptVersion:
    """Load the prompt version an alias points at — fresh from the store on every call.

    Deliberately not client.load_prompt: its cache is keyed by the prompt URI alone, so after
    a promotion swap it would keep serving the pre-swap version (killing hot-reload, iter 6a),
    and it bleeds across registries in a multi-registry process like the test suite.
    """
    return client.get_prompt_version_by_alias(TRIAGE_PROMPT_NAME, alias)


def format_for_ticket(prompt: PromptVersion, ticket: Ticket) -> list[dict[str, Any]]:
    """Render a loaded chat-template prompt into messages for a ticket.

    The single home for this step, shared by the live flow and the offline cassette author —
    so the messages that drive the cassette key can't drift between them.
    """
    return cast("list[dict[str, Any]]", prompt.format(subject=ticket.subject, body=ticket.body))
