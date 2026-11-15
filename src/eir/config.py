"""Configuration for the backend process."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str = "eir.sqlite3"

    def __post_init__(self) -> None:
        if not self.database_path.strip():
            raise ValueError("Database path must not be empty")

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(database_path=os.environ.get("EIR_DATABASE_PATH", "eir.sqlite3"))
