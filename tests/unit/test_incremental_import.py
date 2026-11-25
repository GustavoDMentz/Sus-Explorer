import hashlib
import io
import json
from pathlib import Path

from sus_explorer.data.remote.incremental_import import (
    download_competence, import_competence,
)


URL = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_jan_2026_csv.zip"


class Response(io.BytesIO):
    def __init__(self, content, status, headers=None):
        super().__init__(content)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def entry(content):
    return {"year": 2026, "month": 1, "resource_id": "resource-1", "url": URL,
            "content_length": len(content), "etag": '"snapshot-1"'}


def test_download_resumes_matching_partial_and_hashes_result(tmp_path):
    content = b"0123456789"
    partial = tmp_path / "vacinacao_jan_2026_csv.zip.part"
    partial.write_bytes(content[:4])
    partial.with_suffix(".part.json").write_text(json.dumps({
        "url": URL, "content_length": len(content), "etag": '"snapshot-1"'
    }), "utf-8")

    def opener(request, timeout):
        assert request.headers["Range"] == "bytes=4-"
        assert request.headers["If-range"] == '"snapshot-1"'
        return Response(content[4:], 206, {
            "ETag": '"snapshot-1"', "Content-Range": "bytes 4-9/10"
        })

    result = download_competence(entry(content), tmp_path, opener=opener,
                                 chunk_size=64 * 1024)
    assert result.path.read_bytes() == content
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.created_by_job
    assert not partial.exists()


def test_existing_zip_is_never_owned_or_deleted(tmp_path):
    content = b"existing source"
    path = tmp_path / "vacinacao_jan_2026_csv.zip"
    path.write_bytes(content)
    calls = []

    def ingest(source, **kwargs):
        calls.append((source, kwargs["uf"]))
        return {"id": len(calls), "status": "SUCCESS", "records_received": 3}

    checkpoint = import_competence(entry(content), tmp_path, ufs=["AC", "AL"],
                                   delete_after_success=True, ingest=ingest)
    assert checkpoint["complete"] is True
    assert path.exists()
    assert calls == [(path, "AC"), (path, "AL")]


def test_checkpoint_skips_reconciled_partitions_on_retry(tmp_path):
    content = b"source"
    path = tmp_path / "vacinacao_jan_2026_csv.zip"
    path.write_bytes(content)
    checkpoint_path = tmp_path / "import-2026-01.json"
    checkpoint_path.write_text(json.dumps({
        "year": 2026, "month": 1,
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "source_size": len(content),
        "partitions": {"AC": {"status": "SUCCESS", "ingestion_run_id": 7,
                                "records_received": 10}},
    }), "utf-8")
    imported = []

    def ingest(source, **kwargs):
        imported.append(kwargs["uf"])
        return {"id": 8, "status": "SUCCESS", "records_received": 11}

    result = import_competence(entry(content), tmp_path, ufs=["AC", "AL"], ingest=ingest)
    assert imported == ["AL"]
    assert result["partitions"]["AC"]["ingestion_run_id"] == 7
    assert result["partitions"]["AL"]["ingestion_run_id"] == 8


def test_job_created_zip_is_removed_only_after_all_selected_ufs_succeed(tmp_path):
    content = b"downloaded"

    def opener(request, timeout):
        return Response(content, 200)

    def ingest(source, **kwargs):
        return {"id": 1, "status": "SUCCESS", "records_received": 1}

    result = import_competence(entry(content), tmp_path, ufs=["AC"],
                               delete_after_success=True, opener=opener, ingest=ingest)
    assert result["staging_file_removed"] is True
    assert not (tmp_path / "vacinacao_jan_2026_csv.zip").exists()
    assert (tmp_path / "import-2026-01.json").exists()


def test_retry_recognizes_job_owned_download_and_can_clean_it(tmp_path):
    content = b"downloaded"
    source = tmp_path / "vacinacao_jan_2026_csv.zip"

    def opener(request, timeout):
        return Response(content, 200, {"ETag": '"snapshot-1"'})

    first = download_competence(entry(content), tmp_path, opener=opener)
    assert first.created_by_job is True
    second = download_competence(entry(content), tmp_path,
                                 opener=lambda *_args, **_kwargs: None)
    assert second.created_by_job is True
    assert source.exists()
