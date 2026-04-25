from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    label: str
    score: float
