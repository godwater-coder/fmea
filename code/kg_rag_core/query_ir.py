# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class QueryEntity:
    kind: str
    value: str
    normalized: str = ""


@dataclass
class QueryConstraint:
    kind: str
    operator: str
    value: str


@dataclass
class QueryScope:
    domain: str = ""
    dataset_id: str = ""
    project: str = ""
    process_step: str = ""
    time_range: str = ""
    version: str = ""


@dataclass
class QueryIR:
    original_question: str
    normalized_question: str
    intent: str
    entities: list[QueryEntity] = field(default_factory=list)
    metric: str = ""
    constraints: list[QueryConstraint] = field(default_factory=list)
    scope: QueryScope = field(default_factory=QueryScope)
    output_type: str = ""
    query_variants: list[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_debug_dict(self) -> dict[str, object]:
        return asdict(self)
