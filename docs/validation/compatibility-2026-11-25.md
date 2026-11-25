# Compatibilidade e reprodutibilidade — 25/11/2026

## Alvo oficial

Linux, Python 3.12 e instalação com `python -m pip install --require-hashes -r requirements-lock.txt`. O CI configura Python 3.12 e usa o mesmo lockfile.

## Verificações disponíveis nesta máquina

- somente Python 3.13.15 estava instalado;
- ambiente virtual Windows instalou as versões fixadas em `constraints.txt` e aprovou `pip check`;
- suíte local completa e compilação de todos os módulos foram executadas;
- 25 testes estáticos de lockfile, hashes, pins e defaults de rede passaram;
- Docker Engine estava parado; WSL tinha apenas a distribuição `docker-desktop` e não fornecia um ambiente Linux executável independente;
- `py -3.12` falhou por ausência do runtime.

Assim, o código foi exercitado em Windows/Python 3.13, mas uma instalação limpa Linux/Python 3.12 não foi reproduzida nesta execução. O CI versionado é evidência do procedimento, não substitui uma execução local atual do job remoto.
