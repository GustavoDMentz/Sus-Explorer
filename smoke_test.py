from sus_explorer.pni import PNIRemote
from sus_explorer.schemas import QueryPlan
p=QueryPlan(operation='count',year=2026,month=5,uf='RS')
print(PNIRemote().execute(p).model_dump_json(indent=2))
