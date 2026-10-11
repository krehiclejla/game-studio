#!/usr/bin/env python3
"""Game Studio's character queue, run on the server (scheduled every minute, and
kicked right away whenever something is asked for or finishes), so designs keep
coming while the app is closed.

design-jobs.json holds the queue. Each pass:
  1. A request for several characters comes back as character-plans/<job>.json:
     replace that job with one queued job per planned character.
  2. A running job whose draft landed is done; one silent for too long has failed.
  3. Start queued jobs, oldest first, while fewer than MAX_RUNNING run. Starting is
     idempotent per job (the chat scope is the job id), so a repeat is harmless.
Writes use If-Match, so a change the app makes at the same moment is never lost.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
TOKEN = os.environ.get('APP_TOKEN') or os.environ.get('AGENT_TOKEN', '')
APP = os.environ.get('APP_ID', '12')
JOBS = 'design-jobs.json'
MAX_RUNNING = 2   # 3D is made one step at a time on this machine; two keeps it busy
TIMEOUT_MS = 20 * 60 * 1000
CREATIVE = ('claude-opus-5-5', 'claude-opus', 'claude-sonnet')  # preferred families, best first


def creative_model():
    """A strong model the person has connected (Möbius lists only those), else None so
    the chat uses their own default model."""
    status, data, _ = call('GET', '/api/models')
    ids = [str(m.get('id')) for models in ((data or {}).get('providers') or {}).values() for m in models
           if m.get('available', True)] if status == 200 else []
    for prefix in CREATIVE:
        hit = next((i for i in ids if i.startswith(prefix)), None)
        if hit:
            return hit
    return None


def call(method, path, body=None, headers=None):
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={
        'Authorization': f'Bearer {TOKEN}', **({'Content-Type': 'application/json'} if data is not None else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read()
            return res.status, (json.loads(raw) if raw else None), res.headers.get('ETag')
    except urllib.error.HTTPError as err:
        return err.code, None, None


def storage(path):
    return f'/api/storage/apps/{APP}/{path}'


def planned_job(parent, item, index, now):
    """One queued job for a planned character (the app builds the same shape)."""
    job_id = f"{parent['id'][:24]}{index:02d}"
    hints = '. '.join(x for x in (f"Body: {item['body']}" if item.get('body') else '', f"Build: {item['build']}" if item.get('build') else '', f"Weapon (make it as an asset and equip it; draw the body with --empty-hands): {item['weapon']}" if item.get('weapon') else '', f"Height: {item['height']} m" if item.get('height') else '',
                                    f"Role: {item['role']}" if item.get('role') else '') if x)
    extra = ' '.join(x for x in (f"--body {item['body']}" if item.get('body') else '', f"--height {item['height']}" if item.get('height') else '',
                                   f"--role {item['role']}" if item.get('role') else '') if x)
    group = parent.get('description') or ''
    lead = (f'Make ONE 3D game character, part of a planned cast (make only this one; the cast was asked for as: {group})' if group
            else 'Make a 3D game character')
    content = (f'{lead} named "{item["name"]}": {item["description"]}' + (f'\n{hints}.' if hints else '')
               + f'\nSave the design with: --job {job_id} --source ai {extra} --prompt {json.dumps(item["description"])}')
    system = (parent.get('launch') or {}).get('systemPrompt')
    if not system:
        status, prompts, _ = call('GET', storage('design-prompts.json'))
        system = (prompts or {}).get('pictureTo3d') if status == 200 else None
    return {'id': job_id, 'name': item['name'], 'description': item['description'], 'body': item.get('body'), 'height': item.get('height'),
            'role': item.get('role'), 'build': item.get('build'), 'weapon': item.get('weapon'), 'group': group, 'source': 'ai', 'dim': '3d', 'files': [], 'change': None, 'queued': True,
            'startedAt': now + index, 'launch': {'title': f"Design {item['name']}", 'systemPrompt': system, 'content': content}}


def running(job, now):
    return not job.get('queued') and not job.get('failed') and not job.get('done') and now - job.get('startedAt', 0) < TIMEOUT_MS


def one_pass():
    status, jobs, etag = call('GET', storage(JOBS))
    if status != 200 or not isinstance(jobs, list) or not jobs:
        return 'nothing queued'
    now = int(time.time() * 1000)
    out, changed, plans_done = [], False, []
    taken = {j.get('name') for j in jobs}
    st, assets, _ = call('GET', storage('assets.json'))
    taken |= set(((assets or {}).get('characters') or {}) if st == 200 else ())
    for job in jobs:
        active = not job.get('queued') and not job.get('failed') and not job.get('done')
        if active:
            st, plan, _ = call('GET', storage(f"character-plans/{job['id']}.json"))
            if st == 200 and isinstance((plan or {}).get('characters'), list):
                for i, item in enumerate(plan['characters']):
                    name, n = item['name'], 2
                    while name in taken:
                        name, n = f"{item['name']}-{n}", n + 1
                    taken.add(name)
                    out.append(planned_job(job, {**item, 'name': name}, i, now))
                plans_done.append(job['id'])
                changed = True
                continue
            st, draft, _ = call('GET', storage(f"character-drafts/{job['id']}.json"))
            if st == 200 and draft:
                job = {**job, 'done': True}
                changed = True
            elif now - job.get('startedAt', 0) >= TIMEOUT_MS:
                job = {**job, 'failed': True}
                changed = True
        out.append(job)
    # Start the oldest queued jobs (a planned cast in its planned order).
    busy = sum(1 for j in out if running(j, now))
    for job in sorted((j for j in out if j.get('queued')), key=lambda j: j.get('startedAt', 0)):
        if busy >= MAX_RUNNING:
            break
        launch = job.get('launch') or {}
        if not launch.get('content') and job.get('dim') == '3d' and job.get('source', 'ai') == 'ai' and job.get('description'):
            # Queued by an older version of the app: build its request here.
            built = planned_job({'id': job['id'], 'description': job.get('group') or '', 'launch': launch},
                                {k: job.get(k) for k in ('name', 'description', 'body', 'height', 'role', 'build', 'weapon')}, 0, now)
            launch = {**built['launch'], 'content': built['launch']['content'].replace(f"--job {built['id']}", f"--job {job['id']}")}
            job['launch'] = launch
        if not launch.get('systemPrompt') or not launch.get('content'):
            job.update(queued=False, failed=True)
            changed = True
            continue
        st, res, _ = call('POST', '/api/app-chats/start', {
            'scope': f"design:{job['id']}", 'owner_visible': False, 'title': launch.get('title') or f"Design {job['name']}",
            'system_prompt': launch['systemPrompt'], **({'model': m} if (m := launch.get('model') or creative_model()) else {}), 'content': launch['content'], 'timezone': 'UTC'})
        if st in (200, 201, 202):
            job.update(queued=False, startedAt=now, chatId=(res or {}).get('chat_id'))
            busy += 1
        else:
            job.update(queued=False, failed=True, error=f'start failed ({st})')
        changed = True
    if not changed:
        return 'no change'
    st, _, _ = call('PUT', storage(JOBS), json.dumps(out).encode(), {'If-Match': etag} if etag else None)
    if st == 412:
        return 'retry'  # the app changed the queue meanwhile; the next pass redoes this (starting is idempotent)
    for job_id in plans_done:
        call('DELETE', storage(f'character-plans/{job_id}.json'))
    return f'saved ({st}); running {busy}'


def main():
    for _ in range(3):
        result = one_pass()
        if result != 'retry':
            print(result)
            return
    print('gave up after conflicts; the next run retries')


if __name__ == '__main__':
    sys.exit(main())
