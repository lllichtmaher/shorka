"""Voice profile loader with fuzzy matching."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process


@dataclass
class VoiceProfile:
    key: str
    id: str
    name: str
    aliases: list[str]


class Voices:
    def __init__(self, default_key: str, profiles: dict[str, VoiceProfile]) -> None:
        if default_key not in profiles:
            raise ValueError(f"default voice '{default_key}' not in profiles")
        self.default_key = default_key
        self.profiles = profiles

    @classmethod
    def load(cls, path: Path) -> "Voices":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        profiles = {
            key: VoiceProfile(
                key=key,
                id=p["id"],
                name=p["name"],
                aliases=list(p.get("aliases", [])),
            )
            for key, p in data["profiles"].items()
        }
        return cls(default_key=data["default"], profiles=profiles)

    def default(self) -> VoiceProfile:
        return self.profiles[self.default_key]

    def find(self, query: str) -> Optional[VoiceProfile]:
        """Fuzzy-match a query against keys, names, and aliases."""
        if not query:
            return None
        candidates: dict[str, str] = {}  # surface → profile key
        for key, p in self.profiles.items():
            candidates[key.lower()] = key
            candidates[p.name.lower()] = key
            for alias in p.aliases:
                candidates[alias.lower()] = key
        match = process.extractOne(
            query.lower(),
            list(candidates.keys()),
            scorer=fuzz.WRatio,
            score_cutoff=60,
        )
        if match is None:
            return None
        return self.profiles[candidates[match[0]]]

    def all(self) -> list[VoiceProfile]:
        return list(self.profiles.values())
