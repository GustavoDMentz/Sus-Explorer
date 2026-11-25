# Interface Streamlit

A interface possui quatro áreas: explorador, histórico da sessão, disponibilidade das competências e fontes/proveniência. A pergunta é enviada somente pelo formulário; mudanças de visualização não repetem a consulta.

O estado da sessão conserva no máximo 20 resultados quando o usuário habilita essa opção. Perguntas não são persistidas no PostgreSQL. O histórico persistente opcional guarda planos e agregados seguros, não texto livre.

Resultados distinguem observações diretas, métricas derivadas e contexto documental. Tabelas preservam valores exatos; gráficos omitem números que o navegador não representa com segurança e não conectam lacunas. Referências documentais exibem arquivo, chunk e similaridade.

Falhas de configuração, banco ou Ollama aparecem como mensagem genérica ao usuário; detalhes e credenciais não são expostos. Pergunta vazia é recusada antes do serviço. O catálogo informa indisponibilidade sem convertê-la em zero.

Os testes funcionais usam `streamlit.testing.v1.AppTest` para submissão, estado, histórico, esclarecimento, erros, tabelas, gráficos, referências, catálogo e controles de visualização. Eles isolam fronteiras externas e não substituem o E2E real.
