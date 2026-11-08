"""Legacy R2 configuration used only by explicit migration/audit tools."""
from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class LegacyR2Settings:
    r2_endpoint: str = os.getenv('LEGACY_R2_ENDPOINT','')
    r2_access_key: str = os.getenv('LEGACY_R2_ACCESS_KEY','')
    r2_secret_key: str = os.getenv('LEGACY_R2_SECRET_KEY','')
    r2_region: str = os.getenv('LEGACY_R2_REGION','auto')
    r2_bucket: str = os.getenv('LEGACY_R2_BUCKET','healthbr-data')
    r2_prefix: str = os.getenv('LEGACY_R2_PREFIX','sipni/microdados')
    max_group_rows: int = int(os.getenv('MAX_GROUP_ROWS','50'))
    # Cubo SI-PNI no bucket de auditoria (sus-dados) — credenciais independentes
    sus_data_r2_endpoint: str = os.getenv('LEGACY_AUDIT_R2_ENDPOINT','')
    sus_data_r2_access_key: str = os.getenv('LEGACY_AUDIT_R2_ACCESS_KEY_ID','')
    sus_data_r2_secret_key: str = os.getenv('LEGACY_AUDIT_R2_SECRET_ACCESS_KEY','')
    sus_data_r2_bucket: str = os.getenv('LEGACY_AUDIT_R2_BUCKET','sus-dados')
    sus_data_r2_cube_prefix: str = os.getenv('LEGACY_AUDIT_R2_CUBE_PREFIX','cache/pni_cube')
settings = LegacyR2Settings()
