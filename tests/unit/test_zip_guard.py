import io
import zipfile

import pytest

from sus_explorer.data import zip_guard
from sus_explorer.data.zip_guard import UnsafeZipError, check_archive


def make_zip(members, compression=zipfile.ZIP_STORED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, data in members:
            archive.writestr(name, data)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


def test_normal_archive_passes():
    check_archive(make_zip([("a.csv", b"x;y\n1;2\n")]), "a.csv")


def test_too_many_members_rejected():
    archive = make_zip([(f"f{i}.txt", b"x") for i in range(zip_guard.MAX_MEMBERS + 1)])
    with pytest.raises(UnsafeZipError, match="membros"):
        check_archive(archive)


def test_duplicate_member_names_rejected():
    with pytest.warns(UserWarning):          # o zipfile avisa ao gravar nome duplicado
        archive = make_zip([("a.csv", b"1"), ("a.csv", b"2")])
    with pytest.raises(UnsafeZipError, match="duplicados"):
        check_archive(archive)


@pytest.mark.parametrize("name", ["../evil.csv", "/abs.csv", "a/../../b.csv", "\\root.csv"])
def test_suspicious_member_paths_rejected(name):
    with pytest.raises(UnsafeZipError, match="caminho"):
        check_archive(make_zip([(name, b"x")]))


def test_declared_size_limit_is_enforced(monkeypatch):
    monkeypatch.setenv("SUS_ZIP_MAX_UNCOMPRESSED_BYTES", "10")
    with pytest.raises(UnsafeZipError, match="tamanho"):
        check_archive(make_zip([("a.csv", b"x" * 11)]), "a.csv")
    check_archive(make_zip([("a.csv", b"x" * 10)]), "a.csv")


def test_zip_bomb_ratio_is_rejected():
    bomb = make_zip([("a.csv", b"0" * 5_000_000)], compression=zipfile.ZIP_DEFLATED)
    with pytest.raises(UnsafeZipError, match="compressão"):
        check_archive(bomb, "a.csv")


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_invalid_limit_setting_is_rejected(monkeypatch, value):
    monkeypatch.setenv("SUS_ZIP_MAX_UNCOMPRESSED_BYTES", value)
    with pytest.raises(UnsafeZipError):
        zip_guard.max_uncompressed_bytes()


def test_ingest_csv_applies_the_guard(tmp_path, monkeypatch):
    from sus_explorer.data.persistence import ingest_csv
    path = tmp_path / "m.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("m.csv", "0" * 5_000_000)
    with pytest.raises(UnsafeZipError):
        with ingest_csv._open_reader(path, encoding="utf-8", delimiter=";"):
            pass
