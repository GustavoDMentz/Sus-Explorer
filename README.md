# SUS Explorer 💉

**Explore dados públicos de vacinação do Brasil fazendo perguntas em português.**

O SUS Explorer é um projeto experimental que ajuda estudantes, pesquisadores e profissionais da saúde a consultar registros do **Sistema de Informação do Programa Nacional de Imunizações (SI-PNI)**, sem precisar escrever código ou manipular planilhas grandes.

Em vez de montar uma consulta técnica, você descreve o que deseja investigar. A ferramenta busca os dados disponíveis, apresenta números e gráficos e informa a origem das informações.

> **Projeto em desenvolvimento.** Os resultados dependem da disponibilidade dos dados e precisam ser interpretados com cuidado. O SUS Explorer não é uma ferramenta oficial do Ministério da Saúde nem substitui sistemas oficiais de vigilância e informação.

## Como acessar

**O SUS Explorer é disponibilizado como projeto de código aberto para execução no próprio computador.** Não há uma versão pública hospedada da aplicação. Para utilizá-lo, siga o [guia de instalação](docs/technical-guide.md#instalação-para-iniciantes).

Ao abrir o aplicativo:

1. Informe sua **chave da API Gemini** na barra lateral. Ela é necessária para interpretar perguntas em linguagem natural. O acesso aos dados de vacinação é configurado pelo projeto.
2. Escreva uma pergunta indicando **local e período**.
3. Clique em **Explorar** e aguarde o processamento. Algumas consultas podem levar minutos.
4. Examine os números, gráficos, avisos e a aba **Fontes e proveniência**.

A chave Gemini é fornecida pelo próprio usuário. Seu uso pode estar sujeito a limites ou cobranças do provedor. **Não compartilhe sua chave em mensagens, issues ou capturas de tela.**

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
- **Ausência de dados não significa zero.** Se uma partição mensal estiver indisponível, o sistema deve indicar a lacuna em vez de tratá-la como nenhuma vacinação.
- **Associação não significa causalidade.** Mudanças nos registros podem refletir campanhas, sazonalidade, atraso de registro e outros fatores. O gráfico, sozinho, não explica a causa.

Use os resultados como apoio à **exploração e formulação de hipóteses**, não como evidência isolada para decisões clínicas ou conclusões epidemiológicas.

## De onde vêm os dados?

A fonte primária é o **Ministério da Saúde / OpenDATASUS**, por meio dos registros do SI-PNI.

O projeto utiliza arquivos disponibilizados pelo [**healthbr-data**](https://github.com/SidneyBissoli/healthbr-data), desenvolvido e mantido por **Sidney da Silva Bissoli**, que organiza e distribui os dados em formato adequado para análise.

Agradecemos especialmente ao Sidney pelo trabalho de disponibilização e manutenção dessa infraestrutura aberta. O SUS Explorer é independente do healthbr-data e não reivindica autoria dos registros originais. Consulte as orientações de licença e atribuição do [projeto de origem](https://github.com/SidneyBissoli/healthbr-data#license).

## Limitações atuais

O SUS Explorer é um **protótipo de pesquisa em evolução**. Algumas perguntas podem não ser compreendidas corretamente, alguns filtros podem não estar disponíveis e consultas remotas podem demorar ou falhar. Nem todos os períodos e locais têm necessariamente dados publicados.

Quando usar informações em relatórios, apresentações ou trabalhos científicos, confira o período, os filtros, a fonte e a consistência dos resultados com as bases oficiais.

## Para quem desenvolve ou quer contribuir

A documentação técnica foi preservada e organizada separadamente:

- [**Guia técnico e operacional**](docs/technical-guide.md) — instalação passo a passo para iniciantes, configuração avançada, arquitetura, segurança e testes.
- [**Documentação do projeto**](docs/) — detalhes da interface, análise temporal e persistência.
- [**Diário de desenvolvimento**](docs/development_journal.md) — histórico de decisões e entregas.
- [**Registro de pull requests**](docs/pr_register.md) — alterações integradas e trabalhos pendentes.

Sugestões de perguntas, problemas de interpretação e melhorias na apresentação são bem-vindos nas [issues do repositório](https://github.com/GustavoDMentz/Sus-Explorer/issues). Evite incluir credenciais ou informações pessoais de pacientes.
