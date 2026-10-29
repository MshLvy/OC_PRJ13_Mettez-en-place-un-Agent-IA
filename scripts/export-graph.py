"""Run with backend requirements available. No app.main, provider or model import."""
from app.workflow import build_workflow
g,children=build_workflow()
print(g.get_graph(xray=True).draw_mermaid())
