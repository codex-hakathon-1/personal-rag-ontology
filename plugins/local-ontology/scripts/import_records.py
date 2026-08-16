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

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def raw_metadata_json(self) -> str:
        return self._json(self.raw_text_or_metadata)

    def candidate_entities_json(self) -> str:
        return self._json([asdict(entity) for entity in self.candidate_entities])

    def provenance_json(self) -> str:
        return self._json(self.provenance)

    def content_hash(self) -> str:
        document = asdict(self)
        encoded = self._json(document).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
