from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Settings:
    max_group_rows: int = int(os.getenv('MAX_GROUP_ROWS','50'))
settings=Settings()
