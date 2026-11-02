
import json, os, sys
import httpx

key = sys.argv[1]
base = "https://api.deepseek.com/v1"
payload = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "system", "content": "You are a professional simultaneous interpreter dubbing online video. Translate the user's subtitle line into English. Output ONLY the translation."},
        {"role": "user", "content": "别紧张，你可是魔王，命中注定要把命交给你，我不要这个。"},
    ],
    "temperature": 0.2,
}
try:
    with httpx.Client(timeout=20) as c:
        r = c.post(base + "/chat/completions", json=payload, headers={"Authorization": "Bearer " + key})
        print("status", r.status_code)
        if r.status_code == 200:
            print("translation:", r.json()["choices"][0]["message"]["content"].strip())
        else:
            print(r.text[:300])
except Exception as e:
    print("ERR", type(e).__name__, str(e)[:200])
