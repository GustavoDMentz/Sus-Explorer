from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

# Public, read-only S3 credentials intentionally published by the healthbr-data maintainer:
# https://github.com/SidneyBissoli/healthbr-data (README, Python/PyArrow quick start).
# These are NOT private application secrets. Environment variables override these defaults.

@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv('GEMINI_API_KEY','')
    gemini_model: str = os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite')
    r2_endpoint: str = os.getenv('R2_ENDPOINT','https://5c499208eebced4e34bd98ffa204f2fb.r2.cloudflarestorage.com')
    r2_access_key: str = os.getenv('R2_ACCESS_KEY','28c72d4b3e1140fa468e367ae472b522')
    r2_secret_key: str = os.getenv('R2_SECRET_KEY','2937b2106736e2ba64e24e92f2be4e6c312bba3355586e41ce634b14c1482951')
    r2_region: str = os.getenv('R2_REGION','auto')
    r2_bucket: str = os.getenv('R2_BUCKET','healthbr-data')
    r2_prefix: str = os.getenv('R2_PREFIX','sipni/microdados')
    max_group_rows: int = int(os.getenv('MAX_GROUP_ROWS','50'))
    # Cubo SI-PNI no bucket de auditoria (sus-dados) — credenciais independentes
    sus_data_r2_endpoint: str = os.getenv('SUS_DATA_R2_ENDPOINT','')
    sus_data_r2_access_key: str = os.getenv('SUS_DATA_R2_ACCESS_KEY_ID','')
    sus_data_r2_secret_key: str = os.getenv('SUS_DATA_R2_SECRET_ACCESS_KEY','')
    sus_data_r2_bucket: str = os.getenv('SUS_DATA_R2_BUCKET','sus-dados')
    sus_data_r2_cube_prefix: str = os.getenv('SUS_DATA_R2_CUBE_PREFIX','cache/pni_cube')
settings=Settings()
