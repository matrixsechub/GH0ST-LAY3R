"""
Ghost Layer Studio — Intent model

Leaf module shared by the engine and every subsystem (physics, oversoul,
output, constellation). It must not import from core.engine, which imports
those subsystems; keeping IntentVector here breaks that import cycle.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class IntentVector:
    id: str
    source: str
    description: str
    tags: List[str] = field(default_factory=list)
