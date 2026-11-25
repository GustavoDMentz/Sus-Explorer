# Segurança

## Fronteiras

- Perguntas são normalizadas, limitadas e validadas antes de REGEX, modelo ou banco.
- Planos são tipados e limitam períodos, textos, códigos, idades e volume de saída.
- SQL analítico usa parâmetros; somente expressões de agrupamento de uma allowlist entram na construção da consulta.
- O papel do aplicativo é somente leitura; ingestão, histórico e migrations usam credenciais distintas.
- Payloads descartam identificadores de pacientes, datas de nascimento, CEP e residência.
- Logs estruturados redigem credenciais, tokens, URLs assinadas, CPF, CNS e e-mail.
- ZIPs são verificados contra path traversal, membros duplicados, tamanho e razão de compressão.
- Ollama remoto exige opt-in e HTTPS; redirecionamentos são recusados.

## RAG e prompt injection

Documentos recuperados são dados não confiáveis. O modelo recebe instrução explícita para ignorar comandos contidos nos chunks. A saída é estruturada e referências precisam pertencer ao conjunto recuperado. Sem evidência verificável, o sistema retorna contexto insuficiente.

Essa defesa reduz a superfície de injeção, mas não comprova que uma afirmação é sustentada pela referência selecionada. Use a bateria qualitativa e revisão humana para decisões de alto impacto.

## Privacidade e divulgação

O modelo recebe agregados, nunca linhas. Células abaixo do limiar são suprimidas e idade é agrupada. Consultas sucessivas ainda podem ser combinadas; execução pública exige autenticação, rate limiting, política de finalidade e avaliação de risco adicional.

## Verificação

```bash
python scripts/demo_security.py
python -m pytest tests/unit/test_question_hygiene.py tests/unit/test_plan_bounds.py \
  tests/unit/test_rag.py tests/unit/test_redaction_formats.py -q
```

Auditoria de dependências vulneráveis deve ocorrer no CI com ferramenta e base atualizadas. O lock com hashes protege integridade de distribuição, mas não substitui análise de vulnerabilidade.
