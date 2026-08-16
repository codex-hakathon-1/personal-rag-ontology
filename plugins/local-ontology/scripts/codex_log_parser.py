"""Parse and redact deterministic Markdown Codex conversation exports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import re


class EntityType(str, Enum):
    CONVERSATION = "conversation"
    DECISION = "decision"
    PLAN = "plan"
    TOPIC = "topic"


CLAIM_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(Decision|Plan|Topic)(?:\*\*)?\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
ROLE_PATTERN = re.compile(r"^#{1,6}\s+(User|Assistant)\s*$", re.IGNORECASE)
STANDALONE_REPLACEMENT_PATTERN = re.compile(
    r"^\s*(?:This|That|The|It)(?:\s+(decision|plan))?\s+"
    r"(?:explicitly\s+)?replaces\s+(?:the\s+)?(?:decision\s+|plan\s+)?"
    r"(?:[\"“'](.+?)[\"”']|(.+?))\.?\s*$",
    re.IGNORECASE,
)
INLINE_REPLACEMENT_PATTERN = re.compile(
    r"^(.+?)\s+(?:explicitly\s+)?replaces\s+(?:the\s+)?"
    r"(?:(?:decision|plan)\s+(?:[\"“']?(.+?)[\"”']?)|"
    r"[\"“'](.+?)[\"”'])\.?\s*$",
    re.IGNORECASE,
)
KEY_LIKE_PATTERN = re.compile(
    r"\b((?:[a-z0-9]+[_-])*(?:api[_-]?)?"
    r"(?:key|token|secret|password|passwd|pwd)\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^,;\r\n]+)",
    re.IGNORECASE,
)
TOKEN_LIKE_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~-]{16,}"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\."
        r"[A-Za-z0-9_-]{8,}\b"
    ),
)


@dataclass(frozen=True)
class SourceEvidence:
    line_number: int
    text: str
    role: str | None


@dataclass(frozen=True)
class ExtractedEntity:
    type: EntityType
    canonical_name: str
    source: SourceEvidence

    @property
    def line_number(self) -> int:
        return self.source.line_number

    @property
    def excerpt(self) -> str:
        return self.source.text

    @property
    def role(self) -> str | None:
        return self.source.role


@dataclass(frozen=True)
class CodexMessage:
    source: SourceEvidence

    @property
    def line_number(self) -> int:
        return self.source.line_number

    @property
    def text(self) -> str:
        return self.source.text

    @property
    def role(self) -> str:
        assert self.source.role is not None
        return self.source.role


@dataclass(frozen=True)
class SupersessionStatement:
    type: EntityType
    replacement_name: str
    replaced_name: str
    source: SourceEvidence

    @property
    def line_number(self) -> int:
        return self.source.line_number

    @property
    def excerpt(self) -> str:
        return self.source.text

    @property
    def role(self) -> str | None:
        return self.source.role


@dataclass(frozen=True)
class CodexDocument:
    path: Path
    relative_path: str
    title: str
    occurred_at: str
    source_content_hash: str
    entities: tuple[ExtractedEntity, ...]
    messages: tuple[CodexMessage, ...]
    supersessions: tuple[SupersessionStatement, ...]
    redactions: dict[str, int]


@dataclass(frozen=True)
class RedactionRules:
    secret_paths: tuple[str, ...]


def load_redaction_rules(path: Path | None) -> RedactionRules:
    if path is None:
        return RedactionRules(())
    document = json.loads(path.read_text(encoding="utf-8"))
    values = document.get("secret_paths", [])
    if not isinstance(values, list) or not all(
        isinstance(value, str) and value for value in values
    ):
        raise ValueError("secret_paths must be a list of non-empty strings")
    return RedactionRules(tuple(values))


def _redact(text: str, rules: RedactionRules) -> tuple[str, dict[str, int]]:
    counts = {
        "configured_secret_path": 0,
        "key_like_value": 0,
        "token_like_value": 0,
    }
    redacted = text
    for secret_path in sorted(rules.secret_paths, key=len, reverse=True):
        redacted, replacements = re.subn(
            re.escape(secret_path),
            "[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )
        counts["configured_secret_path"] += replacements

    def replace_key_like(match: re.Match[str]) -> str:
        counts["key_like_value"] += 1
        return f"{match.group(1)}[REDACTED]"

    redacted = KEY_LIKE_PATTERN.sub(replace_key_like, redacted)
    for pattern in TOKEN_LIKE_PATTERNS:
        redacted, replacements = pattern.subn("[REDACTED]", redacted)
        counts["token_like_value"] += replacements
    return redacted, counts


def _normalized_instant(value: str, path: Path) -> str:
    candidate = value.strip().strip('"\'')
    try:
        instant = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Invalid Codex log date in {path}: {value!r}") from error
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    metadata: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return metadata, index + 1
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip().lower()] = value.strip()
    return {}, 0


def _frontmatter_topics(value: str) -> tuple[str, ...]:
    candidate = value.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    return tuple(
        topic.strip().strip('"\'')
        for topic in candidate.split(",")
        if topic.strip().strip('"\'')
    )


def markdown_paths(logs_path: Path) -> tuple[Path, tuple[Path, ...]]:
    resolved = logs_path.resolve()
    if resolved.is_file():
        if resolved.suffix.lower() not in {".md", ".markdown"}:
            raise ValueError(f"Codex log must be Markdown: {resolved}")
        return resolved.parent, (resolved,)
    if not resolved.is_dir():
        raise FileNotFoundError(f"Codex logs path does not exist: {resolved}")
    paths = tuple(
        sorted(
            path
            for path in resolved.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
        )
    )
    return resolved, paths


def _replacement_target(match: re.Match[str]) -> str:
    return (match.group(2) or match.group(3)).strip().rstrip(".").strip()


def parse_document(
    path: Path,
    root: Path,
    redaction_rules: RedactionRules,
) -> CodexDocument:
    original = path.read_text(encoding="utf-8")
    redacted, redactions = _redact(original, redaction_rules)
    lines = redacted.splitlines()
    metadata, body_start = _parse_frontmatter(lines)
    title = metadata.get("title") or path.stem.replace("-", " ").title()
    date_value = metadata.get("date") or metadata.get("created_at")
    if not date_value:
        raise ValueError(f"Codex log requires a frontmatter date: {path}")
    occurred_at = _normalized_instant(date_value, path)
    entities: list[ExtractedEntity] = [
        ExtractedEntity(
            EntityType.CONVERSATION,
            title,
            SourceEvidence(1, title, None),
        )
    ]
    topics_line = next(
        (
            index
            for index, line in enumerate(lines[:body_start], start=1)
            if line.lower().startswith("topics:")
        ),
        1,
    )
    entities.extend(
        ExtractedEntity(
            EntityType.TOPIC,
            topic,
            SourceEvidence(topics_line, topic, None),
        )
        for topic in _frontmatter_topics(metadata.get("topics", ""))
    )
    role: str | None = None
    message_lines: list[tuple[int, str]] = []
    messages: list[CodexMessage] = []
    latest_claim: dict[EntityType, ExtractedEntity] = {}
    latest_any_claim: ExtractedEntity | None = None
    supersessions: list[SupersessionStatement] = []

    def flush_message() -> None:
        nonlocal message_lines
        meaningful = [(number, line) for number, line in message_lines if line.strip()]
        if role is not None and meaningful:
            messages.append(
                CodexMessage(
                    SourceEvidence(
                        meaningful[0][0],
                        "\n".join(line for _, line in meaningful).strip(),
                        role,
                    )
                )
            )
        message_lines = []

    for line_number, line in enumerate(lines[body_start:], start=body_start + 1):
        role_match = ROLE_PATTERN.match(line)
        if role_match:
            flush_message()
            role = role_match.group(1).lower()
            continue
        if role is not None:
            message_lines.append((line_number, line))
        claim_match = CLAIM_PATTERN.match(line)
        if claim_match:
            entity_type = EntityType(claim_match.group(1).lower())
            claim_text = claim_match.group(2).strip()
            inline_replacement = (
                INLINE_REPLACEMENT_PATTERN.match(claim_text)
                if entity_type in {EntityType.DECISION, EntityType.PLAN}
                else None
            )
            canonical_name = (
                inline_replacement.group(1).strip()
                if inline_replacement is not None
                else claim_text
            )
            entity = ExtractedEntity(
                entity_type,
                canonical_name,
                SourceEvidence(line_number, line.strip(), role),
            )
            entities.append(entity)
            if entity_type in {EntityType.DECISION, EntityType.PLAN}:
                latest_claim[entity_type] = entity
                latest_any_claim = entity
                if inline_replacement is not None:
                    supersessions.append(
                        SupersessionStatement(
                            entity_type,
                            entity.canonical_name,
                            _replacement_target(inline_replacement),
                            SourceEvidence(line_number, line.strip(), role),
                        )
                    )
            continue
        replacement_match = STANDALONE_REPLACEMENT_PATTERN.match(line)
        if replacement_match:
            explicit_type = replacement_match.group(1)
            entity_type = EntityType(explicit_type.lower()) if explicit_type else None
            replacement = (
                latest_claim.get(entity_type)
                if entity_type is not None
                else latest_any_claim
            )
            if replacement is not None:
                supersessions.append(
                    SupersessionStatement(
                        replacement.type,
                        replacement.canonical_name,
                        _replacement_target(replacement_match),
                        SourceEvidence(line_number, line.strip(), role),
                    )
                )
    flush_message()
    return CodexDocument(
        path=path,
        relative_path=path.relative_to(root).as_posix(),
        title=title,
        occurred_at=occurred_at,
        source_content_hash=hashlib.sha256(original.encode("utf-8")).hexdigest(),
        entities=tuple(entities),
        messages=tuple(messages),
        supersessions=tuple(supersessions),
        redactions=redactions,
    )
