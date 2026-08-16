"""Common normalized records emitted by Local Ontology import adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping


@dataclass(frozen=True)
class CandidateEntity:
    type: str
    canonical_name: str


@dataclass(frozen=True)
class ImportRecord:
    source_kind: str
    source_ref: str
    occurred_at: str
    raw_text_or_metadata: Mapping[str, Any]
    candidate_entities: tuple[CandidateEntity, ...]
    provenance: Mapping[str, Any]

    def content_hash(self) -> str:
        document = asdict(self)
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
