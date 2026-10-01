import os

# Tests never call real tracing; LangSmith would otherwise try to upload runs.
os.environ["LANGSMITH_TRACING"] = "false"
