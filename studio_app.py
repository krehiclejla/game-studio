"""This Game Studio's own app id, on any Möbius install (it is not always 12).

Order: GS_APP_ID or APP_ID from the environment (job.sh exports APP_ID from the
scheduler's first argument), else the installed app whose source folder is this
one, else 12 (the original install).
"""
import json
import os
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_cached = None


def app_id() -> str:
    global _cached
    if _cached:
        return _cached
    found = os.environ.get('GS_APP_ID') or os.environ.get('APP_ID')
    if not found:
        base = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
        token = os.environ.get('AGENT_TOKEN') or os.environ.get('APP_TOKEN')
        try:
            req = urllib.request.Request(f'{base}/api/apps/', headers={'Authorization': f'Bearer {token}'})
            apps = json.loads(urllib.request.urlopen(req, timeout=20).read() or b'[]')
            for app in apps if isinstance(apps, list) else []:
                src = app.get('source_dir')
                if src and Path(src).resolve() == _HERE:
                    found = str(app['id'])
                    break
        except Exception:
            pass
    _cached = str(found or '12')
    return _cached
