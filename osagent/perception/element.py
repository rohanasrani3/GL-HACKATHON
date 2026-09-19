"""The one shape every perception backend must produce."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class UIElement:
    id: str = ""
    role: str = ""
    name: str = ""
    value: str = ""
    app: str = ""
    window_title: str = ""
    bbox: list[int] = field(default_factory=lambda: [0, 0, 0, 0])  # x, y, w, h
    path: list[list[Any]] = field(default_factory=list)  # [[role, index], ...] from window root
    attrs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.stable_id()

    def stable_id(self) -> str:
        """Deterministic id from identity-ish fields, so the same control in two
        snapshots gets the same id even though the object is rebuilt."""
        seed = "|".join([self.app, self.window_title, self.role, self.name,
                         ".".join(f"{r}{i}" for r, i in self.path)])
        return hashlib.sha1(seed.encode("utf-8", "replace")).hexdigest()[:12]

    @property
    def center(self) -> tuple[int, int]:
        x, y, w, h = self.bbox
        return x + w // 2, y + h // 2

    @property
    def visible(self) -> bool:
        return self.bbox[2] > 0 and self.bbox[3] > 0

    def label(self) -> str:
        n = self.name or self.value or "<unnamed>"
        return f"{self.role}:{n}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UIElement":
        known = {k: d.get(k) for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)
