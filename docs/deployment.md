# Implantação e operação

O modo suportado é execução local ou em host controlado, com Streamlit, PostgreSQL/pgvector e Ollama. O repositório não expõe API REST pública.

1. Instale com Linux/Python 3.12 e lockfile.
2. Configure `.env` e papéis de banco distintos.
3. Inicie PostgreSQL e Ollama.
4. Verifique modelos e dimensão.
5. Aplique migrations.
6. Importe competências incrementalmente.
7. Indexe apenas documentação pública revisada.
8. Execute diagnóstico, suíte local e canários externos.
9. Inicie `streamlit run app.py` atrás do controle de acesso adequado ao ambiente.

As portas do Compose são ligadas a `127.0.0.1`. Para acesso remoto, prefira proxy TLS e autenticação; não publique PostgreSQL ou Ollama diretamente. Monitore disco, WAL, conexões, latência de consulta, recuperação e inferência.

Backups precisam incluir banco e chaves necessárias aos históricos cifrados. Teste restauração. O staging de ZIPs pode ser efêmero; checkpoints e trilha de ingestão devem ser preservados.
