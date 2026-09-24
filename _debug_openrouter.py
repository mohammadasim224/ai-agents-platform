import os
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv(Path('.env'))
key = os.getenv('OPENROUTER_API_KEY', '')
models = [
    os.getenv('DEFAULT_MODEL', ''),
    os.getenv('MANAGER_MODEL', ''),
    os.getenv('MARKETING_MODEL', ''),
    os.getenv('SALES_MODEL', ''),
    os.getenv('AUTOMATION_MODEL', ''),
    os.getenv('EVALUATION_MODEL', ''),
]
print('KEY_OK=', bool(key.strip()))
headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
for m in [x for x in models if x]:
    payload = {'model': m, 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 10}
    try:
        r = requests.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=payload, timeout=30)
        print('MODEL=', m, 'STATUS=', r.status_code)
        print('BODY=', r.text[:250].replace('\n', ' '))
    except Exception as e:
        print('MODEL=', m, 'ERROR=', type(e).__name__, str(e)[:200])
