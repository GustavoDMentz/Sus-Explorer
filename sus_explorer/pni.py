

from dataclasses import dataclass, asdict
import time
import unicodedata

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as pds
import pyarrow.fs as fs

from .config import settings
from .schemas import QueryPlan
from .terminology import terminology


ALIASES = {
    "municipality_code": [
        "co_municipio_estabelecimento",
        "co_municipio_ibge",
    ],
    "municipality_name": [
        "no_municipio_estabelecimento",
    ],
    "vaccine_code": [
        "co_vacina",
    ],
    "vaccine_text": [
        "ds_vacina",
        "sg_imunobiologico",
        "ds_nome",
    ],
    "sex": [
        "tp_sexo_paciente",
        "co_sexo",
    ],
    "age": [
        "nu_idade_paciente",
    ],
    "dose": [
        "ds_tipo_dose",
        "ds_dose_vacina",
        "co_dose_vacina",
        "co_dose",
    ],
    "facility": [
        "co_cnes_estabelecimento",
        "co_cnes",
    ],
    "system_origin": [
        "ds_sistema_origem",
        "co_sistema_origem",
    ],
    "race": [
        "no_raca_cor_paciente",
        "co_raca_cor_paciente",
        "co_raca_cor",
    ],
    "vaccination_date": [
        "dt_vacina",
    ],
    "rnds_entry_date": [
        "dt_entrada_rnds",
    ],
}


@dataclass
class QueryResult:
    operation: str
    data: dict
    provenance: dict
    warnings: list[str] | None = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

    def model_dump(self) -> dict:
        return asdict(self)


def ascii_upper(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(
        c for c in s
        if not unicodedata.combining(c)
    ).upper().strip()


def months(year: int, month: int, end_year: int, end_month: int):
    while (year, month) <= (end_year, end_month):
        yield year, month

        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


@dataclass
class PNIRemote:
    def __post_init__(self):
        if not all([
            settings.r2_endpoint,
            settings.r2_access_key,
            settings.r2_secret_key,
        ]):
            raise RuntimeError("Configuração R2 ausente no .env")

        self.s3 = fs.S3FileSystem(
            endpoint_override=settings.r2_endpoint,
            access_key=settings.r2_access_key,
            secret_key=settings.r2_secret_key,
            region=settings.r2_region,
        )  
   
    def path(self, year: int, month: int, uf: str) -> str:
        return (
            f"{settings.r2_bucket}/"
            f"{settings.r2_prefix}/"
            f"ano={year}/"
            f"mes={month:02d}/"
            f"uf={uf.upper()}/"
        )

    def dataset(self, year: int, month: int, uf: str):
        return pds.dataset(
            self.path(year, month, uf),
            filesystem=self.s3,
            format="parquet",
        )

    def col(self, ds, key: str) -> str:
        names = set(ds.schema.names)

        for candidate in ALIASES[key]:
            if candidate in names:
                return candidate

        raise KeyError(
            f"Coluna lógica {key!r} não encontrada. "
            f"Schema: {sorted(names)}"
        )

    def base_filter(self, ds, plan: QueryPlan):
        expr = None

        def add(value):
            nonlocal expr
            expr = value if expr is None else expr & value

        if plan.municipality_code:
            add(
                pds.field(self.col(ds, "municipality_code"))
                == str(plan.municipality_code)
            )
        elif plan.municipality_name:
            add(
                pds.field(self.col(ds, "municipality_name"))
                == ascii_upper(plan.municipality_name)
            )

        if plan.vaccine_code:
            add(
                pds.field(self.col(ds, "vaccine_code"))
                == str(plan.vaccine_code)
            )

        if plan.sex:
            add(
                pds.field(self.col(ds, "sex"))
                == plan.sex
            )

        return expr

    def post_cols(self, ds, plan: QueryPlan) -> list[str]:
        cols = []

        if plan.vaccine_text:
            cols.append(self.col(ds, "vaccine_text"))
            if terminology.resolve_text(plan.vaccine_text):
                cols.append(self.col(ds, "vaccine_code"))

        if plan.age_min is not None or plan.age_max is not None:
            cols.append(self.col(ds, "age"))

        return list(dict.fromkeys(cols))

    def post_filter(
        self,
        table: pa.Table,
        ds,
        plan: QueryPlan,
    ) -> pa.Table:
        mask = None

        def add(value):
            nonlocal mask
            mask = value if mask is None else pc.and_(mask, value)

        if plan.vaccine_text:
            column = self.col(ds, "vaccine_text")
            text = pc.utf8_upper(table[column])

            text_match = pc.fill_null(pc.match_substring(text, ascii_upper(plan.vaccine_text)), False)
            codes = terminology.resolve_text(plan.vaccine_text)
            if codes:
                code_column = pc.cast(table[self.col(ds, "vaccine_code")], pa.string())
                code_match = pc.is_in(code_column, value_set=pa.array(codes, type=pa.string()))
                text_match = pc.or_(text_match, pc.fill_null(code_match, False))
            add(text_match)

        if plan.age_min is not None or plan.age_max is not None:
            column = self.col(ds, "age")
            ages = pc.cast(
                table[column],
                pa.int64(),
                safe=False,
            )

            if plan.age_min is not None:
                add(pc.greater_equal(ages, plan.age_min))

            if plan.age_max is not None:
                add(pc.less_equal(ages, plan.age_max))

        if mask is None:
            return table

        return table.filter(pc.fill_null(mask, False))

    def provenance(
        self,
        ds,
        plan: QueryPlan,
        start: float,
        cols: list[str],
    ) -> dict:
        partition = None

        if (
            plan.year is not None
            and plan.month is not None
            and plan.uf
        ):
            partition = (
                f"ano={plan.year}/"
                f"mes={plan.month:02d}/"
                f"uf={plan.uf}"
            )

        return {
            "source": "SI-PNI / healthbr-data / OpenDATASUS",
            "partition": partition,
            "parquet_fragments": sum(
                1 for _ in ds.get_fragments()
            ),
            "columns_materialized": cols,
            "elapsed_seconds": round(
                time.perf_counter() - start,
                3,
            ),
            "microdata_sent_to_llm": False,
        }


    def plan_partitions(self, plan: QueryPlan) -> list[tuple[int, int]]:
        if plan.year is None:
            raise ValueError("Ano obrigatório para resolver partições.")

        if plan.month is not None:
            return [(plan.year, plan.month)]

        return [(plan.year, month) for month in range(1, 13)]

    def datasets_for_plan(
        self,
        plan: QueryPlan,
    ) -> tuple[list[tuple[int, int, object]], list[str]]:
        datasets = []
        missing_partitions = []

        for year, month in self.plan_partitions(plan):
            partition = (
                f"ano={year}/"
                f"mes={month:02d}/"
                f"uf={plan.uf}"
            )

            try:
                ds = self.dataset(year, month, plan.uf)
            except FileNotFoundError:
                missing_partitions.append(partition)
                continue

            datasets.append((year, month, ds))

        if not datasets:
            requested = f"ano={plan.year}/uf={plan.uf}"

            if plan.month is not None:
                requested = (
                    f"ano={plan.year}/"
                    f"mes={plan.month:02d}/"
                    f"uf={plan.uf}"
                )

            raise FileNotFoundError(
                "Nenhuma partição encontrada para " + requested
            )

        return datasets, missing_partitions

    def multi_provenance(
        self,
        plan: QueryPlan,
        start: float,
        datasets: list[tuple[int, int, object]],
        cols: list[str],
        missing_partitions: list[str] | None = None,
    ) -> dict:
        partitions = [
            f"ano={year}/mes={month:02d}/uf={plan.uf}"
            for year, month, _ in datasets
        ]

        fragments = sum(
            sum(1 for _ in ds.get_fragments())
            for _, _, ds in datasets
        )

        if plan.month is not None:
            period = f"{plan.year}-{plan.month:02d}"
            partition = partitions[0]
        else:
            period = str(plan.year)
            partition = None

        provenance = {
            "source": "SI-PNI / healthbr-data / OpenDATASUS",
            "period": period,
            "partition": partition,
            "partitions_consulted": len(partitions),
            "partitions": partitions,
            "parquet_fragments": fragments,
            "columns_materialized": sorted(set(cols)),
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "microdata_sent_to_llm": False,
        }

        if missing_partitions:
            provenance["missing_partitions"] = missing_partitions

        if plan.vaccine_text:
            provenance["vaccine_filter"] = self.vaccine_filter_provenance(plan)
        return provenance

    def vaccine_filter_provenance(self, plan):
        metadata = terminology.metadata()
        return {"requested_text": plan.vaccine_text,
                "resolved_codes": terminology.resolve_text(plan.vaccine_text),
                "method": "source_text_or_authoritative_code_v1",
                "terminology_source": "MS + SES-GO",
                "ms_version": metadata.get("ms", {}).get("version"),
                "ses_go_version": metadata.get("ses_go", {}).get("version")}

    def count(self, plan: QueryPlan) -> QueryResult:
        start = time.perf_counter()

        datasets, missing_partitions = self.datasets_for_plan(plan)

        total = 0
        materialized_cols = []

        for _, _, ds in datasets:
            base_filter = self.base_filter(ds, plan)
            cols = self.post_cols(ds, plan)
            materialized_cols.extend(cols)

            if cols:
                table = ds.to_table(
                    columns=cols,
                    filter=base_filter,
                )
                table = self.post_filter(
                    table,
                    ds,
                    plan,
                )
                total += table.num_rows
            else:
                total += ds.count_rows(
                    filter=base_filter
                )

        warnings = []

        if missing_partitions:
            warnings.append(
                "Algumas partições mensais não estavam disponíveis "
                "e foram ignoradas: "
                + ", ".join(missing_partitions)
            )

        return QueryResult(
            operation="count",
            data={"doses": int(total)},
            provenance=self.multi_provenance(
                plan=plan,
                start=start,
                datasets=datasets,
                cols=materialized_cols,
                missing_partitions=missing_partitions,
            ),
            warnings=warnings,
        )

    def group(self, plan: QueryPlan) -> QueryResult:
        start = time.perf_counter()

        logical_map = {
            "vaccine": "vaccine_text",
            "municipality": "municipality_name",
            "sex": "sex",
            "age": "age",
            "dose": "dose",
            "facility": "facility",
            "system_origin": "system_origin",
            "race": "race",
        }

        if plan.group_by not in logical_map:
            raise ValueError(
                f"group_by inválido: {plan.group_by!r}"
            )

        datasets, missing_partitions = self.datasets_for_plan(plan)

        total_after_filters = 0
        materialized_cols = []

        if plan.group_by == "vaccine":
            # co_vacina é a identidade canônica.
            #
            # ds_vacina/sg_imunobiologico é texto de origem e pode variar
            # entre registros ("Vacina influenza trivalente" vs
            # "Vacinainfluenzatrivalente"). Portanto NÃO participa da
            # identidade do grupo.
            aggregate = {}

            for _, _, ds in datasets:
                base_filter = self.base_filter(ds, plan)
                group_col = self.col(ds, "vaccine_text")
                code_col = self.col(ds, "vaccine_code")

                cols = [
                    code_col,
                    group_col,
                    *self.post_cols(ds, plan),
                ]
                cols = list(dict.fromkeys(cols))
                materialized_cols.extend(cols)

                table = ds.to_table(
                    columns=cols,
                    filter=base_filter,
                )
                table = self.post_filter(
                    table,
                    ds,
                    plan,
                )

                total_after_filters += table.num_rows

                pdf = table.select(
                    [code_col, group_col]
                ).to_pandas()

                # Agrupa localmente por código e preserva todas as grafias
                # observadas apenas para auditoria/proveniência.
                for code_value, frame in pdf.groupby(
                    code_col,
                    dropna=False,
                ):
                    code = (
                        None
                        if pd.isna(code_value)
                        else str(code_value)
                    )

                    source_displays = sorted({
                        str(value).strip()
                        for value in frame[group_col].dropna().tolist()
                        if str(value).strip()
                    })

                    key = code

                    if key not in aggregate:
                        aggregate[key] = {
                            "count": 0,
                            "source_displays": set(),
                        }

                    aggregate[key]["count"] += int(len(frame))
                    aggregate[key]["source_displays"].update(
                        source_displays
                    )

            ranked = sorted(
                aggregate.items(),
                key=lambda item: item[1]["count"],
                reverse=True,
            )[
                :min(
                    plan.top_n,
                    settings.max_group_rows,
                )
            ]

            rows = []

            for code, item in ranked:
                official = (
                    terminology.lookup(code)
                    if code
                    else None
                )

                source_displays = sorted(
                    item["source_displays"]
                )

                # Para códigos conhecidos, a terminologia oficial manda.
                # Para código ausente/desconhecido, usamos uma grafia do
                # próprio dado apenas como fallback de apresentação.
                if official:
                    display = official.get("official_display")
                    definition = official.get("definition")
                    definition_source = official.get(
                        "definition_source"
                    )
                    conflict = bool(
                        official.get("conflict")
                    )
                else:
                    display = (
                        source_displays[0]
                        if source_displays
                        else None
                    )
                    definition = None
                    definition_source = None
                    conflict = False

                rows.append({
                    "code": code,
                    "display": display,
                    "official_display": (
                        official.get("official_display")
                        if official
                        else None
                    ),
                    "definition": definition,
                    "definition_source": definition_source,
                    "terminology_conflict": conflict,
                    "source_displays": source_displays,
                    "source_display_variants": len(
                        source_displays
                    ),
                    "count": int(item["count"]),
                })

        else:
            aggregate = {}
            logical = logical_map[plan.group_by]

            for _, _, ds in datasets:
                base_filter = self.base_filter(ds, plan)
                group_col = self.col(ds, logical)

                cols = [
                    group_col,
                    *self.post_cols(ds, plan),
                ]
                cols = list(dict.fromkeys(cols))
                materialized_cols.extend(cols)

                table = ds.to_table(
                    columns=cols,
                    filter=base_filter,
                )
                table = self.post_filter(
                    table,
                    ds,
                    plan,
                )

                total_after_filters += table.num_rows

                counts = pc.value_counts(
                    table[group_col].combine_chunks()
                ).to_pylist()

                for item in counts:
                    value = item["values"]
                    count = int(item["counts"])
                    aggregate[value] = (
                        aggregate.get(value, 0)
                        + count
                    )

            rows = [
                {
                    "value": value,
                    "count": count,
                }
                for value, count in sorted(
                    aggregate.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )[
                    :min(
                        plan.top_n,
                        settings.max_group_rows,
                    )
                ]
            ]

        provenance = self.multi_provenance(
            plan=plan,
            start=start,
            datasets=datasets,
            cols=materialized_cols,
            missing_partitions=missing_partitions,
        )

        if plan.group_by == "vaccine":
            provenance["terminology"] = terminology.metadata()
            provenance["vaccine_grouping"] = {
                "canonical_key": "co_vacina",
                "source_display_role": "audit_only",
                "source_display_variants_preserved": True,
            }

        warnings = []

        if missing_partitions:
            warnings.append(
                "Algumas partições mensais não estavam disponíveis "
                "e foram ignoradas: "
                + ", ".join(missing_partitions)
            )

        return QueryResult(
            operation="group",
            data={
                "group_by": plan.group_by,
                "rows": rows,
                "total_after_filters": total_after_filters,
            },
            provenance=provenance,
            warnings=warnings,
        )

    def timeseries(self, plan: QueryPlan) -> QueryResult:
        start = time.perf_counter()

        rows = []
        fragments = 0
        partitions = 0
        missing_partitions = []

        for year, month in months(
            plan.start_year,
            plan.start_month,
            plan.end_year,
            plan.end_month,
        ):
            try:
                ds = self.dataset(
                    year,
                    month,
                    plan.uf,
                )
            except FileNotFoundError:
                missing_partitions.append(
                    f"ano={year}/mes={month:02d}/uf={plan.uf}"
                )
                continue

            base_filter = self.base_filter(ds, plan)
            cols = self.post_cols(ds, plan)

            if cols:
                table = ds.to_table(
                    columns=cols,
                    filter=base_filter,
                )
                count = self.post_filter(
                    table,
                    ds,
                    plan,
                ).num_rows
            else:
                count = ds.count_rows(
                    filter=base_filter
                )

            rows.append({
                "period": f"{year}-{month:02d}",
                "doses": int(count),
            })

            partitions += 1
            fragments += sum(
                1 for _ in ds.get_fragments()
            )

        if not rows:
            raise FileNotFoundError(
                "Nenhuma partição encontrada "
                "para o intervalo solicitado."
            )

        warnings = []

        if missing_partitions:
            warnings.append(
                "Algumas partições mensais não estavam disponíveis "
                "e foram ignoradas: "
                + ", ".join(missing_partitions)
            )

        return QueryResult(
            operation="timeseries",
            data={"rows": rows},
            provenance={
                "source": "SI-PNI / healthbr-data / OpenDATASUS",
                "uf_partition": plan.uf,
                **({"vaccine_filter": self.vaccine_filter_provenance(plan)} if plan.vaccine_text else {}),
                "partitions_consulted": partitions,
                "missing_partitions": missing_partitions,
                "parquet_fragments": fragments,
                "elapsed_seconds": round(
                    time.perf_counter() - start,
                    3,
                ),
                "microdata_sent_to_llm": False,
            },
            warnings=warnings,
        )

    def latency(self, plan: QueryPlan) -> QueryResult:
        start = time.perf_counter()

        datasets, missing_partitions = self.datasets_for_plan(plan)

        chunks = []
        valid = 0
        materialized_cols = []

        for _, _, ds in datasets:
            base_filter = self.base_filter(ds, plan)

            vaccination_col = self.col(
                ds,
                "vaccination_date",
            )
            rnds_col = self.col(
                ds,
                "rnds_entry_date",
            )

            cols = list(
                dict.fromkeys([
                    vaccination_col,
                    rnds_col,
                    *self.post_cols(ds, plan),
                ])
            )
            materialized_cols.extend(cols)

            scanner = ds.scanner(
                columns=cols,
                filter=base_filter,
                batch_size=50000,
                use_threads=False,
            )

            for batch in scanner.to_batches():
                table = pa.Table.from_batches([batch])
                table = self.post_filter(
                    table,
                    ds,
                    plan,
                )

                if table.num_rows == 0:
                    continue

                pdf = table.select(
                    [
                        vaccination_col,
                        rnds_col,
                    ]
                ).to_pandas()

                vaccination_date = pd.to_datetime(
                    pdf[vaccination_col],
                    errors="coerce",
                    utc=True,
                )
                rnds_date = pd.to_datetime(
                    pdf[rnds_col],
                    errors="coerce",
                    utc=True,
                )

                delta_days = (
                    rnds_date
                    - vaccination_date
                ).dt.total_seconds().div(86400)

                delta_days = delta_days[
                    delta_days.notna()
                    & (delta_days >= 0)
                ]

                if len(delta_days):
                    chunks.append(
                        delta_days.to_numpy(
                            dtype="float64",
                            copy=False,
                        )
                    )
                    valid += len(delta_days)

        if chunks:
            values = np.concatenate(chunks)

            data = {
                "n_valid": int(valid),
                "median_days": round(
                    float(np.median(values)),
                    3,
                ),
                "p90_days": round(
                    float(np.quantile(values, 0.90)),
                    3,
                ),
                "p95_days": round(
                    float(np.quantile(values, 0.95)),
                    3,
                ),
            }
        else:
            data = {
                "n_valid": 0,
                "median_days": None,
                "p90_days": None,
                "p95_days": None,
            }

        warnings = [
            (
                "Latência de registro não mede "
                "qualidade clínica nem prova "
                "atraso operacional."
            )
        ]

        if missing_partitions:
            warnings.append(
                "Algumas partições mensais não estavam disponíveis "
                "e foram ignoradas: "
                + ", ".join(missing_partitions)
            )

        return QueryResult(
            operation="latency",
            data=data,
            provenance=self.multi_provenance(
                plan=plan,
                start=start,
                datasets=datasets,
                cols=materialized_cols,
                missing_partitions=missing_partitions,
            ),
            warnings=warnings,
        )

    def execute(self, plan: QueryPlan) -> QueryResult:
        if plan.operation == "temporal":
            from .analytics.temporal_query import execute_temporal

            return execute_temporal(plan, self.execute)

        operations = {
            "count": self.count,
            "group": self.group,
            "timeseries": self.timeseries,
            "latency": self.latency,
        }

        if getattr(plan, "status", "ready") != "ready":
            raise ValueError(
                "Tentativa de executar um plano "
                "que ainda precisa de esclarecimento."
            )

        if plan.operation not in operations:
            raise ValueError(
                f"Operação inválida: {plan.operation!r}"
            )

        if not plan.uf:
            raise ValueError(
                "UF obrigatória ausente."
            )

        if plan.operation in {
            "count",
            "group",
            "latency",
        }:
            if plan.year is None:
                raise ValueError(
                    "Ano obrigatório ausente."
                )

            # month=None significa ano inteiro.

        if plan.operation == "timeseries":
            required = {
                "start_year": plan.start_year,
                "start_month": plan.start_month,
                "end_year": plan.end_year,
                "end_month": plan.end_month,
            }

            missing = [
                name
                for name, value
                in required.items()
                if value is None
            ]

            if missing:
                raise ValueError(
                    "Período incompleto para timeseries: "
                    + ", ".join(missing)
                )

        return operations[plan.operation](plan)
