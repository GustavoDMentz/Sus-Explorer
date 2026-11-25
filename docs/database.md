# Banco de dados

## Migrations e schema

As migrations numeradas em `sus_explorer/data/persistence/migrations/` são imutáveis, verificadas por SHA-256 e aplicadas em ordem sob lock transacional:

```bash
python -m sus_explorer.data.persistence.migrate
```

O schema armazena execuções de ingestão, registros brutos minimizados, revisões, observações por snapshot, projeções tipadas, histórico opcional e documentos/chunks do RAG. O executor lê somente a última execução `SUCCESS` reconciliada de cada partição.

## Papéis

| Perfil | Uso | Privilégio esperado |
| --- | --- | --- |
| reader | aplicativo, catálogo e busca RAG | SELECT analítico/documental |
| ingest | importadores | escrita nas tabelas de ingestão |
| history | históricos opcionais | escrita limitada às tabelas de histórico |
| migrator | migrations, expurgo e indexação | proprietário dos objetos administrativos |

O superusuário do Compose serve ao bootstrap e às migrations que administram atributos de papéis. A aplicação usa `reader`.

## Retenção e reimportação

Reimportar um ZIP republicado cria novo run e novas observações; registros alterados preservam revisões. Registros ausentes no novo snapshot permanecem no histórico, mas deixam de ser servidos porque o executor atravessa somente as observações do run atual.

Microdados e revisões não têm expurgo automático. A ferramenta `purge` simula por padrão, exige motivo e papel administrativo, recusa partição em ingestão e registra auditoria. Backups devem preservar chaves do histórico cifrado e ser testados por restauração.

## Auditoria semântica

```bash
python -m sus_explorer.data.persistence.semantic_audit
```

O comando é somente leitura e verifica duplicação dentro do snapshot, alinhamento de revisão/projeção, competência da data, UF, código municipal e reutilização de chave entre competências. O último caso é aviso para investigação, pois pode indicar duplicação de evento entre arquivos.
