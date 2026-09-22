import json,sys
from sus_explorer.service import SUSExplorer
if len(sys.argv)<2: raise SystemExit('Uso: python demo.py "pergunta"')
q=' '.join(sys.argv[1:]); x=SUSExplorer().ask(q)
print('\n=== RESPOSTA ===\n',x['answer']); print('\n=== PLANO ==='); print(json.dumps(x['plan'],ensure_ascii=False,indent=2)); print('\n=== RESULTADO ==='); print(json.dumps(x['result'],ensure_ascii=False,indent=2))
