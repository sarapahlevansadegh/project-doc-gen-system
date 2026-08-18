"""Quick diagnostic: check Groq config and LLMClient."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "/app/backend")

print("step 1: checking env")
print("GROQ_API_KEY length:", len(os.getenv("GROQ_API_KEY", "")))
print("DOCGEN_LLM_PROVIDER:", os.getenv("DOCGEN_LLM_PROVIDER"))
print("DOCGEN_GROQ_MODEL:", os.getenv("DOCGEN_GROQ_MODEL"))
print("GROQ_BASE_URL:", os.getenv("GROQ_BASE_URL", "not set"))

print("step 2: importing config")
from config import settings
print("settings.groq_api_key length:", len(settings.groq_api_key))

print("step 3: importing LLMClient")
from agent.llm import LLMClient
print("LLMClient imported")

print("step 4: creating instance")
llm = LLMClient()
print("provider:", llm.provider)
print("model:", llm.model)
print("done")