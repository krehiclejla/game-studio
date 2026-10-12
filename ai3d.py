#!/usr/bin/env python3
"""3D AI Studio (paid, the owner's credits) for Game Studio: text-to-3D with Tripo 3.2 on
api.3daistudio.com. Game Studio makes new 3D models only this way (no drawing, no picture-to-3D).

  python3 ai3d.py balance                                   credits left (free; also checks the key)
  python3 ai3d.py text "PROMPT" OUT.glb [--low-poly] [--faces N] [--detailed]

Costs (credits): 40 per model; --low-poly (game-ready topology) +20; --detailed
texture +20. --faces caps the triangle count (free): about 8000-15000 for characters,
1500-5000 for props. Each run prints the credits it used and what is left. It takes
1-3 minutes. The model comes out standing up (+Y up), about 1 unit tall; rig it or size
it with the usual detailed.py steps (rig ... --no-body, weapon, upright).
If there is no key, no credits, or the service fails, the command says so and exits 2:
then say so: the person can add credits in their 3D AI Studio dashboard.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from studio_app import app_id

API = 'https://api.3daistudio.com'
SECRET = '3daistudio-key'
POLL = 25          # seconds between status checks (the API allows 3 requests a minute)


def fallback(msg):
    print(json.dumps({'ok': False, 'error': msg, 'next': 'Tell the person; offer the free character library, or shapes.py for objects.'}))
    sys.exit(2)


def key():
    if os.environ.get('THREEDAI_KEY'):
        return os.environ['THREEDAI_KEY']
    base = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
    token = os.environ.get('AGENT_TOKEN') or os.environ.get('APP_TOKEN')
    req = urllib.request.Request(f'{base}/api/apps/{app_id()}/secrets/{SECRET}', headers={'Authorization': f'Bearer {token}'})
    try:
        return urllib.request.urlopen(req, timeout=20).read().decode().strip() or None
    except Exception:
        return None


def call(k, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={'Authorization': f'Bearer {k}', 'Content-Type': 'application/json', 'User-Agent': 'MobiusGameStudio'})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                return json.loads(res.read() or b'{}')
        except urllib.error.HTTPError as e:
            text = e.read().decode('utf8', 'replace')[:400]
            if e.code == 429:                       # rate limit: wait and retry
                time.sleep(25)
                continue
            if e.code in (401, 403):
                fallback('The 3D AI Studio key was rejected (' + text + '). Ask the person to add a new key.')
            if e.code == 402 or 'credit' in text.lower() or 'balance' in text.lower():
                fallback('Not enough 3D AI Studio credits (' + text + '). The person can buy more in their 3D AI Studio dashboard.')
            fallback(f'3D AI Studio error {e.code}: {text}')
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                time.sleep(10)
                continue
            fallback(f'Could not reach 3D AI Studio: {e}')
    fallback('3D AI Studio kept rate-limiting the request.')


def balance(k):
    b = call(k, 'GET', '/account/user/wallet/').get('balance')
    try:
        return float(b)
    except (TypeError, ValueError):
        return None


def generate(k, source, out, low_poly=False, faces=None, detailed=False):
    body = {'texture': True, 'pbr': False, 'texture_quality': 'detailed' if detailed else 'standard'}
    if low_poly:
        body['smart_low_poly'] = True
    if faces:
        body['face_limit'] = int(faces)
    body['prompt'] = source[:1024]
    before = balance(k)
    task = call(k, 'POST', '/v1/3d-models/tripo/text-to-3d/3.2/', body)
    tid = task.get('task_id')
    if not tid:
        fallback(f'3D AI Studio did not start the job: {json.dumps(task)[:300]}')
    start = time.time()
    while True:
        time.sleep(POLL)
        st = call(k, 'GET', f'/v1/generation-request/{tid}/status/')
        status = st.get('status')
        if status == 'FINISHED':
            break
        if status == 'FAILED':
            fallback('3D AI Studio could not make it: ' + str(st.get('failure_reason')))
        if time.time() - start > 900:
            fallback('3D AI Studio took more than 15 minutes; job ' + tid)
    url = next((r.get('asset') for r in st.get('results', []) if str(r.get('asset', '')).split('?')[0].endswith('.glb')), None) \
        or next((r.get('asset') for r in st.get('results', []) if r.get('asset')), None)
    if not url:
        fallback('3D AI Studio finished but returned no model: ' + json.dumps(st)[:300])
    req = urllib.request.Request(url, headers={'User-Agent': 'MobiusGameStudio'})
    Path(out).write_bytes(urllib.request.urlopen(req, timeout=300).read())
    after = balance(k)
    used = round(before - after, 2) if before is not None and after is not None else None
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': Path(out).stat().st_size, 'seconds': round(time.time() - start),
                      'credits_used': used, 'credits_left': after,
                      'next': 'Render it and Read it; then rig (detailed.py rig OUT.glb RIGGED.glb --no-body), make a weapon '
                              '(detailed.py weapon) or size a prop (detailed.py upright) as usual. Tell the person the credits used.'}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('action', choices=['balance', 'text'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--low-poly', action='store_true')
    ap.add_argument('--faces', type=int)
    ap.add_argument('--detailed', action='store_true')
    a = ap.parse_args()
    k = key()
    if not k:
        fallback('No 3D AI Studio key is saved yet: the person can add one (the studio agent asks with a sealed card).')
    if a.action == 'balance':
        print(json.dumps({'ok': True, 'credits_left': balance(k)}))
    elif len(a.args) != 2:
        sys.exit(f'usage: ai3d.py {a.action} SOURCE OUT.glb')
    else:
        generate(k, a.args[0], a.args[1], a.low_poly, a.faces, a.detailed)


if __name__ == '__main__':
    main()
