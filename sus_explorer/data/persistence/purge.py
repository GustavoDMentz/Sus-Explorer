"""Administrative purge of stored source data (retention, see docs/data-retention.md).

Two scopes, both **dry-run by default** and both written to ``datasus_purge_audit``:

* ``partition``      removes the raw records, their revision history, observations and
                     typed projection of ONE ``ano=AAAA/mes=MM/uf=XX`` partition. The
                     ingestion runs are kept (they hold only hashes and counts). The app
                     then reports the partition as unavailable until it is imported again.
* ``old_revisions``  removes archived (superseded) payload versions older than N days and
                     keeps the current version of every record.

The tables are append-only for every role. Only the schema owner (the migrator role) can
disable the immutability triggers, and it does so inside one transaction that re-enables
them before committing, so a failure leaves nothing removed and the triggers intact.

    python -m sus_explorer.data.persistence.purge --scope partition \
        --partition ano=2026/mes=01/uf=RS --reason "retirada solicitada pela fonte"
    ... --execute        # without it nothing is removed
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from .database import connect_migrator
from .operational_events import event

PARTITION = re.compile(r"ano=[0-9]{4}/mes=(0[1-9]|1[0-2])/uf=[A-Z]{2}")
MIN_REASON = 10
MAX_REASON = 500
LOCK_NAMESPACE = 91627135        # same advisory-lock space as the importers

_RESOURCES = """SELECT DISTINCT source, resource_type, source_resource_id
                FROM datasus_ingestion_runs WHERE metadata->>'partition' = %s"""
_RAW_OF_PARTITION = """SELECT r.id FROM datasus_raw_records r
    JOIN datasus_ingestion_runs run ON r.source = run.source
     AND r.resource_type = run.resource_type AND r.source_resource_id = run.source_resource_id
    WHERE run.metadata->>'partition' = %s"""


class PurgeError(RuntimeError):
    pass


def _validate(scope, reason, partition, older_than_days):
    if not isinstance(reason, str) or not MIN_REASON <= len(reason.strip()) <= MAX_REASON:
        raise PurgeError(f"--reason é obrigatório ({MIN_REASON} a {MAX_REASON} caracteres)")
    if scope == "partition":
        if not isinstance(partition, str) or not PARTITION.fullmatch(partition):
            raise PurgeError("--partition deve ter o formato ano=AAAA/mes=MM/uf=XX")
        if older_than_days is not None:
            raise PurgeError("--older-than-days não se aplica ao escopo partition")
    elif scope == "old_revisions":
        if partition is not None:
            raise PurgeError("--partition não se aplica ao escopo old_revisions")
        if not isinstance(older_than_days, int) or isinstance(older_than_days, bool) or older_than_days < 1:
            raise PurgeError("--older-than-days deve ser um inteiro maior ou igual a 1")
    else:
        raise PurgeError("escopo inválido")


def _count(connection, query, values=()):
    return connection.execute(query, values).fetchone()["n"]


def _partition_counts(connection, partition):
    return {
        "raw_records": _count(connection, f"SELECT count(*) AS n FROM ({_RAW_OF_PARTITION}) x", (partition,)),
        "revisions": _count(connection, f"""SELECT count(*) AS n FROM datasus_raw_record_revisions
            WHERE raw_record_id IN ({_RAW_OF_PARTITION})""", (partition,)),
        "observations": _count(connection, f"""SELECT count(*) AS n FROM datasus_raw_record_observations
            WHERE raw_record_id IN ({_RAW_OF_PARTITION})""", (partition,)),
        "immunization_records": _count(connection, f"""SELECT count(*) AS n FROM immunization_records
            WHERE source_record_id IN ({_RAW_OF_PARTITION})""", (partition,)),
    }


def _revision_counts(connection, days):
    return {"revisions": _count(connection, """SELECT count(*) AS n FROM datasus_raw_record_revisions
            WHERE superseded_at < clock_timestamp() - make_interval(days => %s)""", (days,))}


def purge(connection, *, scope: str, reason: str, partition: str | None = None,
          older_than_days: int | None = None, execute: bool = False) -> dict:
    """Plan (default) or perform a purge. Returns the counts that were or would be removed."""
    _validate(scope, reason, partition, older_than_days)
    reason = reason.strip()
    locks = []
    try:
        if scope == "partition":
            running = _count(connection, """SELECT count(*) AS n FROM datasus_ingestion_runs
                WHERE metadata->>'partition' = %s AND status = 'RUNNING'""", (partition,))
            if running:
                raise PurgeError("Há uma ingestão em andamento nesta partição; aguarde ou feche a execução órfã")
            for row in connection.execute(_RESOURCES, (partition,)).fetchall():
                got = connection.execute("SELECT pg_try_advisory_lock(%s, hashtext(%s)) AS ok",
                                         (LOCK_NAMESPACE, row["source_resource_id"])).fetchone()["ok"]
                if not got:
                    raise PurgeError("Outra ingestão ocupa esta partição")
                locks.append(row["source_resource_id"])
            connection.commit()
            counts = _partition_counts(connection, partition)
        else:
            counts = _revision_counts(connection, older_than_days)
        counts = {"dry_run": not execute, **counts}
        if not execute:
            _audit(connection, scope, partition, older_than_days, True, reason, counts)
            connection.commit()
            event("purge_planned", scope=scope, partition=partition, counts=counts)
            return counts
        try:
            with connection.transaction():
                connection.execute("SET LOCAL lock_timeout = '10s'")
                connection.execute("ALTER TABLE datasus_raw_record_revisions DISABLE TRIGGER raw_revisions_immutable")
                connection.execute("ALTER TABLE datasus_raw_record_observations DISABLE TRIGGER raw_observations_immutable")
                if scope == "partition":
                    ids = f"SELECT id FROM ({_RAW_OF_PARTITION}) x"
                    connection.execute(f"DELETE FROM datasus_raw_record_observations WHERE raw_record_id IN ({ids})", (partition,))
                    connection.execute(f"DELETE FROM datasus_raw_record_revisions WHERE raw_record_id IN ({ids})", (partition,))
                    connection.execute(f"DELETE FROM immunization_records WHERE source_record_id IN ({ids})", (partition,))
                    connection.execute(f"DELETE FROM datasus_raw_records WHERE id IN ({ids})", (partition,))
                else:
                    connection.execute("""DELETE FROM datasus_raw_record_revisions
                        WHERE superseded_at < clock_timestamp() - make_interval(days => %s)""", (older_than_days,))
                connection.execute("ALTER TABLE datasus_raw_record_revisions ENABLE TRIGGER raw_revisions_immutable")
                connection.execute("ALTER TABLE datasus_raw_record_observations ENABLE TRIGGER raw_observations_immutable")
                _audit(connection, scope, partition, older_than_days, False, reason, counts)
        except Exception as exc:
            connection.rollback()
            event("purge_failed", level="ERROR", scope=scope, error_type=type(exc).__name__)
            raise PurgeError("Falha no expurgo; nada foi removido (requer o papel proprietário do schema)") from exc
        event("purge_executed", scope=scope, partition=partition, counts=counts)
        return counts
    finally:
        for resource in locks:
            try:
                connection.execute("SELECT pg_advisory_unlock(%s, hashtext(%s))", (LOCK_NAMESPACE, resource))
                connection.commit()
            except Exception:
                connection.rollback()


def _audit(connection, scope, partition, older_than_days, dry_run, reason, counts):
    connection.execute(
        """INSERT INTO datasus_purge_audit (scope, partition, older_than_days, dry_run, reason, counts)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
        (scope, partition, older_than_days, dry_run, reason, json.dumps(counts)),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Expurgo administrativo (simulação por padrão)")
    parser.add_argument("--scope", choices=("partition", "old_revisions"), required=True)
    parser.add_argument("--partition", help="ano=AAAA/mes=MM/uf=XX (escopo partition)")
    parser.add_argument("--older-than-days", type=int, help="idade mínima das revisões (escopo old_revisions)")
    parser.add_argument("--reason", required=True, help="motivo, registrado na auditoria")
    parser.add_argument("--execute", action="store_true", help="remove de fato; sem isto é só simulação")
    args = parser.parse_args(argv)
    try:
        with connect_migrator() as connection:
            result = purge(connection, scope=args.scope, reason=args.reason, partition=args.partition,
                           older_than_days=args.older_than_days, execute=args.execute)
    except PurgeError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["dry_run"]:
        print("Simulação: nada foi removido. Reexecute com --execute para remover.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
