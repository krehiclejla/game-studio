"""The request board: wishes collaborators write in a game's Project.

requests.md in the project is the board itself, so anyone invited can add a
wish with the ordinary file editor:

    - [ ] Add a double jump (Amra)

The box says where a wish stands: [ ] new, [~] the owner asked the game's AI
to do it, [x] done, [-] declined. A plain "- wish" line counts as new.

Every sync (each minute, and after the game's AI changes the project):
1. applies the owner's decisions from Game Studio (storage
   requests/<gameId>/<key>.json, one small file per decision so the studio and
   this job never write the same file) to the matching new lines;
2. publishes the board to the studio as requests/<gameId>.json;
3. tells the owner about wishes that were not on the board before.
"""
import hashlib
import json
import re

FILE = 'requests.md'
TEMPLATE = """# Requests

Wishes for this game. Write one per line, starting with "- [ ]", and put your
name in brackets at the end so everyone knows who asked:

- [ ] Example: make the first level a little easier (Amra)

The owner sees new wishes in Game Studio and can ask the game's AI to make
them. The box shows where each one stands: [ ] new, [~] the AI is on it,
[x] done, [-] not this time.

"""
LINE = re.compile(r'^(\s*[-*]\s+)(?:\[([ ~xX-])\]\s+)?(.*\S)\s*$')
WHO = re.compile(r'\s*\(([^()]{1,40})\)$')
STATUS = {' ': 'new', '~': 'asked', 'x': 'done', 'X': 'done', '-': 'declined'}
MARK = {'asked': '~', 'declined': '-'}


def key_of(text):
    return hashlib.sha1(' '.join(text.lower().split()).encode()).hexdigest()[:12]


def parse(source):
    """Wishes in file order: [(line index, item)]. The template's example is not a wish."""
    found = []
    for index, line in enumerate(source.splitlines()):
        match = LINE.match(line)
        if not match:
            continue
        body = match.group(3)
        if body.lower().startswith('example:'):
            continue
        who = WHO.search(body)
        text = body[:who.start()].strip() if who else body
        if not text:
            continue
        found.append((index, {'key': key_of(text), 'text': text, 'who': who.group(1).strip() if who else None,
                              'status': STATUS[match.group(2) or ' ']}))
    return found


def apply_decisions(source, decisions):
    """Mark the new wishes the owner decided on; later states (done, declined) are left alone."""
    lines = source.splitlines(keepends=True)
    for index, item in parse(source):
        decision = decisions.get(item['key'])
        if item['status'] != 'new' or decision not in MARK:
            continue
        bare = lines[index].rstrip('\r\n')
        match = LINE.match(bare)
        lines[index] = f"{match.group(1)}[{MARK[decision]}] {match.group(3)}{lines[index][len(bare):]}"
    return ''.join(lines)


def update(root, store, game_name, notify):
    """Run the board for one game. store(get|put|list|delete, path, data) talks to studio storage.

    Returns True when requests.md changed (the caller commits the project)."""
    path = root / FILE
    changed = False
    if not path.exists():
        path.write_text(TEMPLATE)
        changed = True
    source = path.read_text()

    decisions = {}
    for name in store('list', 'decisions') or []:
        record = store('get', f'decisions/{name}')
        if isinstance(record, dict) and record.get('status'):
            decisions[name[:-5]] = record['status']
    if decisions:
        updated = apply_decisions(source, decisions)
        if updated != source:
            path.write_text(updated)
            source, changed = updated, True
        # Every decision is spent now, including ones about wishes no longer in the file.
        for key in decisions:
            store('delete', f'decisions/{key}.json')

    items = [item for _, item in parse(source)]
    board = store('get', 'board') or {}
    if board.get('items') != items:
        known = {item['key'] for item in board.get('items') or []}
        fresh = [item for item in items if item['status'] == 'new' and item['key'] not in known]
        store('put', 'board', {'items': items})
        # The very first look at a board is not news; later new lines are.
        if fresh and 'items' in board:
            first = fresh[0]
            who = first['who'] or 'Someone'
            more = f' (+{len(fresh) - 1} more)' if len(fresh) > 1 else ''
            notify(f'New wish for {game_name}', f'{who}: {first["text"]}{more}'[:300])
    return changed
