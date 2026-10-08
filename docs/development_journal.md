# Diário técnico do SUS Explorer

> **Atualização contemporânea — 2026-10-07**
>
> **Intervalo total coberto:** 2026-09-19 a 2026-10-07.
>
> A nota metodológica e todo o texto histórico abaixo, até “Débitos técnicos conhecidos”, são a **reconstrução retrospectiva de 2026-09-19 a 2026-09-26**, preservada integralmente. Seu intervalo, inventário, pendências e afirmações de ausência de evidência descrevem aquela revisão histórica; não são automaticamente afirmações sobre o estado atual.
>
> A seção acrescentada ao final é **documentação contemporânea consolidada em 2026-10-07**, baseada em commits, diffs, PRs, logs de CI e arquivos versionados consultados nessa data. Datas da nova cronologia usam **America/Sao_Paulo (UTC−03:00)**; timestamps UTC aparecem quando necessários para rastrear a evidência. A referência atual é `master` em `fc446cb00eed33b580be9cd08bbb3b9091b7d4df`. Não foram reinspecionados os discos, snapshots ZIP, histórico de shell ou buckets usados na reconstrução antiga.

> **Nota metodológica**
>
> Este diário foi reconstruído **retrosivamente** a partir das evidências disponíveis no repositório e no histórico operacional da máquina de desenvolvimento. As fontes usadas foram:
>
> - histórico Git completo do repositório (`git log --all --graph --decorate --date=iso`), incluindo mensagens, timestamps e diffs;
> - metadados de tempo de modificação (`mtime`) dos artefatos em disco (`cache/pni_cube/`, `audit/`, documentos);
> - artefatos produzidos pelo projeto: `cache/pni_cube/manifest.json`, `audit/ms_crosscheck/2023_10_summary.json`, `audit/ms_crosscheck/2023_10_unpartitionable.jsonl`;
> - documentação versionada (`README.md`, `docs/architecture.md`, `docs/refactor_findings.md`) e documentação adjacente não versionada, em `../SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` e `../sus_explorer_provenance.json` (data de consolidação declarada: 2026-09-22);
> - arquivos ZIP de snapshots antigos preservados em `~/sus_explorer_mvp/` (`sus_explorer_mvp.zip`, `sus_explorer_mvp_terminology.zip`, `sus_explorer_mvp_ms_go.zip`);
> - `~/.zsh_history` (timestamps em formato epoch, usados apenas como fonte de comandos, URLs públicas oficiais, tentativas e resultados observáveis).
>
> Regras aplicadas na redação:
>
> 1. Fatos têm uma evidência recuperável e são citados com arquivo/commit.
> 2. Quando a evidência permite inferir uma motivação com segurança razoável, isso é marcado explicitamente como **inferência**.
> 3. Onde a evidência é insuficiente, o texto diz que a evidência disponível não permite determinar a causa.
> 4. Nenhuma data, número, erro ou justificativa foi inventado. Onde o histórico do shell registra apenas o comando e não a saída, isso é dito.
> 5. Nenhuma credencial, chave, token ou segredo é reproduzido. Credenciais são mencionadas apenas de forma genérica.
>
> **Intervalo coberto:** 2026-09-19 (primeiros comandos recuperáveis) a 2026-09-26 (último commit).

---

## 2026-09-19 e 2026-09-20 — Primeiros experimentos com microdados do SI-PNI

### Contexto

O projeto ainda não tinha estrutura de código no repositório atual. O histórico do shell mostra trabalho em `/home/gumentz/sus_explorer_mvp_ms_go/` (diretório que hoje não existe mais) e, a partir de 2026-09-22, em `/home/gumentz/sus_explorer_mvp/sus_explorer_versao_atualizada/sus_explorer_mvp_terminology/`.

Em 2026-09-19 23:37 aparece a execução de `python3 teste.py`, seguida de `pip install duckdb` (23:48), criação de um virtualenv (23:49) e nova execução do script.

### Problema e tentativas

Ainda em 2026-09-19/20 o foco era o **formato e o volume do arquivo oficial**. A sequência registrada:

- `file vacinacao_mai_2026.zip`, `head -c 200`, `du -h` (00:00 de 2026-09-20);
- `curl -sI "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_mai_2026_csv.zip" | grep -iE "content-length|content-range|accept-ranges"` (00:01) — cabeçalhos HTTP do recurso público oficial;
- `curl -C - -o vacinacao_mai_2026.zip <mesma URL>` (00:02) — download com **retomada por HTTP Range**, indicando que um download anterior havia sido interrompido;
- `unzip -l` (00:10) para inspecionar o conteúdo do ZIP;
- `time unzip -p vacinacao_mai_2026.zip vacinacao_mai_2026.csv > /dev/null` (2026-09-20 17:42) — medir o tempo de descompressão pura, sem escrita;
- `duckdb --version` e `pip install duckdb` (17:46–17:47).

### A tentativa com DuckDB e o limite de memória

O comando de 2026-09-20 17:47 é a evidência mais direta do primeiro enfoque de processamento:

```bash
time unzip -p vacinacao_mai_2026.zip vacinacao_mai_2026.csv | \
duckdb -c "
SET memory_limit='3GB';
SET temp_directory='/tmp/duckdb_temp';
COPY (
    SELECT *
    FROM read_csv('/dev/stdin', header=true, auto_detect=true, sample_size=100000)
)
TO 'pni_maio_2026_zstd.parquet'(
    FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000
);
"
```

Três decisões estão explícitas nesse comando: `memory_limit='3GB'` (limitação deliberada de memória), `temp_directory` (spill em disco) e leitura de `/dev/stdin` (streaming do CSV a partir do ZIP, sem materializar o CSV em disco).

Logo em seguida aparecem `htop` (17:49, 17:55) e `watch -n 2 'free -h; echo; ls -lh pni_maio_2026_zstd.parquet'` (17:50) — **monitoramento explícito de consumo de memória durante a conversão**, o que indica que a execução estava sendo observada de perto por causa do gargalo de memória conhecido.

**O que a evidência não registra:** a saída do `time`, o consumo real de memória e o tamanho final de `pni_maio_2026_zstd.parquet` não foram guardados em nenhum artefato do projeto. A evidência disponível **não permite determinar com segurança** se essa execução falhou por limite de memória, quanto consumiu, ou se apenas levou muito tempo.

**O que a evidência registra:** depois dessa experiência com DuckDB, nenhuma linha de código do projeto usa `duckdb`, e o `duckdb` não consta em nenhum virtualenv do projeto. A ausência é um fato; a causa é inferência.

### Encoding

Às 18:22–18:23 de 2026-09-20 o histórico registra duas sondagens de encoding sobre o CSV em streaming:

```bash
unzip -p vacinacao_mai_2026.zip vacinacao_mai_2026.csv | head -c 100000 | file -
unzip -p ... | head -c 1000000 | iconv -f ISO-8859-1 -t UTF-8 > /dev/null; echo $?
```

Mais tarde, em 2026-09-22 00:43, um script em Python testou explicitamente `utf-8`, `cp1252` e `latin-1` nas duas primeiras linhas do CSV oficial de outubro/2023. O documento de proveniência (`SUS_EXPLORER_PROVENIENCIA_E_CACHE.md`, seção 12) registra o resultado: **UTF-8 falha com `UnicodeDecodeError`; `cp1252` é o encoding correto**, e o separador é `;`. O encoding `cp1252` está consolidado em `recover_pni_2023_10.py`, em `sus_explorer/audit_ms_2023_10.py` e em `sus_explorer/cli/audit_ms.py` (`CSV_ENCODING = "cp1252"`).

### Resultado e consequência arquitetural

**Fato:** o pipeline que sobreviveu no projeto **não usa DuckDB**. Ele usa PyArrow + pandas em chunks sobre datasets Parquet remotos (`sus_explorer/build_cache.py`) e streaming de CSV do ZIP com `pandas.read_csv(..., chunksize=250_000)` (`recover_pni_2023_10.py`, `sus_explorer/audit_ms_2023_10.py`, `sus_explorer/cli/audit_ms.py`).

**Inferência sustentada:** a experiência de 2026-09-20 com limite de memória de 3 GiB e `temp_directory` parece ter motivado a adoção de uma estratégia de **streaming por chunks** como padrão permanente do projeto, já visível em todos os leitores de CSV posteriores. Nenhuma fonte registra essa decisão de forma explícita.

---

## 2026-09-20 (20:57) a 2026-09-21 (00:28) — Três snapshots do MVP

### Contexto

Antes de qualquer commit, o projeto foi preservado como três arquivos ZIP em `~/sus_explorer_mvp/`. Eles são o **artefato mais antigo recuperável do código do SUS Explorer**.

As datas na coluna abaixo são os *mtime* dos arquivos ZIP no disco. As datas internas das entradas do arquivo diferem em cerca de três horas (23:55, 00:19 e 00:28), o que sugere que os ZIPs foram gerados com carimbo de tempo em UTC. A diferença não altera a ordem dos três snapshots.

### Os três estados preservados

| Arquivo | mtime | Conteúdo |
|---|---|---|
| `sus_explorer_mvp.zip` | 2026-09-20 20:57 | 12 arquivos, 16.373 bytes descomprimidos: `.env.example`, `requirements.txt`, `smoke_test.py`, `README.md` (1.550 B), `app.py`, `demo.py`, `sus_explorer/{schemas,config,__init__,pni,llm,service}.py` |
| `sus_explorer_mvp_terminology.zip` | 2026-09-20 21:20 | 14 arquivos, 20.202 bytes: acrescenta `refresh_terminology.py` (185 B) e `sus_explorer/terminology.py` (2.470 B) |
| `sus_explorer_mvp_ms_go.zip` | 2026-09-20 21:29 | 14 arquivos, 27.818 bytes: `refresh_terminology.py` (576 B), `terminology.py` (8.042 B), `README.md` (2.498 B) — este é o ancestral direto do `README.md` atual |

### Decisões já presentes no primeiro snapshot

O `README.md` do snapshot mais antigo (idêntico ao do snapshot `ms_go` na parte do MVP) documenta, em 2026-09-20, decisões que permanecem válidas:

- o LLM é usado **apenas para planejar consultas e explicar resultados agregados**; **microdados individuais não são enviados ao LLM**;
- fluxo: `Pergunta → Gemini (plano JSON) → Pydantic → PyArrow/R2 → agregado + proveniência → Gemini → resposta`;
- **o LLM não escreve SQL e não acessa o bucket diretamente**: produz apenas um `QueryPlan` validado;
- **a partição `uf=` é a UF do estabelecimento**, não a UF de residência do paciente;
- o MVP não calcula cobertura vacinal (entraria depois com denominadores IBGE);
- operações do MVP: `count`, `group`, `timeseries`, `latency`.

O isolamento de responsabilidades "LLM planeja / PyArrow executa" está implementado em `sus_explorer/schemas.py` (`QueryPlan` com `status: ready | needs_clarification` e `@model_validator` que exige `clarification_question` quando falta informação) e em `sus_explorer/llm.py` (prompts `PLANNER` e `ANSWER` separados).

### Verificação funcional inicial

O histórico de 2026-09-20 registra a validação do MVP ponta a ponta:

- `python smoke_test.py` (21:06) — contagem de uma partição remota sem LLM;
- `python demo.py "Quantas doses foram aplicadas em Porto Alegre em maio de 2026?"` (21:08);
- `python demo.py "Quais foram os 10 imunobiológicos com mais doses registradas no RS em maio de 2026?"` (21:13);
- `streamlit run app.py` (21:44).

**A evidência não registra a saída** desses comandos. Ela registra que foram executados nessa ordem, como parte da validação do fluxo.

---

## 2026-09-20/21 — Merge de terminologia MS × SES-GO

### Contexto

Entre os três snapshots há um salto de escopo: `terminology.py` cresce de 2.470 bytes (não existe no primeiro snapshot) para 8.042 bytes, e o `README.md` ganha uma seção "Merge de terminologia MS + SES-GO".

### Decisão

`sus_explorer/terminology.py` implementa um merge com **proveniência explícita por campo**:

- **Ministério da Saúde / BRImunobiologico** é a autoridade para `code` e `official_display`;
- **SES-GO / BRImunobiologico** fornece `definition`;
- a definição da SES-GO só é incorporada se o `display` do mesmo código for compatível com o display canônico do MS; em divergência, a linha passa a ter `{"definition": null, "terminology_conflict": true}`;
- o LLM é instruído a nunca completar a descrição por memória própria (prompt `ANSWER` em `sus_explorer/llm.py`).

Fontes usadas pelo código: `https://terminologia.saude.gov.br/fhir/ValueSet-BRImunobiologico.json`, `https://terminologia.saude.gov.br/fhir/CodeSystem/BRImunobiologico` e `https://fhir.saude.go.gov.br/r4/reds-go/CodeSystem-BRImunobiologico.json`. Cache local em `~/.cache/sus_explorer/BRImunobiologico_ms_go.json`, com TTL de 7 dias.

### Verificação

- 2026-09-20 21:24: `python refresh_terminology.py`;
- 2026-09-20 21:42: script Python lendo `~/.cache/sus_explorer/BRImunobiologico_ms_go.json` e listando **conceitos em conflito** (`x["conflict"]`, `x["conflict_detail"]`);
- 2026-09-20 21:44: `streamlit run app.py`.

**Não há registro da quantidade de conflitos** encontrada. A evidência disponível não permite determinar esse número.

---

## 2026-09-20/21 — Ambiente, dependências e o começo do pipeline SI-PNI

### O problema do ambiente

Entre 2026-09-20 18:26 e 2026-09-21 00:08, o histórico registra **repetidas recriações de virtualenv** (`python3 -m venv .venv`, `source .venv/bin/activate`) alternadas com `pip install -r requirements.txt`. Só no dia 20/09 a partir de 21:02 há quatro recriações de `.venv` em sequência.

Um problema específico é identificável: em 2026-09-20 23:52, `python -m pip install python-dotenv` seguido de `python -c "from dotenv import load_dotenv; print('dotenv OK')"`, imediatamente antes de `python -m sus_explorer.build_cache --year 2025 --uf RS`. Ou seja, **`python-dotenv` era uma dependência necessária e ausente** no ambiente, o que explicava falhas de importação de `sus_explorer.config` (`load_dotenv()` no topo do módulo). Hoje `python-dotenv>=1.0` está em `requirements.txt`.

### Nascimento do builder

- 2026-09-20 23:43–23:52: várias tentativas de executar o builder, inicialmente como script (`python build_cache.py`), depois como módulo (`python -m sus_explorer.build_cache`), com diagnóstico de qual interpretador estava em uso (`which python`, `which python3`, `python -c "import sus_explorer; print(sus_explorer.__file__)"`).
- 2026-09-21 00:07–00:13: aparece um módulo `sus_explorer.build_cache_brazil` sendo invocado com `--start-year/--end-year`; em seguida, `sus_explorer.build_cache` passa a ser invocado com as mesmas opções.
- O `mtime` do diretório `cache/pni_cube/ano=2020` é **2026-09-21 00:38**, indicando que a primeira partição do cubo foi materializada nessa janela.
- `cache/pni_cube/manifest.json` declara `created_at = 2026-09-21T03:09:09.206609+00:00` (UTC), equivalente a 2026-09-21 00:09 no fuso local (-03:00) usado nos commits.

**Inferência sustentada:** a existência de `build_cache_brazil` seguida logo depois pelo uso de `build_cache` com os mesmos argumentos sugere uma consolidação do builder nacional em um único módulo. Nenhuma fonte registra a motivação, nem existe `build_cache_brazil` no repositório atual.

### Estrutura do cubo

O formato do cubo está documentado em `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` (seção 5) e implementado em `sus_explorer/build_cache.py`:

- chaves de partição: `ano=YYYY/uf=XX/mes=MM/cube.parquet` (a ordem de diretórios é ano → UF → mês; a chave textual do manifest é `YYYY/UF/MM`, gerada por `partition_key()` em `sus_explorer/transform/pni.py`);
- colunas: `year, month, uf, municipality_code, municipality_name, vaccine_code, sex, age_band, dose, doses`;
- compressão ZSTD (nível 6, dicionário e estatísticas habilitados em `build_cache.py`);
- faixas etárias: `00-04 … 80+, IGNORADA`.

**Invariante declarada no código** (`build_cache.py`, comentário "Invariante fundamental"):

```python
if cube_doses != raw_rows:
    raise RuntimeError(...)
```

isto é, `SUM(cube.doses)` deve ser exatamente igual ao número de linhas brutas lidas da partição. A mesma invariante é verificada **depois da gravação**, lendo o arquivo temporário antes do `os.replace` atômico.

---

## 2026-09-21/22 — Diagnóstico dos `missing` e recuperação por retry

### Problema

Após a primeira execução nacional, o manifest continha partições ausentes. O histórico de 2026-09-21 23:57 a 2026-09-21 23:59 registra três scripts Python sucessivos de análise do `manifest.json`, cada vez mais estruturados: o primeiro tolera diferenças de formato do manifest, o segundo inspeciona a estrutura da raiz, o terceiro produz a matriz **ano × UF** dos `missing`, com lista exata por partição e seção separada para `failed`.

### Resultado registrado na documentação de proveniência

`../sus_explorer_provenance.json` e `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` (seções 7 e 8) registram o estado do cache **antes** da recuperação de outubro/2023:

- `cached_partitions`: **2.133**
- `represented_doses_records`: **1.231.680.542**
- `cube_rows`: **81.778.600**
- `size_mib`: **146,44**
- `failed`: **0**
- `missing`: **135** — sendo 27 partições de 2023/10 (todas as UFs) e 108 partições de 2026/09 a 2026/12.

Grade analisada: 2020–2026 × 27 UFs × 12 meses = **2.268** combinações.

### Retry

Em 2026-09-22 00:03 aparece:

```bash
python -m sus_explorer.build_cache --start-year 2022 --end-year 2022 --retry-failed --retries 5
```

A documentação de proveniência lista as partições recuperadas por esse retry: **2022/RN/09, 2022/RN/10, 2022/RN/11 e 2022/SP/07**.

**Observação relevante:** o estado atual do `manifest.json` registra `failed: 0` e partições com status `missing` em 2026/09–2026/12, e o comando de retry é uma funcionalidade permanente de `build_cache.py` (`--retry-failed`, espera exponencial com `min(2**(attempt-1), 30)` segundos). A evidência disponível **não permite determinar** se o retry de 2022 foi decorrente de erro de rede ou de outro tipo de falha: o manifest não guarda partições hoje classificadas como `failed`, e o `error_type`/`error` só é persistido no momento da falha.

### Verificação da ausência contra o espelho

`SUS_EXPLORER_PROVENIENCIA_E_CACHE.md`, seção 9, registra que a listagem de `healthbr-data/sipni/microdados/ano=2023/` no R2 encontrou apenas `01,02,03,04,05,06,07,08,09,11,12` — `mes=10` **não existe no bucket de redistribuição**. Combinando com a seção 10 (o Portal de Dados Abertos do SUS contém explicitamente "Vacinação - Outubro 2023"), a conclusão registrada é:

```text
MS/OpenDataSUS → outubro/2023 existe
healthbr-data  → outubro/2023 ausente
SUS Explorer   → missing corretamente
```

Este é o fato que justifica toda a etapa de recuperação seguinte.

---

## 2026-09-22 (00:06–01:13) — Recuperação de outubro/2023 a partir da fonte oficial

### Por que outubro/2023

**Fato:** outubro/2023 era o **único buraco histórico nacional** do cache, as 27 partições de 2023/10, e o período **não existia** no bucket de redistribuição `healthbr-data`, embora existisse na fonte oficial do Ministério da Saúde.

**A evidência disponível não registra** uma justificativa adicional para a escolha desse período específico (por exemplo, uma prioridade de produto). A escolha é sustentada pelo diagnóstico de `missing` documentado acima.

### A busca pela URL oficial

Sequência registrada no histórico de shell, na noite de 2026-09-22:

1. **00:06** — tentativa de consultar um manifesto espelho: `https://data.sidneybissoli.com/sipni/microdados/manifest.json`, procurando por `"2023/10"`, `"ano=2023/mes=10"`, `"2023-10"`. O script seguinte (00:07) imprime status HTTP, content-type, URL final e os primeiros 500 caracteres da resposta. **Nenhuma das duas saídas foi preservada**, portanto não é possível afirmar o resultado.
2. **00:08** — `grep -nE "S3FileSystem|healthbr-data|base_dir|base_path|microdados|FileSystemDataset|dataset" sus_explorer/build_cache.py` seguido de `sed -n '80,105p;170,200p'`: leitura do código do builder para localizar como o bucket de origem é acessado.
3. **00:10** — script usando `pyarrow.fs.FileSelector` sobre `healthbr-data/sipni/microdados/ano=2023` listando os meses encontrados. É a evidência operacional da seção 9 da documentação de proveniência.
4. **00:12** — consulta à API CKAN do portal `https://dadosabertos.saude.gov.br/api/3/action/package_show?id=7ed6eecc-c254-475c-92c5-daba5727596b`, filtrando recursos cujo nome contenha "outubro" e "2023". O `package_id` observado foi depois registrado em `sus_explorer_provenance.json`.
5. **00:13** — scraping da página HTML do dataset `doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-2023` procurando todas as ocorrências de "Outubro".
6. **00:14** — download de `https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_out_2023_csv.zip` para `tmp/pni_2023_10/`, com barra de progresso por chunk de 1 MiB.

Esse URL é a **URL pública oficial** que permanece em uso por `recover_pni_2023_10.py` e `sus_explorer/audit_ms_2023_10.py` (via a constante `ZIP_PATH`).

### Download interrompido e retomada

Às 00:38 o histórico mostra `ls -lh tmp/pni_2023_10/vacinacao_out_2023_csv.zip` e, imediatamente depois, um script de **retomada por HTTP Range** com até 10 tentativas, `Range: bytes=<tamanho_atual>-`, exigindo **HTTP 206** para anexar ao arquivo parcial e recusando apagar/recomeçar se o servidor devolvesse 200. `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` (seção 11) confirma o incidente: **"O primeiro download caiu em 98,8% e foi retomado via HTTP Range."**

Tamanhos registrados em `sus_explorer_provenance.json`:
- ZIP: **1,719 GiB**
- CSV interno (`vacinacao_out_2023.csv`): **6,935 GiB**

E às 00:39, o script `ZipFile.testzip()` verifica a integridade do arquivo após a retomada.

### Semântica da partição por UF — teste empírico

Às 00:45, um script abre via PyArrow o dataset remoto `healthbr-data/sipni/microdados/ano=2023/mes=09/uf=RS` e coleta os valores distintos de `sg_uf_paciente` e `sg_uf_estabelecimento`. O resultado está registrado em `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` (seção 4):

- `sg_uf_paciente` continha as 27 UFs;
- `sg_uf_estabelecimento` continha apenas `RS`.

Daí a conclusão: **`uf=XX` representa a UF do estabelecimento**, não a UF de residência do paciente. Esse achado é a razão de a recuperação de outubro/2023 agregar por `sg_uf_estabelecimento`.

### O script de recuperação

Às 00:46–00:47 o arquivo `recover_pni_2023_10.py` é escrito com `nano` e executado. Suas características:

- lê **apenas 7 colunas** do CSV oficial (`sg_uf_estabelecimento`, `co_municipio_estabelecimento`, `no_municipio_estabelecimento`, `co_vacina`, `tp_sexo_paciente`, `nu_idade_paciente`, `ds_tipo_dose`), com `sep=";"`, `encoding="cp1252"`, `chunksize=250_000`;
- descarta linhas cuja UF não esteja na lista das 27 UFs, contabilizando-as separadamente;
- agrega por `uf` + as 6 chaves do cubo usando `.groupby(...).size()` — **mesma semântica de contagem de registros** do builder, sem introduzir filtros clínicos;
- grava os 27 `cube.parquet` com escrita atômica (`.parquet.tmp` + `os.replace`), **validando a soma de doses antes do replace**;
- **só salva o manifest depois que todas as 27 partições foram produzidas e validadas**;
- registra proveniência explícita no manifest: `source: "opendatasus_csv_recovery"`, `source_resource_id`, `source_file`, `source_encoding: "cp1252"`, `source_partition_column: "sg_uf_estabelecimento"`.

### Os 22 registros não particionáveis

Às 00:58, dois scripts percorrem o CSV oficial procurando linhas cuja UF não pertence às 27 UFs. O resultado não foi impresso no histórico, mas **sobreviveu no manifest e na auditoria**: as 27 partições de 2023/10 somam `doses = 12.454.230` e `rows_cube = 1.238.805`, e a auditoria registra `raw_rows = 12.454.252` e `unpartitionable_rows = 22`. A diferença é exatamente **12.454.252 − 12.454.230 = 22**.

Esses 22 registros estão preservados em `audit/ms_crosscheck/2023_10_unpartitionable.jsonl` (22 linhas), todas com `sg_uf_estabelecimento: "nan"` e `co_municipio_estabelecimento: "nan"`.

---

## 2026-09-22 (01:17–01:53) — Versionamento em Git

### O que aconteceu

O histórico de shell mostra uma primeira tentativa de versionamento **no diretório antigo** (`/home/gumentz/sus_explorer_mvp_ms_go/`), com `git add .`, `git commit -m "checkpoint: cache nacional e recovery 2023-10 funcionando"` e `git tag pre-architecture-refactor` (01:17 a 01:20), seguida por `rm -rf /home/gumentz/.git` (01:35 e 01:43) e por várias investigações de uso de disco (`du -x -h --max-depth=2 /`, `df -h /`, `sudo lsof +L1`).

No novo diretório `sus_explorer_versao_atualizada/sus_explorer_mvp_terminology`:

- **01:51** — escrita de um `.gitignore` completo (secrets, Python, venvs, dados brutos, `/cache/`, `/data/cache/`, `/data/quarantine/`, `/audit/differences/`, `*.parquet`);
- **01:52** — `git init`; `git check-ignore -v .env` confirmando que `.env` está ignorado;
- **01:53** — verificação de arquivos acima de 10 MiB, `git add .` e o commit inicial **`8282675` — "checkpoint: working SUS Explorer before architecture refactor"** (18 arquivos, 3.555 linhas adicionadas).

**Fato:** a tag `pre-architecture-refactor` mencionada no histórico **não existe neste repositório** (`git tag -l` retorna vazio). A evidência disponível **não permite determinar** se a tag foi criada no repositório antigo e perdida com a remoção do `.git`, ou se o commit correspondente simplesmente não foi replicado. Este é um ponto de perda de proveniência registrado aqui de propósito.

### Decisão: dados grandes fora do Git

O `.gitignore` exclui explicitamente `/cache/`, `*.parquet`, `/tmp/`, `/data/raw/`, `*.zip` e `/audit/differences/`, mas **permite** `audit/ms_crosscheck/*.json` e `*.jsonl`. Ou seja: artefatos grandes ficam fora do versionamento; **summaries pequenos de auditoria são versionados**. Essa escolha é confirmada por um episódio concreto de 2026-09-25 (§ "Publicação da auditoria" abaixo), em que o `git check-ignore` foi usado para decidir o que versionar.

---

## 2026-09-22 (02:11–02:26) — Refatoração arquitetural conservadora

### Objetivo declarado

`docs/architecture.md` (commit `0665012`) documenta três diretrizes que resumem a intenção da fase:

1. **Invariância de dados**: nenhum arquivo do cache `cache/pni_cube` é reescrito durante as refatorações.
2. **Backward compatibility**: imports históricos de `sus_explorer.build_cache` continuam funcionando através de re-exportações delegadas (`make_s3 = make_filesystem`, `source_path = partition_path`).
3. **Independência da auditoria**: `sus_explorer/audit_ms_2023_10.py` e `recover_pni_2023_10.py` mantêm capacidade de auditoria determinística independente da produção.

Os docstrings dos módulos criados repetem a fórmula: *"Extraído de build_cache.py **sem alteração de comportamento**"* (`sus_explorer/data/remote/r2.py`, `sus_explorer/data/cache/manifest.py`) e *"Regras extraídas de build_cache.py **SEM nenhuma alteração de comportamento**"* (`sus_explorer/transform/pni.py`).

### As seis etapas, em ordem

| # | Commit | Horário | Conteúdo |
|---|---|---|---|
| 1 | `86df584` | 02:11 | `test: add regression coverage for PNI transformations and manifest` — cria `tests/conftest.py`, `tests/unit/test_transform.py` (17 testes) e `tests/unit/test_manifest.py` (9 testes) |
| 2 | `e949664` | 02:15 | `refactor: extract canonical PNI transformations to sus_explorer/transform/pni.py` — extrai `UFS`, `CUBE_ALIASES`, `resolve_col`, `normalize_string`, `age_band_series`, `partition_key`, `parse_ufs` (−90 linhas em `build_cache.py`) |
| 3 | `75cddc8` | 02:17 | `refactor: isolate R2 data access to sus_explorer/data/remote/r2.py` — extrai `make_filesystem`, `partition_path`, `open_partition` |
| 4 | `57ff066` | 02:21 | `refactor: centralize cache manifest handling to sus_explorer/data/cache/manifest.py` — extrai `utc_now`, `load_manifest`, `save_manifest` (escrita atômica com `os.replace`), `validate_existing_cache`, `cache_file`; ajusta `.gitignore` |
| 5 | `fcea75d` | 02:24 | `refactor: centralize application paths to sus_explorer/paths.py` — `PROJECT_ROOT`, `CACHE_ROOT`, `RAW_ROOT`, `QUARANTINE_ROOT`, `AUDIT_ROOT`, `AUDIT_REPORTS`, `AUDIT_DIFFERENCES`, `AUDIT_PROVENANCE`; cria `tests/unit/test_paths.py` (3 testes) |
| 6 | `0665012` | 02:26 | `docs: add architecture documentation and refactor findings` — `docs/architecture.md`, `docs/refactor_findings.md`, `sus_explorer/domain/provenance.py` (`SourceFingerprint`, `AuditResult`) e `tests/unit/test_provenance.py` (2 testes) |

**Ordem deliberadamente registrada:** a etapa 1 cria os testes de regressão **antes** de qualquer extração. Isso é verificável pelos timestamps (02:11 antes de 02:15) e é a evidência disponível para a escolha de "testar antes de mexer". Nenhuma fonte escreve a motivação em prosa.

A intenção está escrita no próprio arquivo de testes criado na etapa 1 (`tests/unit/test_transform.py`):

> *Estes testes congelam o comportamento ATUAL das funções de `normalize_string`, `age_band_series` e `partition_key`.*
> *NÃO corrija o comportamento aqui. Se algum teste falhar após uma refatoração, é sinal de regressão — não de teste errado.*

Os testes importavam de `sus_explorer.build_cache` (a porta de entrada da refatoração); após a etapa 2 passaram a importar de `sus_explorer.transform.pni`, e `test_transform.py` foi de 17 para **20** testes.

O histórico de shell mostra `mkdir -p ...` e `nano sus_explorer/transform/pni.py` às 01:55 e `find sus_explorer -maxdepth 3 -type d | sort` às 01:55, confirmando a criação dos pacotes.

### Débitos registrados na própria refatoração

`docs/refactor_findings.md` documenta quatro achados. Os três primeiros são sobre `build_cache.py`; o quarto é sobre o código de produção:

1. **Divergência de aliases** (`POSSIBLE_BUG`) — `build_cache.py`/`transform/pni.py` define 6 aliases canônicos para o cubo; `pni.py` mantém **12** aliases para consultas remotas diretas, incluindo colunas de detalhamento (`vaccine_text`, `facility`, `system_origin`, `race`, `vaccination_date`, `rnds_entry_date`). Verificado no código: `CUBE_ALIASES` tem 6 chaves e `pni.py:ALIASES` tem 12.
2. **Duplicação de `partition_key`** — existia em `build_cache.py` e `recover_pni_2023_10.py`; foi centralizada em `transform/pni.py`.
3. **Duplicação proposital de transformações na auditoria** (`ARCHITECTURE_DEBT`) — `sus_explorer/audit_ms_2023_10.py` reimplementa `norm()` e `age_band()` localmente. Justificativa registrada **no próprio código**:
   ```python
   # Implementação propositalmente independente do build_cache.py.
   ```
   e, em `docs/refactor_findings.md`: *"O auditor não deve confiar nas funções de produção que está auditando."*
4. **Instanciação duplicada do S3FileSystem** (`ARCHITECTURE_DEBT`) — `build_cache.py` passou a usar `data/remote/r2.make_filesystem()`, enquanto `pni.py` continua instanciando o próprio filesystem. Justificativa registrada: *"`pni.py` é o mecanismo de consulta ativo em produção. Preservá-lo integralmente diminui drasticamente o risco da refatoração nesta primeira fase."*

**Contradição encontrada entre documentação e código (registrada, não corrigida):** o achado 4 fala em `s3fs.S3FileSystem`, mas o código real em `sus_explorer/pni.py:114` usa `pyarrow.fs.S3FileSystem` (`fs.S3FileSystem`). A conclusão do achado (duplicação de instanciação) permanece correta; apenas o nome da biblioteca citado no documento não corresponde ao código.

---

## 2026-09-24/25 — Primeira auditoria independente MS × cubo local

### Contexto

Entre 2026-09-22 02:27 e 2026-09-24 23:51 há um intervalo de **três dias sem comandos registrados** no histórico. Nada sobre auditoria é registrado nesse período.

### Execução

- 2026-09-24 23:51 — retorno ao diretório do projeto, `git status --short`, `git log --oneline -8`;
- 23:55–23:57 — conferência do ZIP e leitura estrutural de `audit_ms_2023_10.py` (`grep -nE '^(def |class |if __name__)|ZIP|cache|manifest|parquet|difference|report|sha256|csv|chunksize'`, `sed -n '261,520p'`);
- 2026-09-25 00:00 e 00:03 — execuções de `python3 audit_ms_2023_10.py`;
- 2026-09-25 01:03 e 11:51 — `sha256sum tmp/pni_2023_10/vacinacao_out_2023_csv.zip`;
- 2026-09-25 11:52 — o valor é impresso no histórico:
  `133756671d73b14ce913f431cbc9e17915a00c99d885685eb611d048c323ca40`.

Esse hash é **idêntico** ao gravado em `audit/ms_crosscheck/2023_10_summary.json` e ao registrado na documentação de proveniência. É a identificação criptográfica do artefato oficial validado.

### O que a primeira versão da auditoria fazia

`sus_explorer/audit_ms_2023_10.py` (453 linhas, commit `8282675`):

1. calcula o **SHA-256 do ZIP**;
2. **reimplementa** `norm()` e `age_band()` localmente (independência de propósito, comentada no código);
3. lê o CSV oficial em chunks de 250.000 linhas e agrega pelas 7 chaves (`uf` + 6 dimensões), separando `partitionable_rows` e `unpartitionable_rows`;
4. carrega os **27 cubos locais** em `cache/pni_cube/ano=2023/uf=*/mes=10/cube.parquet`, reagrupando defensivamente para eliminar duplicação acidental;
5. faz um **`merge` outer pelas 7 chaves com `indicator=True`** e calcula `delta = cube_doses − ms_doses`, `missing_from_cube`, `extra_in_cube`, `changed_keys`, `absolute_dose_delta` e `net_dose_delta`;
6. define `EXACT_MATCH` somente quando não há chave faltando, chave extra, chave alterada **e** os totais de doses são iguais;
7. grava `audit/ms_crosscheck/2023_10_differences.parquet` **somente se** houver diferenças, e apaga o arquivo anterior se não houver;
8. **não apaga o ZIP automaticamente**, com a instrução impressa: *"Apague somente depois de conferir status=EXACT_MATCH e o summary."*

**Sobre a natureza da comparação:** o comentário no código é explícito — `# Outer join — comparação célula por célula`. A auditoria compara o valor de `doses` de **cada chave individual**, não apenas totais agregados. Isso é verificável no código e está refletido nas métricas `changed_keys` e `absolute_dose_delta` do summary.

### Resultado — versão 1 (commit `d37a486`, 2026-09-25 22:35)

`audit_version: 1`, `status: EXACT_MATCH`, `elapsed_seconds: 135.616`, `local_cube` com `cube_rows: 1.238.805` e `doses: 12.454.230`, todas as métricas de comparação em zero.

---

## 2026-09-25 (12:11–12:24) — O projeto passa a ser preservado remotamente

O histórico registra `git remote -v` (12:11, sem remoto), a adição do remoto `git@github.com:<owner>/sus-explorer.git` (12:15) e uma primeira tentativa de `git push` (12:15) que não deu certo — a sequência de comandos imediatamente posterior (`ssh-add -l`, criação de chave, edição de `~/.ssh/config`, `ssh -T git@github.com`) indica que a autenticação ainda não estava configurada — seguida de:

- `ls -lah ~/.ssh`, `ssh-add -l` (12:18);
- criação de um par de chaves SSH dedicado (12:19), `eval "$(ssh-agent -s)"` (12:20), leitura da chave pública (12:20);
- edição de `~/.ssh/config` (12:22) e `chmod 700 ~/.ssh` (12:23);
- `ssh -T git@github.com` (12:24) e novo `git push -u origin master` (12:24), bem-sucedido.

**Fato:** até 2026-09-25 12:15 não existia remoto; o histórico Git local passa a ter `origin/master` a partir daí. Nenhuma informação sensível de autenticação é reproduzida aqui.

**Consequência:** a partir desse momento, todo o trabalho posterior (auditoria, workflows, refatoração do auditor) tem histórico recuperável de forma remota — algo que não existia para os dias 19 a 22 de setembro.

---

## 2026-09-25 (12:40–22:25) — Cloudflare R2 `sus-dados`: configuração, upload e verificação

### Distinção essencial entre os dois buckets

Esta distinção é sustentada pelo código e pela configuração:

| | `healthbr-data` | `sus-dados` |
|---|---|---|
| Papel | **fonte** de microdados em Parquet, mantida por terceiro | **destino** do cubo derivado, mantido pelo projeto |
| Configuração | `R2_ENDPOINT`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET` (default `healthbr-data`), `R2_PREFIX` (default `sipni/microdados`) | `SUS_DATA_R2_ENDPOINT`, `SUS_DATA_R2_ACCESS_KEY_ID`, `SUS_DATA_R2_SECRET_ACCESS_KEY`, `SUS_DATA_R2_BUCKET` (default `sus-dados`), `SUS_DATA_R2_CUBE_PREFIX` (default `cache/pni_cube`) |
| Quem lê | `sus_explorer/data/remote/r2.py` (builder) e `sus_explorer/pni.py` (consultas remotas) | **apenas** `sus_explorer/cli/audit_ms.py` (auditoria) |
| Mantenedor | `SidneyBissoli/healthbr-data` (registrado em `sus_explorer_provenance.json`) | projeto SUS Explorer |

`sus_explorer/cli/audit_ms.py` reforça a separação no código: *"Usa exclusivamente `SUS_DATA_R2_*` — **sem fallback para healthbr-data**"*, e `make_audit_filesystem()` levanta `RuntimeError` se qualquer uma das três variáveis estiver ausente. As credenciais são Read Only: a auditoria apenas executa `s3.open_input_file()` e leitura de Parquet; nenhuma escrita no R2 é feita pelo auditor.

### Sequência de diagnóstico registrada

- **12:40–12:41** — instalação do rclone via `apt` e `rclone config`;
- **12:48** — `rclone lsd sus-r2:` (listagem de buckets);
- **12:49** — primeiro teste de escrita de um arquivo de texto em `sus-r2:sus-dados/test/`;
- **20:46–20:49** — `rclone ls sus-r2:sus-dados/test/`, `rclone config file`, edição de `~/.config/rclone/rclone.conf`, novo teste de upload com `-vv`, e tentativa de `sudo rclone selfupdate`;
- **22:03** — backup da configuração, `sudo apt remove rclone` e reinstalação pelo script oficial (`curl https://rclone.org/install.sh | sudo bash`), seguida de `rclone version` e `rclone listremotes` (22:07–22:08);
- **22:08** — teste de escrita **"R2 funcionando de verdade"**, com `rclone ls` e `rclone cat` confirmando leitura de volta (22:08);
- **22:11–22:14** — três rodadas de diagnóstico com `-vv` (`rclone cat`, `rclone lsf`, `rclone config redacted`) intercaladas com nova edição manual do `rclone.conf`;
- **22:15** — teste final "R2 agora vai", confirmado por `rclone ls` e `rclone cat`.

**O que a evidência permite e o que não permite:** o histórico registra a **sequência de tentativas** (instalação via pacote de sistema → teste falho → tentativa de `selfupdate` → remoção e reinstalação pelo instalador oficial → ainda com diagnóstico verboso → correção manual do arquivo de configuração → sucesso confirmado por leitura de volta). Ele **não** registra o texto de nenhum erro. Portanto:

- **Fato:** a versão do rclone instalada por `apt` foi removida e substituída pelo instalador oficial, e o `rclone.conf` foi editado manualmente pelo menos duas vezes antes de o acesso passar.
- **Não verificável:** a ocorrência específica de erro HTTP **501**, e a existência de um "endpoint configurado incorretamente" na configuração original. Nenhuma fonte preservada (histórico, artefato, commit) contém essa mensagem de erro. Qualquer afirmação sobre a causa raiz seria invenção.

**Inferência razoavelmente sustentada:** a sequência (debug verboso → troca de versão do cliente → nova edição do endpoint → sucesso) é compatível com um problema de cliente e/ou de endpoint que impedia o acesso. O sucesso é atestado por leitura de volta (`rclone cat`) e por todas as operações seguintes.

### Upload, `rclone size`, `rclone check` e restore

- **22:16** — `du -sh cache/pni_cube` seguido de `rclone copy cache/pni_cube sus-r2:sus-dados/cache/pni_cube --progress --transfers 8 --checkers 16`;
- **22:22** — `rclone size cache/pni_cube` e `rclone size sus-r2:sus-dados/cache/pni_cube`, seguido de `rclone check cache/pni_cube sus-r2:sus-dados/cache/pni_cube --one-way`;
- **22:23** — **restore de uma partição**: `rclone copy sus-r2:sus-dados/cache/pni_cube/ano=2023/uf=RS/mes=10 /tmp/sus-restore-test` seguido de `ls -lh`.

O `--one-way` no `rclone check` significa que apenas a direção local → remoto é comparada. O restore de uma partição é uma verificação de leitura real do objeto recém-gravado.

### Estado do prefixo no R2

O `rclone size` foi executado novamente em 2026-09-26 00:54, também para o bucket inteiro (`rclone size sus-r2:sus-dados`). **A saída não foi preservada em nenhum artefato do repositório.** Os valores abaixo são verificáveis localmente e foram conferidos contra as contagens do manifest:

| Medida | Valor | Como verificar |
|---|---|---|
| Objetos em `cache/pni_cube` | **2.161** | `find cache/pni_cube -type f \| wc -l` → 2.161 (2.160 `cube.parquet` + 1 `manifest.json`) |
| Bytes em `cache/pni_cube` | **156.520.408** | `du -sb cache/pni_cube` |

Como `rclone copy` foi uma cópia direta, arquivo a arquivo, e o `rclone check --one-way` foi executado em seguida, é sustentado registrar que o prefixo `sus-dados/cache/pni_cube` é uma cópia idêntica do cache local.

**Cuidado com a leitura:** o número **156.520.408 bytes** é o tamanho **do prefixo auditado** (`cache/pni_cube`), **não** o tamanho do bucket `sus-dados` inteiro. Durante o diagnóstico foram criados econfirmados por leitura de volta arquivos de teste em `sus-dados/test/` (`r2-v3.txt` e `r2-v4.txt`; antes deles houve duas tentativas com nomes `sus-test.txt` e `sus-test-2.txt`, cuja presença não foi confirmada). O bucket completo tem, portanto, mais objetos e mais bytes que o prefixo do cubo.

**Conferência aritmética adicional:** a soma de `bytes` das partições no manifest (155.832.282) mais o tamanho do próprio `manifest.json` (688.126) resulta exatamente em 156.520.408. Isso confirma internamente a contagem de 2.161 objetos.

### Publicação da auditoria — decisão sobre o que versionar

Entre 22:25 e 22:35 o histórico registra uma sequência de verificação de ignore rules:

- `find` por arquivos `*audit*`, `*summary*.json`, `*provenance*`, `*fingerprint*` (22:25);
- `git check-ignore -v audit/summaries/2023_10_summary.json` (22:28) — caminho **errado**; o arquivo real está em `audit/ms_crosscheck/`;
- `cd` para o diretório do arquivo, nova tentativa, `pwd`, `git rev-parse --show-toplevel` (22:30);
- `git check-ignore -v ./audit/ms_crosscheck/2023_10_summary.json` (22:31) — agora correto;
- `git add ./audit/ms_crosscheck/2023_10_summary.json`, `git diff --cached --stat`, `git diff --cached` (22:32);
- commit **`d37a486` — "audit: record exact MS validation for PNI 2023-10"** e `git push` (22:35).

**Decisão documentada pela prática:** o summary pequeno de auditoria (32 linhas de JSON) é versionado; o Parquet de diferenças e o cache não são.

---

## 2026-09-25 (22:49–23:32) — GitHub Actions × R2

### O workflow

O commit **`bf9f5ef` — "ci: add read-only R2 cache verification"** (22:53) adiciona `.github/workflows/verify-r2.yml`, disparado apenas por `workflow_dispatch` (nenhum trigger automático), com `permissions: contents: read`, instalação do rclone pelo instalador oficial, configuração de um remote `sus-r2` do tipo `provider = Cloudflare` com `no_check_bucket = true`, e três verificações: `rclone lsf` do prefixo, `rclone size` do prefixo e `rclone ls` de uma partição conhecida (`ano=2023/uf=RS/mes=10`).

### A primeira falha e o passo de diagnóstico

O commit **`a6e3791` — "ci: diagnose R2 configuration"** (23:14) acrescenta um passo que imprime `R2_ENDPOINT` e `R2_BUCKET` (ou `<EMPTY>`) e apenas **SET/EMPTY** para as duas chaves de acesso, seguido de quatro `test -n ... || exit 1`. Ou seja: o workflow passou a **falhar explicitamente** quando a configuração não chega ao runner, em vez de falhar mais tarde com um erro do rclone.

O histórico de shell mostra, nesse intervalo, `git add`/`git commit` repetidos (23:14 e 23:22) e consultas `gh secret list` / `gh variable list` (23:22–23:25).

**Fato:** o commit **`3294948` — "ci: isolate Actions configuration test"** (23:27) cria um segundo workflow, `.github/workflows/test-config.yml`, que **não faz nenhuma verificação de R2** — apenas ecoa `github.repository`, `github.ref`, `github.event_name` e o estado `SET/EMPTY` das quatro configurações. Isso isola o problema de "a configuração chega ao runner?" do problema de "o rclone consegue falar com o R2?".

Em seguida, 2026-09-25 23:30–23:32, o histórico registra a configuração no repositório remoto:

- `gh variable set R2_BUCKET` e `gh variable set R2_ENDPOINT` com os valores do bucket `sus-dados` e do endpoint correspondente;
- `gh secret set R2_ACCESS_KEY_ID` e `gh secret set R2_SECRET_ACCESS_KEY` (os valores foram digitados interativamente e **não são reproduzidos aqui**);
- `gh secret list` e `gh variable list` para confirmação.

**Sequência sustentada pelas evidências:** o workflow foi escrito com as quatro configurações esperadas; o workflow falhou; foi adicionado um passo de diagnóstico; a causa foi isolada num workflow separado; e só então as configurações foram efetivamente cadastradas no repositório. **A evidência disponível não permite determinar com segurança qual era a causa exata** — se as variáveis não existiam, se estavam com escopo errado, ou outra. Nenhuma saída de execução de workflow foi preservada no repositório.

---

## 2026-09-25 (23:43) e 2026-09-26 (00:51) — Remoção do ZIP oficial

Após a confirmação de `EXACT_MATCH`, o ZIP de 1,719 GiB é removido (`rm -v tmp/pni_2023_10/vacinacao_out_2023_csv.zip` e `rmdir tmp/pni_2023_10`), com `df -h /` e `du -sh tmp cache/pni_cube` em seguida. Em 2026-09-26 00:51 a mesma remoção é tentada novamente (o diretório `tmp/` já havia sido removido) — sem efeito.

Isso é coerente com a regra que os dois scripts de auditoria imprimem: o ZIP não é apagado automaticamente pelo código, e a remoção é uma decisão humana posterior à confirmação.

---

## 2026-09-26 (00:05–00:49) — Auditoria generalize MS × R2

### Generalização

O commit **`5c88b9e` — "refactor: generalize independent MS audit"** (00:05) cria `sus_explorer/cli/audit_ms.py` (657 linhas) e acrescenta ao `Settings` os quatro campos `sus_data_r2_*` em `sus_explorer/config.py`.

O que mudou em relação a `sus_explorer/audit_ms_2023_10.py`:

| Aspecto | `audit_ms_2023_10.py` (especializado) | `cli/audit_ms.py` (generalizado) |
|---|---|---|
| Período | hardcoded `YEAR = 2023`, `MONTH = 10` | CLI `--year` (obrigatório) e `--month` (obrigatório) |
| Alvo do cubo | 27 arquivos **locais** em `cache/pni_cube/` | leitura **direta do R2** (`sus-dados/cache/pni_cube`), via `S3FileSystem` |
| ZIP | caminho hardcoded `tmp/pni_2023_10/vacinacao_out_2023_csv.zip` | `--zip-path`, ou descoberta automática em `tmp/pni_<ano>_<mes>/` |
| Proveniência | `resource_id` constante no código | `--resource-id` (se omitido, `warnings.warn` e o summary registra `null`) |
| **Gate de integridade** | apenas **registra** o SHA-256 | `--expected-sha256`: se o valor divergir, imprime aviso e **`raise SystemExit(1)` antes de processar qualquer linha**; se não for fornecido, emite warning explícito |
| Não particionáveis | apenas contados | persistidos em JSONL (`2023_10_unpartitionable.jsonl`) com campos mínimos |
| `audit_version` | 1 | 2 |
| Nome das métricas | `missing_from_cube` / `extra_in_cube` | `missing_from_bucket` / `extra_in_bucket` |
| Bloco `target` | ausente | `{"type": "cloudflare_r2", "bucket": ..., "prefix": ...}` |

A regra de independência está escrita no docstring do módulo:

> *Este módulo NÃO importa lógica de transformação de `sus_explorer.transform.pni`. As funções `norm()` e `age_band()` são implementadas localmente para evitar common-mode failure: um bug no pipeline não pode ser reproduzido automaticamente pelo auditor.*

O módulo também declara o que **pode** reutilizar: `sus_explorer.config.settings` (credenciais, sem vazar valores) e `sus_explorer.paths` (caminhos de saída). A lista de 27 UFs e as chaves do cubo também são **copiadas localmente** no auditor.

### Testes sintéticos

O commit **`4685837` — "test: add MS to R2 audit regression coverage"** (00:05:51) adiciona `tests/unit/test_audit_ms.py` com **11 testes**, todos sobre dados sintéticos (sem acesso a rede): `test_exact_match`, `test_exact_match_status_string`, `test_missing_from_bucket`, `test_extra_in_bucket`, `test_changed_key_doses`, `test_net_delta_zero_but_differences_exist` (dois deltas opostos: `net=0` mas `changed_keys=2` → MISMATCH), `test_invalid_uf_is_unpartitionable`, `test_regroup_defensivo_elimina_duplicatas`, `test_mismatch_status_string`, `test_norm_independent`, `test_age_band_independent`.

Esse último par é o que **torna a independência do auditor testável**: ele fixa o comportamento esperado das funções locais, de modo que uma alteração acidental no auditor é detectada.

**Total da suíte unitária:** 45 funções `test_` em 5 arquivos (`test_transform.py` 20, `test_audit_ms.py` 11, `test_manifest.py` 9, `test_paths.py` 3, `test_provenance.py` 2), organizadas em classes por unidade. O cache de pytest em `.pytest_cache/v/cache/nodeids` registra **64 node IDs** coletados.

### Resultado final — versão 2 (commit `65c06fe`, 2026-09-26 00:49)

`audit/ms_crosscheck/2023_10_summary.json` (artefato versionado, confirmado no repositório):

```json
{
  "audit_version": 2,
  "period": "2023-10",
  "official_source": {
    "provider": "Ministério da Saúde / OpenDataSUS",
    "resource_id": "bb1c023c-e524-48ff-8471-f68f6cdf189e",
    "filename": "vacinacao_out_2023_csv.zip",
    "sha256": "133756671d73b14ce913f431cbc9e17915a00c99d885685eb611d048c323ca40",
    "encoding": "cp1252"
  },
  "target": { "type": "cloudflare_r2", "bucket": "sus-dados", "prefix": "cache/pni_cube" },
  "ms": {
    "raw_rows": 12454252,
    "partitionable_rows": 12454230,
    "unpartitionable_rows": 22,
    "cube_keys": 1238805,
    "partitionable_doses": 12454230
  },
  "r2_cube": { "cube_rows": 1238805, "doses": 12454230 },
  "comparison": {
    "missing_from_bucket": 0, "extra_in_bucket": 0, "changed_keys": 0,
    "different_keys": 0, "absolute_dose_delta": 0, "net_dose_delta": 0
  },
  "status": "EXACT_MATCH",
  "elapsed_seconds": 173.891
}
```

Todos os valores esperados foram **confirmados no artefato versionado**, e não copiados de outra fonte. Observe-se que `elapsed_seconds` subiu de **135,616 s** (auditoria v1, contra o cache local) para **173,891 s** (auditoria v2, contra o R2) — o custo de ler o cubo pela rede em vez do disco local.

### Sobre a natureza da comparação

Confirmado no código: a auditoria faz `ms_df.merge(cube_df, on=KEYS, how="outer", indicator=True)` sobre as **7 chaves** (`uf`, `municipality_code`, `municipality_name`, `vaccine_code`, `sex`, `age_band`, `dose`) e calcula `delta` **por chave**. `EXACT_MATCH` exige simultaneamente: zero chave só na fonte, zero chave só no bucket, zero chave com `delta != 0`, **e** igualdade dos totais de doses. Portanto a igualdade observada é célula a célula, não apenas de totais.

Consequência registrada no próprio código: em caso de `MISMATCH`, o auditor imprime, em texto, a instrução de não adaptar a transformação para "fazer bater" a comparação — ou seja, **divergência deve produzir falha explícita, não correção automática**.

### Os 22 registros não particionáveis

O commit `65c06fe` adiciona `audit/ms_crosscheck/2023_10_unpartitionable.jsonl` com **22 linhas**, todas com `sg_uf_estabelecimento: "nan"` e `co_municipio_estabelecimento: "nan"`. Isso explica aritmeticamente por que `raw_rows` (12.454.252) é 22 maior que `partitionable_rows` / `partitionable_doses` (12.454.230): são registros sem UF de estabelecimento válida, portanto não atribuíveis a nenhuma partição.

---

# Decisões e invariantes acumulados

Cada item abaixo é sustentado por código, artefato ou documentação citados.

1. **Microdados individuais não são enviados ao LLM.** O LLM recebe apenas plano, agregados e métricas. — `README.md`, `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` §17, `sus_explorer/llm.py`.
2. **O LLM planeja e narra; não escreve SQL e não acessa o bucket.** Ele produz apenas um `QueryPlan` validado por Pydantic. — `README.md`, `sus_explorer/schemas.py`, `sus_explorer/llm.py`.
3. **O planejador nunca inventa período, UF, município ou código.** Se falta informação, o plano é `needs_clarification` com `missing` e `clarification_question`, e o modelo validador exige a pergunta. — `sus_explorer/schemas.py` (`@model_validator`), prompt `PLANNER`.
4. **Grandes datasets são processados incrementalmente.** Leitura do CSV oficial em `chunksize=250_000`; leitura do Parquet remoto via `pyarrow.dataset` com `scanner(batch_size=100_000)`; escrita do manifest a cada partição. — `recover_pni_2023_10.py`, `sus_explorer/audit_ms_2023_10.py`, `sus_explorer/cli/audit_ms.py`, `sus_explorer/build_cache.py`.
5. **Invariante do cubo: `SUM(cube.doses) == raw_rows` da partição**, verificada **antes** da gravação e **depois** da gravação no arquivo temporário, com escrita atômica (`os.replace`). Divergência aborta e apaga o temporário. — `sus_explorer/build_cache.py`, `recover_pni_2023_10.py`.
6. **O manifest é o registro operacional do cache** e permite retomada: partições já existentes são revalidadas e marcadas `cached`; `missing` e `failed` são status de primeira classe; `--retry-failed` re-tenta apenas o que falhou. — `sus_explorer/build_cache.py`, `sus_explorer/data/cache/manifest.py`.
7. **A transformação auditada não pode ser reutilizada pelo auditor.** `norm()` e `age_band()` são reimplementadas localmente no auditor, com o motivo escrito no código ("auditoria cega e isenta de common-mode failure"). — `sus_explorer/audit_ms_2023_10.py`, `sus_explorer/cli/audit_ms.py`, `docs/refactor_findings.md` §3.
8. **A auditoria lê o alvo por uma via independente** — rede, bucket próprio (`sus-dados`), credenciais próprias (`SUS_DATA_R2_*`), sem fallback para o bucket de origem. — `sus_explorer/cli/audit_ms.py`, `sus_explorer/config.py`.
9. **Credenciais do R2 de auditoria são Read Only.** O auditor apenas lê; nenhuma escrita é realizada sobre o bucket. — `sus_explorer/cli/audit_ms.py`.
10. **SHA-256 identifica exatamente o artefato oficial validado**, e o auditor **aborta antes de processar** se o hash observado divergir do esperado. Sem `--expected-sha256`, o auditor emite warning explícito. — `sus_explorer/cli/audit_ms.py`, `audit/ms_crosscheck/2023_10_summary.json`.
11. **A comparação é por chave, não por total.** Outer join pelas 7 chaves, `delta` por chave, e `EXACT_MATCH` exige ausência de chave faltando, chave extra, chave alterada **e** igualdade de totais. — `sus_explorer/cli/audit_ms.py`.
12. **Divergência deve produzir falha explícita, nunca correção automática.** O auditor imprime "Não adaptar transformação para 'fazer bater'". — `sus_explorer/cli/audit_ms.py`.
13. **O ZIP oficial nunca é apagado automaticamente** pelo código de auditoria; a remoção é decisão humana posterior à confirmação do `EXACT_MATCH`. — ambos os auditadores.
14. **A partição `uf=` é a UF do estabelecimento**, não a do paciente — verificado empiricamente no microdado remoto. — `README.md`, `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` §4.
15. **`missing` não é igual a zero.** Meses correntes e futuros são corretamente marcados `missing` e não devem ser tratados como buraco histórico. — `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` §8, §19.6.
16. **Registros não equivalem necessariamente a pessoas únicas.** A medida do cubo é `doses`/registros. — `README.md`, §19.7, prompt `ANSWER`.
17. **O MS é canônico para `code` e `official_display`; a SES-GO só contribui com `definition` e apenas se compatível.** Conflito gera `terminology_conflict: true` com `definition: null`, e o LLM é proibido de completar descrições por memória. — `sus_explorer/terminology.py`, `README.md`.
18. **O cubo derivado é preservado separado da fonte**, em bucket e prefixo próprios, para permitir auditoria independente. — `sus_explorer/config.py`, `sus_explorer/cli/audit_ms.py`.
19. **Dados grandes não pertencem ao Git** (`/cache/`, `*.parquet`, `*.zip`, `/data/raw/`, `/audit/differences/`), **mas summaries pequenos de auditoria são versionados**. — `.gitignore`, commit `d37a486`.
20. **Refatoração sem alteração de comportamento**, precedida por testes de regressão e com backward compatibility por re-exportação. — `docs/architecture.md`, commits `86df584` → `e949664` → `75cddc8` → `57ff066` → `fcea75d` → `0665012`.
21. **A procedência da fonte é registrada junto de cada partição** (`source`, `source_resource_id`, `source_file`, `source_encoding`, `source_partition_column`). — `recover_pni_2023_10.py`, `cache/pni_cube/manifest.json` (as 27 partições de 2023/10 carregam `source: "opendatasus_csv_recovery"`).

---

# Estado ao final de 2026-09-26

## O que existe

**Código** — em `/home/gumentz/sus_explorer_mvp/sus_explorer_versao_atualizada/sus_explorer_mvp_terminology`, remoto `origin/master`, 14 commits de `8282675` a `65c06fe`:

- aplicação: `app.py` (Streamlit), `demo.py` (CLI), `smoke_test.py`, `refresh_terminology.py`;
- `sus_explorer/`: `build_cache.py` (builder nacional), `pni.py` (consulta remota, 940 linhas), `service.py`, `llm.py`, `schemas.py`, `terminology.py`, `benchmark_cache.py`, `audit_ms_2023_10.py` (auditor v1, preservado), `paths.py`, `config.py`;
- pacotes extraídos na refatoração: `transform/pni.py`, `data/remote/r2.py`, `data/cache/manifest.py`, `domain/provenance.py`, `cli/audit_ms.py`;
- recuperação: `recover_pni_2023_10.py` (386 linhas);
- testes: 45 funções em `tests/unit/` (5 arquivos);
- workflows: `.github/workflows/verify-r2.yml`, `.github/workflows/test-config.yml`;
- documentação: `README.md`, `docs/architecture.md`, `docs/refactor_findings.md` (versionadas) e `../SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` + `../sus_explorer_provenance.json` (não versionadas, no diretório pai).

**Cubo** — `cache/pni_cube/`, **163 MiB**, **156.520.408 bytes**, **2.161 arquivos** (2.160 `cube.parquet` + `manifest.json`).

**Estado do `manifest.json`** (verificado por leitura direta):

| Métrica | Valor |
|---|---|
| Partições registradas | 2.268 (2020–2026 × 27 UFs × 12 meses) |
| `built` | 1.129 |
| `cached` | 1.031 |
| `missing` | 108 (todas 2026/09 a 2026/12, 27 UFs cada) |
| `failed` | 0 |
| `rows_cube` total | 83.017.405 |
| `doses` total | 1.244.134.772 |
| Bytes dos Parquets | 155.832.282 |
| `created_at` | 2026-09-21T03:09:09Z |
| `updated_at` | 2026-09-22T03:50:11Z |
| `schema_version` | 1 |

Distribuição por ano (partições concluídas / doses / bytes):

| Ano | Partições | Doses | Bytes |
|---|---|---|---|
| 2020 | 324 | 102.423.524 | 19.885.830 |
| 2021 | 324 | 415.451.924 | 26.838.366 |
| 2022 | 324 | 206.648.099 | 25.178.991 |
| 2023 | 324 | 127.916.136 | 21.884.907 |
| 2024 | 324 | 103.709.388 | 20.532.469 |
| 2025 | 324 | 167.611.516 | 25.049.598 |
| 2026 | 216 | 120.374.185 | 16.462.121 |

Doses por partição construídas (2023/10, recuperadas da fonte oficial): **12.454.230 doses**, **1.238.805 linhas de cubo**, **2.275.004 bytes (2,17 MiB)**.

**Conferência de consistência:** os números registrados na documentação de proveniência antes da recuperação (`2.133` partições, `1.231.680.542` doses, `81.778.600` linhas) + as 27 partições recuperadas de 2023/10 (`12.454.230` doses, `1.238.805` linhas) resultam **exatamente** nos totais atuais do manifest (`2.160` partições concluídas, `1.244.134.772` doses, `83.017.405` linhas). A continuidade numérica é verificável.

## O que foi validado

- **Outubro/2023, célula por célula, contra a fonte oficial do Ministério da Saúde**, lendo o cubo **direto do Cloudflare R2** (`sus-dados/cache/pni_cube`), com SHA-256 do ZIP oficial conferido, resultado `EXACT_MATCH`, zero divergência em 1.238.805 chaves. Artefato versionado: `audit/ms_crosscheck/2023_10_summary.json` (commit `65c06fe`).
- **Os 22 registros não particionáveis** estão isolados e versionados em `audit/ms_crosscheck/2023_10_unpartitionable.jsonl`.
- **A suíte unitária** cobre transformações, manifest, paths, proveniência e o auditor. Nenhuma execução de teste foi feita durante a reconstrução deste diário (nenhum código foi alterado).
- **O cubo no R2** foi conferido com `rclone check --one-way` e um restore de partição real (`ano=2023/uf=RS/mes=10`).

## Onde está cada coisa

- **Código:** repositório local acima, espelhado em `origin/master`.
- **Fonte de microdados:** bucket `healthbr-data`, prefixo `sipni/microdados` (projeto `healthbr-data`, mantido por terceiro).
- **Cubo derivado:** local em `cache/pni_cube/` e no bucket `sus-dados`, prefixo `cache/pni_cube`.
- **Auditoria:** `audit/ms_crosscheck/` (summary + JSONL versionados; o Parquet de diferenças não existe, pois não houve diferenças).

## Garantias obtidas

1. Identificação criptográfica do artefato oficial auditado (SHA-256).
2. Gate que aborta a auditoria antes do processamento se o hash divergir.
3. Independência de implementação entre construtor e auditor.
4. Leitura do alvo por rede, bucket e credenciais próprios, sem fallback.
5. Comparação por chave com outer join, não apenas por total.
6. `EXACT_MATCH` como condição conjunta (sem chave faltando, sem chave extra, sem chave alterada, totais iguais).
7. Proveniência por partição no manifest (`resource_id`, arquivo, encoding, coluna de particionamento).
8. Invariante `SUM(doses) == raw_rows` verificada antes e depois da gravação, com escrita atômica.
9. Ausências registradas explicitamente como `missing`, sem confusão entre lacuna histórica e mês futuro.
10. Falha explícita em vez de correção automática em caso de divergência.

## O que ainda não foi feito (verificável)

- **Nenhuma auditoria independente para nenhum período além de outubro/2023.** As outras **2.133** partições do cubo nunca foram comparadas com a fonte oficial.
- **O `pni.py` não consulta o cache local.** Uma busca por `cache`/`CACHE_ROOT`/`pni_cube` em `sus_explorer/pni.py` retorna **zero** ocorrências: a rota "cache-first" sugerida em `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` §21 (item 6) não foi integrada. O cubo é construído e versionado, mas o caminho de consulta de produção continua lendo microdados remotos.
- **A verificação do R2 pelo GitHub Actions não tem evidência de execução bem-sucedida** preservada no repositório (workflows são `workflow_dispatch`, sem histórico de runs versionado).
- **A cobertura vacinal não existe** (declarado no `README.md`).
- **Granularidades ausentes do cubo:** CNES, raça/cor, lote, latência RNDS, fabricante, via, estratégia — acessíveis apenas via microdado remoto (`pni.py` tem aliases para vários deles).
- **Períodos de 2026/09 a 2026/12 seguem `missing`** porque ainda não havia microdado publicado na fonte.

---

# Débitos técnicos conhecidos

Todos os itens abaixo são sustentados por inspeção do repositório em 2026-09-26. **Nenhum foi corrigido.**

1. **A URL oficial não é persistida na proveniência.** `audit/ms_crosscheck/2023_10_summary.json` grava `resource_id`, `filename`, `sha256` e `encoding`, mas **não** a URL. `recover_pni_2023_10.py` grava `source_resource_id` e `source_file`, também sem URL. A classe `SourceFingerprint` em `sus_explorer/domain/provenance.py` **tem** o campo `url: str | None`, mas nenhum código o preenche. A relação `resource_id` ↔ URL existe apenas em código (`RESOURCE_ID` em `sus_explorer/audit_ms_2023_10.py`, `recover_pni_2023_10.py`) e em `../sus_explorer_provenance.json`, que **não é versionado**. Consequência: o repositório, sozinho, não permite resolver o `resource_id` para a URL oficial.

2. **`"nan"` em vez de `null` no JSONL de não particionáveis.** `audit/ms_crosscheck/2023_10_unpartitionable.jsonl` grava `str(row.get("sg_uf_estabelecimento", ""))` sobre valores `NaN` do pandas, produzindo a string `"nan"` nas 22 linhas. Isso é semanticamente diferente de `null` e torna o arquivo ambíguo para consumo por máquina.

3. **Ausência de configuração do `pytest`.** Não existem `pytest.ini`, `pyproject.toml`, `setup.cfg` nem `tox.ini`. Consequência observada: `.pytest_cache/v/cache/lastfailed` registra `{"smoke_test.py": true}` — ou seja, o `pytest` coleta `smoke_test.py` (que não contém testes) como item falho, e o cache de `nodeids` tem **64** entradas, acima dos 45 testes realmente existentes em `tests/unit/`. Não há `testpaths` restringindo a coleta a `tests/`.

4. **Arquivos untracked necessários para o pacote funcionar.** `git status` reporta como não rastreados: `sus_explorer/audit/`, `sus_explorer/query/`, `sus_explorer/data/cache/__init__.py` e `sus_explorer/domain/__init__.py`. Porém `sus_explorer/build_cache.py` importa `from .data.cache.manifest import ...`, e `tests/unit/test_provenance.py` importa `sus_explorer.domain.provenance`. Um clone limpo do repositório **não** contém os `__init__.py` necessários. `sus_explorer/audit/` e `sus_explorer/query/` estão vazios e não são referenciados por nenhum código.

5. **Divergência de aliases entre transformação e consulta** (`POSSIBLE_BUG` em `docs/refactor_findings.md` §1). `transform/pni.py:CUBE_ALIASES` tem 6 chaves; `pni.py:ALIASES` tem 12. Alterar um alias em um módulo não afeta o outro.

6. **Instanciação duplicada de `S3FileSystem`** (`ARCHITECTURE_DEBT`, `docs/refactor_findings.md` §4). `build_cache.py` usa `data.remote.r2.make_filesystem()`; `pni.py:114` ainda instancia o seu próprio `fs.S3FileSystem`. Observação adicional: o texto do achado cita `s3fs.S3FileSystem`, enquanto o código usa `pyarrow.fs.S3FileSystem` — **divergência entre documentação e código**.

7. **Credenciais de auditoria ausentes do `.env` do projeto.** `sus_explorer/config.py` define `sus_data_r2_*` a partir de `SUS_DATA_R2_*`, mas o `.env` presente no diretório contém apenas chaves `GEMINI_*` e `R2_*`. As credenciais usadas pela auditoria vieram de outra fonte (variáveis de ambiente da sessão), o que significa que o procedimento de auditoria **não é reproduzível a partir do `.env` versionável** — e o `.env` não é versionado, por decisão do `.gitignore`.

8. **`.env.example` ausente.** O `README.md` instrui `cp .env.example .env`, e o `.gitignore` tem a exceção `!.env.example`, mas **não existe** `.env.example` no repositório (ele existia nos snapshots ZIP de 2026-09-20/21). Uma instalação seguindo o README falha nesse passo.

9. **Tag `pre-architecture-refactor` perdida.** O histórico registra a criação dessa tag em 2026-09-22 01:17–01:20, em um repositório que foi descartado. `git tag -l` no repositório atual retorna vazio. O marco equivalente é o commit `8282675`, mas a tag nominal não sobreviveu.

10. **Documentação de proveniência não versionada.** `SUS_EXPLORER_PROVENIENCIA_E_CACHE.md` e `sus_explorer_provenance.json` estão no diretório **pai** do repositório Git. Contêm informação essencial (package_id do CKAN, URL oficial, tamanhos observados, diagnóstico dos `missing`) que não é preservada pelo versionamento.

11. **`benchmark_cache.py` não é referenciado por nenhum comando, workflow ou documentação.** Existe no código (107 linhas) e no Git desde `8282675`, mas não há registro de execução nem de resultado.

12. **Intervalo sem histórico entre 2026-09-22 02:27 e 2026-09-24 23:51** (três dias). Nenhuma evidência recuperável cobre o que ocorreu nesse período; a auditoria v1 só tem registro de execução a partir de 2026-09-25 00:00.

13. **Dependências do ambiente não são declaradas de forma exata.** `requirements.txt` usa apenas limites inferiores (`pyarrow>=18.0`, `pandas>=2.2`, etc.), não versões fixadas; não há lockfile. O virtualenv do projeto tem, por exemplo, `pandas 3.0.6` e `pyarrow 25.0.1` — versões muito posteriores às mínimas declaradas. `duckdb` e `s3fs` não estão em `requirements.txt` nem instalados no virtualenv do projeto (apesar de `s3fs` ser citado em `docs/refactor_findings.md` §4).

---

# Documentação contemporânea — evolução até 2026-10-07

## Método e limites desta atualização

Esta seção registra somente desenvolvimento verificável no Git e no GitHub e contratos observáveis nos arquivos atuais. A reconstrução anterior foi versionada no commit [`96190e5`](https://github.com/GustavoDMentz/sus-explorer/commit/96190e562549fcab8bbeada105949c847a04c45d), em 2026-09-26. Não há aqui reconstrução de conversas, intenções privadas ou atividade de máquina não preservada.

Os resultados de testes locais citados nos PRs são identificados como **relatos dos PRs**; os resultados do GitHub Actions foram conferidos diretamente nos logs. CI com dados sintéticos e banco descartável não equivale a nova auditoria dos microdados oficiais, nem comprova implantação em produção. Nenhum novo total nacional do cubo é inferido.

## 2026-10-01 — Logging operacional estruturado

O commit [`548dedc`](https://github.com/GustavoDMentz/sus-explorer/commit/548dedc12a91be5fb8838062aa36a8dd12b135e3), registrado em 2026-10-02 01:31 UTC (**2026-10-01 22:31 local**), acrescentou `sus_explorer/operational_logging.py` e integrou `JsonlRunLogger` ao builder e à CLI de auditoria.

O contrato passa a registrar JSONL append-only por execução em `logs/<run_id>.jsonl`, com `schema_version`, timestamp UTC, nível, componente, evento, `run_id` estável e PID. Eventos cobrem início/fim, partições, retries, identificação/hash da fonte, comparação e falhas. `/logs/` é ignorado pelo Git e permanece separado dos artefatos científicos.

Há redação recursiva de campos sensíveis, valores secretos conhecidos e material de autenticação em URLs. Falhas de logging são capturadas e sinalizadas por `logging_failed`, sem substituir o resultado científico ou derrubar a operação apenas pela indisponibilidade do log. O hardening posterior ampliou a sanitização de texto para assignments de secrets, e-mails e CPF. Evidências: código atual de `sus_explorer/operational_logging.py`, diff do commit e `tests/unit/test_operational_logging.py`.

## 2026-10-01 — Publicação atômica e imutável das auditorias

O commit [`973cff8`](https://github.com/GustavoDMentz/sus-explorer/commit/973cff8cd86e4640d81bd890f9e95a1afc43f654), em 2026-10-02 02:16:37 UTC (**2026-10-01 23:16:37 local**), alterou a persistência da CLI generalizada, preservando os resultados históricos.

`publish_audit_run()` gera o conjunto completo em diretório temporário irmão, valida summary, JSONL e metadados Parquet e publica uma execução com um único `os.rename` para `<output-dir>/runs/<run_id>/`. O summary identifica o `run_id` e os nomes de seus artefatos. JSONL de não particionáveis e Parquet de diferenças só existem quando necessários.

Colisões de `run_id` são rejeitadas; uma execução publicada não é sobrescrita nem removida pela função. Falhas limpam apenas o temporário da própria execução, sem deixar um conjunto final parcial. A CLI oferece `--output-dir`; não aceita `--overwrite`. Essa imutabilidade é o contrato do publicador, não uma alegação de armazenamento WORM ou de proteção contra um administrador do filesystem.

Os testes em `tests/unit/test_audit_ms.py` exercitam publicação completa, colisão, ausência de diferenças e falhas na geração, validação e rename. A transformação independente, a leitura do R2 de auditoria, o gate SHA-256 e a comparação célula a célula permanecem no caminho científico. A mudança não registra uma nova execução sobre outubro/2023 nem sobre outro período.

## 2026-10-06/07 — PostgreSQL/pgvector complementar e PR #1

Os quatro commits de fundação têm timestamp 2026-10-07 02:52:37 UTC (**2026-10-06 23:52:37 local**):

| Commit | Desenvolvimento versionado |
|---|---|
| [`1377328`](https://github.com/GustavoDMentz/sus-explorer/commit/1377328e8ebbd23617f682a453c8fd7cecc12adb) | Persistência PostgreSQL operacional opcional |
| [`d6351a7`](https://github.com/GustavoDMentz/sus-explorer/commit/d6351a7e36949dc15edc0dbd66b4ce843d969adf) | Testes das invariantes de persistência |
| [`f0f3953`](https://github.com/GustavoDMentz/sus-explorer/commit/f0f3953718de30a9bbdba1ff91134f7dd96f47b2) | Documentação da arquitetura híbrida |
| [`99a571a`](https://github.com/GustavoDMentz/sus-explorer/commit/99a571a2024e17939c4ec384212d97a1cdde2c62) | CI com PostgreSQL e pgvector |

O [PR #1 — Add optional PostgreSQL persistence foundation](https://github.com/GustavoDMentz/sus-explorer/pull/1), da branch `integration/database-foundation-v2` para `master`, foi aberto em **2026-10-07 00:09:41 local** e integrado às **00:12:13**, pelo merge [`b728d71`](https://github.com/GustavoDMentz/sus-explorer/commit/b728d71a48e02ccad3da20423c8efeab6cedf9da).

### Decisão arquitetural e garantias implementadas

Parquet/R2 continua como caminho analítico de microdados e cubos para `count`, `group`, `timeseries` e `latency`. PostgreSQL é **opt-in e complementar**, destinado a estado operacional, proveniência das ingestões, documentos JSONB e projeções normalizadas. Não substitui Parquet/R2 nem é fallback silencioso. Imports e consultas analíticas não abrem conexão nem aplicam migrations.

A migration `001_foundation.sql` habilita pgvector como **fundação futura**. Não há embeddings, busca semântica ou RAG ativo introduzidos por essa integração. O contrato exige evolução posterior com fontes documentais, versionamento, avaliação e política de reindexação.

O código em `sus_explorer/data/persistence/` implementa:

- execuções de ingestão com origem, identidade, metadados, contagens e estados `RUNNING/SUCCESS/PARTIAL/FAILED`; execuções terminadas ficam congeladas;
- raw JSONB corrente, revisões anteriores e observações append-only, protegidas por triggers;
- vínculo entre execução, origem, registro, revisão e instante de coleta;
- invalidação automática da projeção anterior quando muda o raw e gravação de raw + nova projeção de imunização em uma transação;
- leitura normalizada condicionada à igualdade entre revisão projetada e revisão raw atual;
- conclusão da ingestão serializada com writers;
- migrations ordenadas, transacionais, sob advisory lock e com SHA-256; alteração de migration aplicada é erro;
- integração ao logger JSONL canônico por `operational_events.py`, com metadados técnicos e contagens, sem incluir payloads individuais.

Evidências: `repositories.py`, `migrate.py`, `migrations/001_foundation.sql`, `operational_events.py`, `docs/persistence.md`, `README.md` e `docs/architecture.md`.

### Validação da fundação

O corpo do PR #1 relata **91 testes locais aprovados e 4 testes PostgreSQL pulados**, por ausência de banco descartável local. Esse relato não foi tratado como execução integral do banco.

O [run 37565455392](https://github.com/GustavoDMentz/sus-explorer/actions/runs/37565455392), job `112612006677`, executou `python -m pytest tests -q` com PostgreSQL 17 + pgvector e registrou **95 passed in 1.10s**, sem skips no resumo. O workflow `.github/workflows/test-postgres.yml` fornece o serviço `pgvector/pgvector:0.8.6-pg17` e habilita `SUS_EXPLORER_TEST_DB=1`.

## 2026-10-07 — Hardening PostgreSQL e PR #2

O [PR #2 — security: harden PostgreSQL trust boundary](https://github.com/GustavoDMentz/sus-explorer/pull/2), da branch `security/postgres-hardening`, foi aberto às **00:39:47 local**. A sequência registrada:

| Horário local | Commit | Mudança |
|---|---|---|
| 00:36:13 | [`3ab7fb0`](https://github.com/GustavoDMentz/sus-explorer/commit/3ab7fb07a621ea79bbbf9f0e8ee8995495ea0e23) | Privilégio mínimo no PostgreSQL |
| 00:37:25 | [`9434f8e`](https://github.com/GustavoDMentz/sus-explorer/commit/9434f8ea17c22674f2638780b2dd6fda90b474d0) | Inputs e conexões defensivas |
| 00:38:05 | [`5739082`](https://github.com/GustavoDMentz/sus-explorer/commit/5739082f03f89e3ae88cee5d285c87845e1b82f9) | Testes das fronteiras de segurança |
| 00:39:19 | [`9473fa3`](https://github.com/GustavoDMentz/sus-explorer/commit/9473fa342a61f1798749704cca1cae9256b7bbba) | Supply chain do CI e modelo de ameaça |
| 00:45:12 | [`705910b`](https://github.com/GustavoDMentz/sus-explorer/commit/705910be365208b7e2ae2a866f6dcc5e23c94a3f) | Correção da colisão de nomes na migration |
| 00:47:35 | [`ecffdd5`](https://github.com/GustavoDMentz/sus-explorer/commit/ecffdd5f85968b6d4ec64b03c356e12f712eade7) | Correção dos testes para exercitar o banco real |

### Fronteira de confiança

A nova migration `002_security_hardening.sql` separa três roles estruturais `NOLOGIN`: `sus_explorer_migrator` (owner/migrations), `sus_explorer_runtime` (operações necessárias) e `sus_explorer_reader` (leitura). Runtime não possui objetos, não pode executar DDL, desabilitar triggers, assumir migrator ou escrever diretamente no histórico. Funções de proteção usam `SECURITY DEFINER`, owner migrator, `search_path` fixo e revogação de `EXECUTE` de `PUBLIC`.

Conexões ganham timeouts de conexão, statements, locks e transações ociosas, `application_name`, schema validado e `search_path` restrito com `pg_catalog`. TLS é configurável; `prefer` é o default local, enquanto a documentação exige `verify-full` com CA confiável para serviços remotos.

A validação limita identificadores, metadata (256 KiB), payload JSONB (4 MiB), profundidade (32) e nós JSON (100 mil). Constraints repetem limites essenciais no banco. `error_summary` é sanitizado, convertido para uma linha e limitado a 2.048 caracteres; secrets, credenciais, URLs assinadas, e-mails e CPF são removidos conforme as regras implementadas.

O workflow fixa Actions por SHA, usa `contents: read` e instala com `constraints.txt`. Dependabot foi configurado para propor atualizações semanais de Python e Actions. Isso não comprova ativação de branch protection, CodeQL ou secret scanning, nem implantação das roles em um banco de produção. `001_foundation.sql` permanece intacta; pgvector continua sem RAG ativo.

Evidências: migration 002, `database.py`, `validation.py`, `repositories.py`, `docs/persistence.md`, workflow, constraints e testes em `tests/integration/test_postgres_foundation.py` e `tests/unit/test_persistence_contract.py`.

### Falha do CI, correções e validação final

O corpo inicial do PR #2 relata **99 passed, 7 skipped** localmente, além de uma seleção de 46 testes aprovada. Os testes PostgreSQL pulados não validavam as novas roles. Os logs do banco real revelaram problemas adicionais:

| Evidência do CI | Resultado observado | Diagnóstico/correção verificável |
|---|---|---|
| [Run 37567789237](https://github.com/GustavoDMentz/sus-explorer/actions/runs/37567789237), job `112619376152`, head `9473fa3` | **4 failed, 99 passed, 3 errors** | `UnboundLocalError` em `migrate.py`: a variável local `sql` sombreava o módulo `psycopg.sql`. `705910b` renomeou o texto da migration para `migration_sql`. |
| [Run 37568229753](https://github.com/GustavoDMentz/sus-explorer/actions/runs/37568229753), job `112620752361`, head `705910b` | **1 failed, 102 passed, 3 errors** | A fixture usava parâmetro `%s` em `CREATE ROLE ... PASSWORD`, produzindo erro de sintaxe perto de `$1`; o teste de rollback usava UF `INVALID`, rejeitada por tamanho no Python antes de chegar ao banco. |
| [Run 37568411460](https://github.com/GustavoDMentz/sus-explorer/actions/runs/37568411460), job `112621323526`, head `ecffdd5` | **106 passed in 2.08s** | `ecffdd5` usou composição segura com `sql.Identifier`/`sql.Literal` na fixture e UF `rs`, de tamanho aceito pelo Python mas formato inválido no banco, exercitando o rollback PostgreSQL. |
| [Run 37569084257](https://github.com/GustavoDMentz/sus-explorer/actions/runs/37569084257), job `112623417083`, push em `master`/`fc446cb` | **106 passed in 1.97s** | Confirmação pós-merge na árvore integrada. |

**Validação final: `106 passed, 0 skipped`.** Os logs imprimem `106 passed`, sem categoria skipped; o workflow habilita os testes reais no serviço PostgreSQL 17 + pgvector. São 99 casos unitários e 7 de integração, incluindo negativas de privilégio, fluxo autorizado, histórico, conclusão de ingestão, constraints, checksum, concorrência e rollback. Erros de permissão emitidos pelo servidor durante os testes adversariais são rejeições esperadas; os jobs finais concluíram com sucesso.

O PR #2 foi integrado às **00:56:31 local**, após o CI aprovado, pelo merge [`fc446cb`](https://github.com/GustavoDMentz/sus-explorer/commit/fc446cb00eed33b580be9cd08bbb3b9091b7d4df). Os resultados locais com skips descritos no corpo original não representam o resultado final.

## Estado e invariantes preservados em 2026-10-07

A comparação Git [`96190e5...fc446cb`](https://github.com/GustavoDMentz/sus-explorer/compare/96190e562549fcab8bbeada105949c847a04c45d...fc446cb00eed33b580be9cd08bbb3b9091b7d4df) mostra as mudanças posteriores à reconstrução e permite verificar que os artefatos científicos históricos não foram alterados. Isso é preservação de conteúdo versionado, não uma nova checagem dos buckets ou do cache local.

- **Números determinísticos e privacidade:** LLM continua planejando `QueryPlan` validado e explicando agregados, sem SQL livre, acesso direto ao bucket ou envio de microdados individuais.
- **Backends complementares:** Parquet/R2 mantém a análise; PostgreSQL é operacional opt-in, sem fallback implícito; pgvector é fundação futura.
- **Integridade científica:** independência entre builder e auditor, gate SHA-256, comparação por chave e falha explícita permanecem. `audit/ms_crosscheck/2023_10_summary.json` e `2023_10_unpartitionable.jsonl` não mudaram. O `EXACT_MATCH` histórico não foi estendido a outros meses.
- **Atomicidade em duas fronteiras distintas:** auditoria publica um conjunto completo por rename e preserva runs anteriores; PostgreSQL grava raw/projeção em transação, protege histórico append-only e congela ingestões concluídas.
- **Observabilidade separada:** JSONL operacional, `run_id`, redação e tolerância a falhas de logging permanecem; logs não substituem summaries científicos.
- **Migrations imutáveis:** a migration 001 não foi reescrita pelo hardening; evolução é feita na 002, sob o controle transacional e de checksum.

O inventário antigo e seus débitos permanecem como fotografia de 26/09. Por exemplo, `.env.example` agora existe, e há constraints e CI PostgreSQL verificável. Essas evidências não autorizam declarar todos os débitos resolvidos. Nenhum cubo local foi lido nesta atualização, nenhuma nova auditoria oficial foi executada e não há comprovação aqui de RAG ou frontend novo implantado.

## Próximos requisitos — registrados em 2026-10-07, ainda não entregues

Os itens abaixo são **requisitos prospectivos solicitados para este diário**, não fatos históricos deduzidos de commits ou funcionalidades concluídas. O estado atual fornece a base técnica descrita; não há atribuição retroativa de datas de implementação.

1. **Analytics derivados:** definir métricas e agregações derivadas com execução determinística, fórmula, unidade, filtros, fonte, versão e limitações explícitas. Preservar a distinção entre doses/registros e pessoas, entre `missing` e zero e entre UF do estabelecimento e residência. Cobertura vacinal exige denominadores e compatibilidade de população/período; não deve ser inferida apenas de doses. Critério de entrega: resultados reproduzíveis e proveniência verificável, mantendo os contratos científicos e a separação dos backends.
2. **Novo frontend:** evoluir a interface atual de `app.py` (Streamlit) para apresentar consultas, pedidos de esclarecimento, resultados, visualizações e proveniência de forma organizada. Tecnologia, desenho e implantação ainda precisam ser definidos. Critério de entrega: manter validação do plano, números determinísticos e credenciais fora do frontend/LLM; comprovar que a mudança de interface preserva o comportamento analítico.
3. **Atividade pública anonimizada:** oferecer no site uma visão de atividade, como acesso e tipo de operação executada, por uma projeção pública específica de eventos. Não publicar JSONL bruto, payloads, credenciais, IPs, identificadores pessoais ou perguntas livres potencialmente identificáveis. Definir campos permitidos, anonimização, granularidade temporal, retenção e testes antes da exposição. Critério de entrega: somente eventos mínimos sanitizados, com verificação de ausência de informação identificável e sem confundir atividade operacional com evidência científica.

A redação do logger atual é uma defesa operacional; por si só, não comprova anonimização suficiente para publicação. Esses requisitos não ativam analytics novos, não substituem a interface e não tornam logs públicos nesta atualização documental.

## 2026-10-08 — Streamlit temporal, YoY e catálogo oficial de campanhas

Esta entrada registra as entregas nas branches dos [PRs #11–#17](https://github.com/GustavoDMentz/Sus-Explorer/pulls), **ainda não incorporadas ao master na revisão abaixo**. Não altera retroativamente a fotografia anterior nem transforma requisitos prospectivos em funcionalidades já integradas. A direção adotada é evoluir diretamente o Streamlit e o pipeline Python existentes; Next.js/FastAPI não são necessários ao fluxo principal. Atividade pública anonimizada e RAG continuam fora desta entrega.

### Funcionalidades e decisões implementadas nas branches

- **Planner e interface (#11/#12):** JSON Schema nativo, validação local e tratamento controlado do retorno Gemini; convenção explícita de intervalos de anos; filtro textual de imunobiológico com resolução pela terminologia e proveniência. O formulário Streamlit consulta SUSExplorer diretamente, mantém o resultado na sessão e oferece gráficos, indicadores, tabela exata recolhida, exportações e proveniência. Reruns de apresentação não repetem a consulta.
- **Percentuais mensais (#13):** `100 * (y(t)-y(t-1))/y(t-1)`, somente entre meses calendariamente consecutivos. Lacunas, nulos e denominador zero retornam null com justificativas. Inteiros/Decimal e strings racionais preservam a precisão; arredondamento ocorre na apresentação. Δ1, Δ2 e Δ3 são preservados, sem confundir percentual com pontos percentuais. Eixo mensal conciso e segmentos separados tornam lacunas explícitas.
- **Contexto sazonal (#14):** volume mensal como visualização principal; resumo com total observado (parcial quando necessário), máximo mensal e maior mudança absoluta. A síntese determinística usa observações calculáveis, sem inferir cobertura, pessoas vacinadas, significância ou causalidade. O tratamento inicial de extremos ocultava barras explicitamente; foi posteriormente substituído pela interrupção visual do #16, preservando o restante do resumo/hierarquia.
- **Proveniência (#15):** configuração central com DIRECT — Observado (`#16A34A`), DERIVED — Calculado (`#9333EA`) e ENRICHED — Contextualizado (`#2563EB`), com rótulos textuais, legenda e contraste claro/escuro. ENRICHED exige fonte externa documentada; não é atribuído a doses ou a uma interpretação meramente descritiva.
- **YoY e escala interrompida (#16):** `y(t)-y(t-12)` e `100*(y(t)-y(t-12))/y(t-12)`, comparando o mesmo mês calendário e filtros idênticos. Histórico consultado explicitamente e documentado fora das linhas principais. Referência ausente/nula invalida a comparação; denominador zero invalida só o percentual, preservando a diferença absoluta. O seletor MoM/YoY respeita o método solicitado; carregar histórico adicional exige ação explícita. Barras >+100% têm interrupção, anotação real, tooltip/tabela exatos e opção de escala completa. A limitação da escala é exclusivamente visual.
- **Campanhas oficiais (#17):** seção independente, catálogo JSON versionado, calendários documentais e fontes MS clicáveis; opções de 30/60 dias e aproximação mensal com razões estruturadas de indisponibilidade. Cálculo/gráfico puros preparados e testados com agregados sintéticos; **nenhum adaptador diário/consolidado real foi ativado e nenhum gráfico numérico de campanha foi habilitado**.

Não foram adicionados serviços, dependências, migrations ou novo frontend por estas melhorias Streamlit/analytics. O protótipo anterior continua nas branches empilhadas como conteúdo herdado; isso não representa sua aprovação para integração.

### Fontes oficiais verificadas e limitação científica do MVP

O catálogo `sus_explorer/analytics/campaign_catalog.json`, versão `2026-10-08.1`, foi verificado em 08/10/2026 e possui hash no resultado. Contém calendários **previstos nos documentos citados**, não cronogramas municipais efetivos nem histórico completo de prorrogações.

| Documento oficial MS | Calendário aplicável ao RS | Evidência e metadados |
| --- | --- | --- |
| [Informe Técnico Operacional de Vacinação Contra a Influenza 2023](https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/calendario-nacional-de-vacinacao/arquivos/informe-tecnico-operacional-de-vacinacao-contra-a-influenza-2023/@@download/file) | Nacional: 10/04/2023–31/05/2023 | Introdução; seção 13/13.1 exige registro consolidado no módulo da campanha. [Página oficial](https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/calendario-nacional-de-vacinacao/arquivos/informe-tecnico-operacional-de-vacinacao-contra-a-influenza-2023/view) informa atualização em 15/03/2023; data de publicação e edição não explicitadas permanecem null, com nota. |
| [Estratégia de vacinação contra influenza — Nordeste, Centro-Oeste, Sul e Sudeste — 2024](https://www.gov.br/saude/pt-br/vacinacao/publicacoes/estrategia-de-vacinacao-contra-a-influenza-nas-regioes-nordeste-centro-oeste-sul-e-sudeste-2024) | RS pertence à Região Sul: 25/03/2024–31/05/2024 | Seção 3.2; primeira edição eletrônica de 2024. [Página oficial do informe](https://www.gov.br/saude/pt-br/vacinacao/informes/estrategia-de-vacinacao-influenza-2024/view): publicação 16/03/2024, atualização 26/03/2026. |

O catálogo preserva título, URL do documento/metadados, abrangência, localizadores, publicação quando disponível, edição e verificação. Não possui cópia binária/hash dos PDFs; uma URL oficial pode mudar. Seu versionamento não comprova atualização contínua nem doses aplicadas.

`PNIRemote.timeseries` conta registros por partição ano/mês/UF; não agrega por `dt_vacina` nem certifica completude diária, pertencimento à campanha ou equivalência entre microdados e registro consolidado. A existência da coluna de vacinação na análise de latência não resolve essas condições. Neste ambiente não havia credenciais R2 nem cubo local para validar volumes reais.

[A página oficial dos painéis de influenza](https://www.gov.br/saude/pt-br/composicao/seidigi/demas/campanhas-de-vacinacao/vacinacao-contra-a-influenza) distingue residência e ocorrência. Não foi obtida/auditada uma extração histórica compatível com todas as dimensões para este MVP; não se conclui que dados adequados não existam no MS.

Maio é o único mês inteiro comum a 2023/2024, mas a adequação dos microdados à comparação das campanhas não foi comprovada. A aproximação mensal, portanto, também permanece indisponível. Não há rateio de meses em dias. Uma janela de 60 dias ultrapassa o fim previsto de 2023 e não é encurtada silenciosamente.

Quando existir extração adequada auditada, `C(d)=sum(y(i), i=1..d)` e `diferença(d)=C_recente(d)-C_anterior(d)`. Doses observadas são DIRECT, acumulados/diferenças DERIVED e calendário ENRICHED. Dia ausente/nulo invalida acumulados posteriores; o gráfico compara somente o prefixo disponível em ambas as campanhas, com janela incompleta explícita. Filtros e bases geográfica/temporal devem coincidir. Flags do contrato não substituem auditoria. Diferenças não demonstram desempenho, cobertura, eficácia ou causa.

Detalhamento: [docs/official_campaigns.md](official_campaigns.md), [docs/streamlit.md](streamlit.md) e [docs/temporal_queryplan.md](temporal_queryplan.md).

### Evidências de validação

As execuções abaixo são locais, nas árvores das branches citadas; **não são validação do master, dos upgrades Dependabot ou do banco PostgreSQL real**.

| Entrega | Resultado registrado de `python -m pytest tests -q -rs` |
| --- | --- |
| PR #13 — percentuais mensais | 303 aprovados, 7 PostgreSQL pulados |
| PR #14 — contexto sazonal | 314 aprovados, 7 PostgreSQL pulados |
| PR #15 — cores e acessibilidade | 329 aprovados, 7 PostgreSQL pulados |
| PR #16 — YoY/barras interrompidas | 352 aprovados, 7 PostgreSQL pulados |
| PR #17 — campanhas | **380 aprovados, 7 PostgreSQL pulados, 0 falhos** |

A árvore final testada do MVP de campanhas é `1b2214447ea13ea468bb577d716ad1baefade9cf`, publicada no head remoto `04f6cf290a9e895c8cb8a338c48f08cf150d9c26` antes desta atualização documental. Foram acrescentados 28 casos de campanhas. Streamlit AppTest verifica fontes clicáveis, seletores, ausência de nova consulta e preservação do payload; não houve captura de navegador. Dados de acumulados de campanha usados nos testes são sintéticos. YoY também inclui teste PyArrow real em memória com filtros. `git diff --check` passou. Não houve chamada real Gemini/R2, auditoria de doses de campanha ou execução PostgreSQL nesta etapa.

Um teste antigo da interface supunha existir exatamente uma tabela na página; passou a identificar a tabela mensal pelas colunas e verificar os valores preservados, permitindo a seção adicional de evidências. O resultado completo acima inclui essa correção.

## 2026-10-08 — Saneamento dos pull requests abertos

### Referência e critério de classificação

Foi consultada a coleção de PRs abertos com paginação (12 na página 1; página 2 vazia), revisados seus patches/arquivos em relação às bases próprias e comparados à árvore de `master`:

- commit: [`7e7b3976f1feb20c9b0c6c8b080affa76fa2e0b4`](https://github.com/GustavoDMentz/Sus-Explorer/commit/7e7b3976f1feb20c9b0c6c8b080affa76fa2e0b4), merge do PR #9;
- árvore: `51f0f06038cb4f0634d5a022eab6c4685f29dd79`;
- verificação: árvores/blobs, patches, versões do CI/dependências e implementações presentes no commit congelado. A presença em outra branch/PR **não** foi tratada como integração ao master.

**Integrado:** alterações já no master. **Obsoleto:** direção substituída/abandonada, sem alteração útil do core a descartar. **Pendente:** trabalho útil ainda não incorporado; PR misto ou parcialmente substituído continua aberto quando possui trabalho útil. Não se classificou um PR como obsoleto apenas por idade, conflito ou bloqueio por dados.

Resultado: **0 integrados, 1 obsoleto fechado (#10), 11 pendentes mantidos abertos**. As atualizações de dependências não foram aprovadas/testadas implicitamente por este saneamento.

| PR | Título | Classificação | Ação | Justificativa contra master |
| --- | --- | --- | --- | --- |
| [#3](https://github.com/GustavoDMentz/Sus-Explorer/pull/3) | build(deps): bump actions/setup-python from 6.1.0 to 7.0.0 | Pendente | Mantido aberto | master usa setup-python v6.1.0 (83679a8); o PR propõe v7.0.0 (5fda3b9). Atualização válida, ainda precisa de revisão/CI. |
| [#4](https://github.com/GustavoDMentz/Sus-Explorer/pull/4) | build(deps): bump actions/checkout from 6 to 7 | Pendente | Mantido aberto | master usa checkout v6.0.1 no CI PostgreSQL e v6 no verify-r2; o PR propõe v7.0.1/v7. Ainda não incorporado. |
| [#5](https://github.com/GustavoDMentz/Sus-Explorer/pull/5) | build(deps): bump numpy from 2.3.5 to 2.5.3 | Pendente | Mantido aberto | master fixa numpy 2.3.5; o PR propõe 2.5.3 e eleva o requisito mínimo. Compatibilidade ainda requer revisão. |
| [#6](https://github.com/GustavoDMentz/Sus-Explorer/pull/6) | build(deps): bump pandas from 2.2.3 to 3.0.6 | Pendente | Mantido aberto | master fixa pandas 2.2.3; o PR propõe 3.0.6. Migração de versão principal ainda requer revisão. |
| [#10](https://github.com/GustavoDMentz/Sus-Explorer/pull/10) | feat(web): dual-mode SUS Explorer prototype with thin Python API | Obsoleto | Fechado com comentário | Somente protótipo Next.js/FastAPI (13 arquivos adicionados), direção substituída por Streamlit direto. Fechado como obsoleto, sem afirmar integração. |
| [#11](https://github.com/GustavoDMentz/Sus-Explorer/pull/11) | fix(gemini): preserve strict structured output using native JSON Schema | Pendente | Mantido aberto | master ainda usa response_schema=QueryPlan; JSON Schema nativo/validação/retry e testes Gemini continuam úteis. Alterações de API/frontend são parciais obsoletas, não motivo para descartar o core. |
| [#12](https://github.com/GustavoDMentz/Sus-Explorer/pull/12) | feat(streamlit): restore primary interface with charts and temporal results | Pendente | Mantido aberto | master não tem streamlit_views.py nem testes específicos; formulário/gráficos/exportações, convenção de intervalos e filtro textual de imunobiológico ainda precisam de integração. |
| [#13](https://github.com/GustavoDMentz/Sus-Explorer/pull/13) | feat(streamlit): clearer temporal charts and exact monthly percentages | Pendente | Mantido aberto | master não tem analytics/percentage.py ou pct_change; percentuais mensais exatos e visualização de lacunas ainda não integrados. |
| [#14](https://github.com/GustavoDMentz/Sus-Explorer/pull/14) | feat(streamlit): contextualize seasonal vaccination volumes and extreme percentages | Pendente | Mantido aberto | master não tem summarize_series, cards sazonais ou testes. O tratamento visual antigo de extremos evolui no #16, mas resumo e hierarquia continuam válidos. |
| [#15](https://github.com/GustavoDMentz/Sus-Explorer/pull/15) | feat(streamlit): standardize accessible provenance colors and labels | Pendente | Mantido aberto | master não tem streamlit_provenance.py; cores centralizadas, contraste e rótulos acessíveis ainda não integrados. |
| [#16](https://github.com/GustavoDMentz/Sus-Explorer/pull/16) | feat(temporal): add calendar YoY comparison and explicit broken percentage bars | Pendente | Mantido aberto | master não tem yoy.py/comparison MoM/YoY; histórico explícito, YoY independente e barras interrompidas ainda não integrados. |
| [#17](https://github.com/GustavoDMentz/Sus-Explorer/pull/17) | feat(campaigns): add official RS influenza catalog and guarded comparison section | Pendente | Mantido aberto | master não tem catálogo/analytics/campaigns.py/streamlit_campaigns.py. MVP documenta indisponibilidade numérica real e requer revisão; não é obsoleto por estar bloqueado por dados. |

O #10 teve seus 13 arquivos revisados: somente `frontend/`, `web_api.py`, `requirements-web.txt`, testes HTTP e documentação do protótipo; não modifica o core analítico. Foi fechado como **obsoleto, não integrado**, com [comentário explicativo](https://github.com/GustavoDMentz/Sus-Explorer/pull/10#issuecomment-6064607106). A correção Gemini do #11 não foi descartada.

### Heads e dependências preservados

Os heads examinados (antes da atualização documental desta entrada) foram:

| PR | Head | Base do PR |
| --- | --- | --- |
| #3 | `ea49aa67591489297a21636ddc966527ce2a5354` | `master` |
| #4 | `1a3fe9004cf0e046abd65222d879ecc17aa715a2` | `master` |
| #5 | `2abcf01cd22b60b3bfb3ddcddf9c138cdf3523d1` | `master` |
| #6 | `ad6bc0557cf51d4a82314bbbde3b6ad7092b8843` | `master` |
| #10 | `6e96c1b715b56f868acbbccce1b3da585129a309` | `master` |
| #11 | `4b423b11aab3634dbf86983c62d473562bbb8220` | `feature/web-explorer-v1` |
| #12 | `b382337fc1bc0ec8bdba526c319e8d3e25006697` | `fix/gemini-native-json-schema` |
| #13 | `7f138e7fb76136ae05d83a17e6a639c996c5e869` | `feature/streamlit-analytics` |
| #14 | `d9216cd3ca2c1db7de29256233bce40ac63dc588` | `feature/streamlit-temporal-percent` |
| #15 | `82149792be7d5c47c2c60a2708ba17d09b26c821` | `feature/streamlit-seasonal-context` |
| #16 | `1c4610a9999f898c19073f53711a57d980299aa4` | `feature/streamlit-provenance-colors` |
| #17 | `04f6cf290a9e895c8cb8a338c48f08cf150d9c26` | `feature/temporal-yoy-broken-scale` |

Os PRs #11–#17 estão empilhados: #11 tem base na branch do #10, #12 na do #11, e assim sucessivamente até #17. Fechar #10 não apaga sua branch nem retira código herdado das branches seguintes. **A integração futura precisa revisar/isolar as mudanças úteis e evitar incorporar automaticamente o protótipo Next.js/FastAPI.** Não houve retarget, cherry-pick, merge, exclusão de branch ou reescrita de histórico. O fato de #16 evoluir as barras de #14 não torna o resumo/hierarquia deste último descartáveis antes da integração.

Esta atualização do diário foi adicionada à branch/PR #17 existente, sem criar outro PR ou escrever diretamente em master. O fechamento de #10 é reversível e preserva comentário, commits e branch; os outros PRs continuam disponíveis para revisão.
