"""
Ghost Layer Studio — Core Types

Responsibilities:
- Define shared, dependency-free data models used across core/ and agents/
- IntentVector: canonical representation of an incoming intent
- OperatorAxis: operator alignment/doctrine/signature metadata
- Has no dependency on core.engine, breaking the historical circular import
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class OperatorAxis:
    alignment: str = "operator-defensive"
    doctrine: str = "bounded-escalation"
    signature: str = "MatrixSecHub"


@dataclass
class IntentVector:
    id: str
    source: str
    description: str
    tags: List[str] = field(default_factory=list)
