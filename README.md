# SUS Explorer 💉

**Explore dados públicos de vacinação do Brasil fazendo perguntas em português.**

O SUS Explorer é um projeto experimental que ajuda estudantes, pesquisadores e profissionais da saúde a consultar registros do **Sistema de Informação do Programa Nacional de Imunizações (SI-PNI)**, sem precisar escrever código ou manipular planilhas grandes.

Em vez de montar uma consulta técnica, você descreve o que deseja investigar. A ferramenta busca os dados disponíveis, apresenta números e gráficos e informa a origem das informações.

> **Projeto em desenvolvimento.** Os resultados dependem da disponibilidade dos dados e precisam ser interpretados com cuidado. O SUS Explorer não é uma ferramenta oficial do Ministério da Saúde nem substitui sistemas oficiais de vigilância e informação.

## Como acessar

**O SUS Explorer é disponibilizado como projeto de código aberto para execução no próprio computador.** Não há uma versão pública hospedada da aplicação. O ambiente recomendado é Linux com Python 3.12, PostgreSQL/pgvector e Ollama. Consulte a [instalação](docs/installation.md) e a [configuração](docs/configuration.md).

Ao abrir o aplicativo:

1. Configure Ollama e PostgreSQL e rode `python -m sus_explorer.diagnose`.
2. Escreva uma pergunta indicando **local e período**.
3. Clique em **Explorar** e aguarde o processamento. Algumas consultas podem levar minutos.
4. Examine os números, gráficos, avisos e a aba **Fontes e proveniência**.

O processamento de IA usa modelos locais no Ollama; as consultas analíticas leem as partições completas já importadas no PostgreSQL.

## O que posso perguntar?

Experimente perguntas como:

- **Quantas doses de vacinas foram registradas no Rio Grande do Sul em maio de 2026?**
- **Como variou mensalmente o número de doses registradas no RS de janeiro a junho de 2026?**
- **Quantas doses foram registradas em Porto Alegre em maio de 2026?**
- **Como os registros de vacinação contra influenza variaram ao longo de um período?**

Esses são exemplos de consultas, **não resultados já calculados**. A resposta depende das partições disponíveis e dos filtros aceitos para cada análise.

## O que a ferramenta apresenta?

| Recurso | Para que serve |
| --- | --- |
| **Totais de doses** | Consultar quantos registros de vacinação aparecem em determinado local e período |
| **Evolução mensal** | Observar aumentos, quedas e diferenças entre meses |
| **Comparação com o ano anterior** | Comparar um mês com o mesmo mês do ano anterior, quando há dados suficientes |
| **Tabelas e gráficos** | Facilitar a leitura e a exploração dos resultados |
| **Origem dos dados** | Mostrar de onde vieram os números e indicar períodos sem informação disponível |

A inteligência artificial ajuda a **interpretar a pergunta e explicar os resultados**. Os totais e as variações são calculados pelo sistema a partir dos registros consultados, e não inventados pelo modelo.

## Como interpretar os resultados?

Alguns cuidados são fundamentais para análises em saúde pública:

- **Doses não são pessoas.** Uma pessoa pode aparecer em mais de um registro. Portanto, o total de doses não representa automaticamente o número de pessoas vacinadas.
- **Registros não são cobertura vacinal.** Para calcular cobertura, são necessários denominadores populacionais e definições apropriadas.
- **O local se refere ao estabelecimento de vacinação.** Ele não representa necessariamente o município ou estado de residência da pessoa vacinada.
- **Números pequenos são ocultados.** Contagens menores que 5 aparecem como "menos de 5", e os filtros de idade usam faixas de 5 anos, para que ninguém seja identificado. Veja [privacidade](docs/privacy.md).
- **Ausência de dados não significa zero.** Se uma partição mensal estiver indisponível, o sistema deve indicar a lacuna em vez de tratá-la como nenhuma vacinação.
- **Associação não significa causalidade.** Mudanças nos registros podem refletir campanhas, sazonalidade, atraso de registro e outros fatores. O gráfico, sozinho, não explica a causa.

Use os resultados como apoio à **exploração e formulação de hipóteses**, não como evidência isolada para decisões clínicas ou conclusões epidemiológicas.

## De onde vêm os dados?

A fonte primária é o **Ministério da Saúde / OpenDATASUS**, por meio dos registros do SI-PNI. Os ZIPs mensais oficiais são importados **no PostgreSQL**, com identidade e hash (SHA-256) da fonte, e o serviço consulta apenas essas competências já importadas. O [pipeline incremental](docs/data-migration.md) baixa uma competência por vez, retoma downloads interrompidos e importa as UFs sequencialmente.

### Descoberta de arquivos novos

O portal oficial não oferece mais uma API CKAN pública, então o projeto inclui uma ferramenta **somente leitura** que lê a página de cada dataset anual e consulta os ZIPs no S3 oficial (tamanho, data e ETag). Ela compara com um manifesto salvo e aponta competências novas, removidas, alteradas ou listadas mas indisponíveis. **Não baixa nem importa nada.**

```bash
python -m sus_explorer.data.remote.opendatasus_catalog --years 2025 2026 --manifest audit/opendatasus-pni.json
```

Na rechecagem somente leitura de 25/11/2026, o catálogo e os cabeçalhos oficiais listaram 83 competências mensais e responderam HTTP 200 para os 83 ZIPs, somando 218,3 GB comprimidos. Isso não comprova contagens por UF nem importação local. Meses recentes são republicados com frequência, então uma competência já importada pode ficar defasada. Consulte [fontes](docs/data-sources.md) e a [evidência histórica](docs/validation/2026-11-08.md).

### Espelho histórico

O espelho [**healthbr-data**](https://github.com/SidneyBissoli/healthbr-data), desenvolvido e mantido por **Sidney da Silva Bissoli**, foi a fonte histórica antes da migração para o PostgreSQL. Os leitores desse espelho agora ficam isolados nas ferramentas de migração e não fazem parte do fluxo de consulta.

Agradecemos especialmente ao Sidney pelo trabalho de disponibilização e manutenção dessa infraestrutura aberta. O SUS Explorer é independente do healthbr-data e não reivindica autoria dos registros originais. Consulte as orientações de licença e atribuição do [projeto de origem](https://github.com/SidneyBissoli/healthbr-data#license).

## Limitações atuais

O SUS Explorer é um **protótipo de pesquisa em evolução**. Algumas perguntas podem não ser compreendidas corretamente e nem todas as competências estão importadas no PostgreSQL. Competências ausentes ou parciais não significam zero doses. Os 218,3 GB representam a soma histórica comprimida, enquanto o staging incremental mantém uma competência por vez; tabelas, índices, WAL e margem precisam de orçamento próprio baseado em medições. A última cobertura registrada em banco descartável, de 08/11/2026, tinha duas partições validadas e 2.185 pendentes; o estado atual de uma base permanente não foi conferido.

Quando usar informações em relatórios, apresentações ou trabalhos científicos, confira o período, os filtros, a fonte e a consistência dos resultados com as bases oficiais.

## Para quem desenvolve ou quer contribuir

A documentação oficial está no [índice técnico](docs/README.md): arquitetura, instalação, configuração, banco, fontes, migração incremental, RAG, analytics, interface, testes, segurança, implantação e troubleshooting. Evidências históricas permanecem separadas em `docs/validation/`.

Sugestões de perguntas, problemas de interpretação e melhorias na apresentação são bem-vindos nas [issues do repositório](https://github.com/GustavoDMentz/Sus-Explorer/issues). Evite incluir credenciais ou informações pessoais de pacientes.
