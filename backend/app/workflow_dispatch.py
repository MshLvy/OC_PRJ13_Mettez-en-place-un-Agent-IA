"""Thin HTTP adapter. Intents are selected by server routes, never by a free URL."""

def dispatch(request, intent, **payload):
    trace = []
    request.state.workflow_trace = trace
    return request.app.state.workflow.invoke(intent, payload, trace=trace)
