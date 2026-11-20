# Retenção de dados e expurgo

Este documento define **o que o SUS Explorer guarda, por quanto tempo e como remover**. A origem dos dados (OpenDATASUS/SI-PNI) é pública; a política existe para limitar o que fica copiado no banco local e reduzir o dano de um backup ou *dump* que vaze.

## O que é guardado

| Dado | Onde | O que contém | Retenção |
|---|---|---|---|
| **Registro bruto atual** | `datasus_raw_records.payload` | Somente as colunas da **lista permitida** (versão 1, `sus_explorer/data/persistence/payload_policy.py`): identificador do registro, vacina, município, UF e datas do estabelecimento, sexo, idade, raça/cor, CNES, dose, sistema de origem e data de entrada no RNDS | Enquanto a partição for servida pelo app |
| **Projeção tipada** | `immunization_records` | Vacina, dose, data, município e UF | Igual ao registro bruto |
| **Revisões anteriores** | `datasus_raw_record_revisions` | Versões antigas do payload, criadas quando o Ministério republica um mês | **90 dias** após a substituição, depois expurgo (escopo `old_revisions`) |
| **Observações** | `datasus_raw_record_observations` | Qual execução viu qual registro (sem payload) | Enquanto o registro existir |
| **Execuções de ingestão** | `datasus_ingestion_runs` | Hashes, nomes de arquivo, contagens e estado (sem payload) | Permanente: é a trilha de auditoria |
| **Auditoria de expurgos** | `datasus_purge_audit` | Quem, quando, por quê e quantos registros | Permanente, imutável |
| **Histórico de consultas** | `query_history`, `analytical_result_versions` | Parâmetros tipados e resultados já com supressão de células pequenas | Sem prazo automático; ver "Pendências" |
| **Logs operacionais** | `logs/*.jsonl` (arquivos, modo 0600) | Eventos sem linhas de dados | Rotação a cargo do operador |

Colunas que o CSV oficial traz mas **não** estão na lista (por exemplo pseudônimo do paciente, data de nascimento, CEP, município de residência) são descartadas antes de chegar ao banco. Cada execução registra em seus metadados a versão da lista (`payload_allowlist_version`). Acrescentar uma coluna exige uma nova versão da lista e o código que a lê.

## Como expurgar

O expurgo é uma ferramenta administrativa e exige o papel **proprietário do schema** (migrator). Qualquer outro papel recebe erro e nada é removido. É **simulação por padrão**: sem `--execute` nada é apagado, mas a tentativa também é registrada na auditoria.

```bash
# Simulação (padrão): mostra quantos registros seriam removidos
python -m sus_explorer.data.persistence.purge --scope partition \
    --partition ano=2026/mes=01/uf=RS --reason "retirada solicitada pela fonte"

# Execução de fato
python -m sus_explorer.data.persistence.purge --scope partition \
    --partition ano=2026/mes=01/uf=RS --reason "retirada solicitada pela fonte" --execute

# Revisões antigas (escopo old_revisions)
python -m sus_explorer.data.persistence.purge --scope old_revisions \
    --older-than-days 90 --reason "retenção de revisões de 90 dias" --execute
```

- **Escopo estrito:** `partition` remove uma única partição `ano=AAAA/mes=MM/uf=XX` (registros brutos, revisões, observações e projeção) e mantém as execuções de ingestão. `old_revisions` remove só versões substituídas há mais de N dias e mantém a versão atual de cada registro.
- **Atomicidade:** os gatilhos de imutabilidade são desligados e religados dentro de **uma transação**. Se algo falhar, nada é removido e os gatilhos continuam ativos.
- **Segurança:** a partição não pode ter ingestão em andamento (o expurgo recusa e informa). O motivo (de 10 a 500 caracteres) é obrigatório e fica na auditoria junto com o usuário e as contagens.
- **Efeito no app:** uma partição expurgada aparece como **indisponível**, nunca como zero doses, até ser importada de novo. A reimportação funciona normalmente depois do expurgo.

## Backups e cópias

O expurgo age **somente no banco vivo**. Um backup, snapshot de volume ou *dump* feito antes continua com os dados até ser rotacionado. Por isso:

1. Defina uma rotação de backups de no máximo 90 dias, no mesmo prazo das revisões.
2. Depois de um expurgo por pedido da fonte, **expire também os backups anteriores** que contenham a partição, ou registre por escrito a data em que eles serão destruídos.
3. Não restaure um backup anterior a um expurgo sem repetir o expurgo (a auditoria mostra quais foram feitos).
4. Os JSONs em `audit/` guardam apenas contagens e hashes, nunca linhas.

## Pendências

- O histórico de consultas e as versões analíticas ainda não têm expurgo automático; hoje o papel de runtime não tem `DELETE` nessas tabelas.
- Não há agendamento do expurgo de revisões: rodar manualmente ou por `cron`, com o papel proprietário.
