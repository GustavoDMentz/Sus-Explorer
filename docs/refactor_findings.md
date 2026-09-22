# Achados da Refatoração (Refactor Findings)

Este documento registra observações, possíveis inconsistências e débitos técnicos identificados durante a refatoração arquitetural conservadora do SUS Explorer.

---

## 1. Divergência de Aliases (`POSSIBLE_BUG`)

* **Localização**: `sus_explorer/transform/pni.py` vs `sus_explorer/pni.py`
* **Descrição**: `build_cache.py` utiliza 6 aliases canônicos para agrupar e comprimir os microdados do cubo Parquet (`uf`, `municipality_code`, `vaccine_code`, `dose_code`, `age_group`, `gender`). O módulo de consulta `pni.py` possui 12 aliases expandidos para consultas remotas diretas ao R2 (adicionando colunas de detalhamento como `vaccine_text`, `facility`, `system_origin`, `race`, etc.).
* **Risco**: Manter a definição duplicada dos 6 aliases comuns pode levar a inconsistências caso um alias seja alterado em um módulo e não no outro.
* **Recomendação**: Em refatoração futura, fazer `pni.py` herdar ou compor seus aliases a partir de `sus_explorer.transform.pni.CUBE_ALIASES`.

---

## 2. Duplicação da Função `partition_key` (`POSSIBLE_BUG`)

* **Localização**: `build_cache.py` e `recover_pni_2023_10.py`
* **Descrição**: A função `partition_key(year, month, uf)` estava duplicada em ambos os arquivos.
* **Ação tomada**: Centralizada em `sus_explorer.transform.pni.partition_key`. Ambos os módulos agora importam a mesma implementação.

---

## 3. Duplicação Proposital de Transformações na Auditoria (`ARCHITECTURE_DEBT`)

* **Localização**: `sus_explorer/audit_ms_2023_10.py`
* **Descrição**: O script de auditoria reimplementa localmente as funções `norm()` e `age_band()` sem importar de `sus_explorer.transform.pni`.
* **Justificativa**: Conforme documentado no próprio código (`# Implementação propositalmente independente do build_cache.py para garantir auditoria cega e isenta`), a duplicação é intencional por design. O auditor não deve confiar nas funções de produção que está auditando.
* **Recomendação**: Preservar essa independência estritamente em futuras refatorações.

---

## 4. Instanciação Duplicada do S3FileSystem (`ARCHITECTURE_DEBT`)

* **Localização**: `sus_explorer/data/remote/r2.py` vs `sus_explorer/pni.py`
* **Descrição**: `build_cache.py` agora utiliza `sus_explorer.data.remote.r2.make_filesystem()`, enquanto `pni.py` (`PNIRemote`) continua instanciando seu próprio `s3fs.S3FileSystem` em `__post_init__`.
* **Justificativa**: `pni.py` é o mecanismo de consulta ativo em produção. Preservá-lo integralmente diminui drasticamente o risco da refatoração nesta primeira fase.
* **Recomendação**: Integrar `pni.py` com `sus_explorer.data.remote.r2` em uma segunda fase dedicada de refatoração.
