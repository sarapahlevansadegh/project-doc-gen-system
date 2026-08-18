import os
from groq import Groq
key = os.getenv("GROQ_API_KEY")
print("provider env:", os.getenv("DOCGEN_LLM_PROVIDER"))
print("model env:", os.getenv("DOCGEN_GROQ_MODEL"))
print("key len:", len(key) if key else 0)
print("key prefix:", (key[:4] if key else None))
for m in ["groq/compound-mini", "compound-mini", "llama-3.3-70b-versatile"]:
    try:
        c = Groq(api_key=key)
        r = c.chat.completions.create(model=m, messages=[{"role": "user", "content": "say hi"}], max_tokens=10)
        print(f"MODEL={m!r} -> 200 OK: {r.choices[0].message.content!r}")
    except Exception as e:
        code = getattr(e, "status_code", "?")
        print(f"MODEL={m!r} -> ERR status={code}: {str(e)[:160]}")
