import os
print("GROQ_API_KEY length:", len(os.getenv("GROQ_API_KEY", "")))
print("DOCGEN_LLM_PROVIDER:", os.getenv("DOCGEN_LLM_PROVIDER"))
print("DOCGEN_GROQ_MODEL:", os.getenv("DOCGEN_GROQ_MODEL"))