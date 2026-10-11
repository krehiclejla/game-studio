#!/usr/bin/env python3
"""Free CC0 3D characters for Game Studio: KayKit (Kay Lousberg) and Quaternius.

  python3 library.py list [WORDS...]          characters whose names match (all when no words)
  python3 library.py get NAME OUT.glb [--keep-items] [--all-anims]
      Download its pack once, convert it, remove held props (weapons, shields, mugs) unless
      --keep-items, and rename its moves to the studio's names (idle, walk, run, jump, attack,
      hurt, die, and extras such as dodge, block, cheer, cast, shoot). People come out 1.8 m tall
      in real metres, so gear built to real size fits. Prints its parts, moves
      and credit, plus "source": the original pack file, whose removed props (a KayKit 1H_Axe,
      Round_Shield...) blender_edit.py borrow() can put back in the right hand. Then edit it with
      blender_edit.py, check it and save it.
  python3 library.py items [PACK]            KayKit's separate weapons and props (files to equip)

Every entry is CC0 (public domain): free to use, change and ship; credit is kind but optional.
KayKit characters are chibi adventurers and skeletons split into parts (head, hat, cape, body,
arms, legs) on one shared skeleton, so parts swap between them. Quaternius characters are one
mesh with named colour materials (Skin, Shirt, Pants, Hat...), and their skin is black by design
(a silhouette style): recolour it for normal skin.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = Path.home() / '.cache' / 'game-studio' / 'library'
UA = {'User-Agent': 'Mozilla/5.0 (MobiusGameStudio)'}

PACKS = {
    'kaykit-adventurers': {
        'url': 'https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0/archive/refs/heads/main.zip',
        'credit': 'KayKit Adventurers by Kay Lousberg (CC0)', 'files': '**/Characters/gltf/{name}.glb', 'items': '**/Assets/gltf/*.gltf',
        'characters': {'Barbarian': 'bearded barbarian in a bear-skin hat', 'Knight': 'armoured knight with a helmet and cape',
                       'Mage': 'mage in a pointed hat and robe', 'Rogue': 'rogue in a cape', 'Rogue_Hooded': 'hooded rogue'}},
    'kaykit-skeletons': {
        'url': 'https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Skeletons-1.0/archive/refs/heads/main.zip',
        'credit': 'KayKit Skeletons by Kay Lousberg (CC0)', 'files': '**/Characters/gltf/{name}.glb', 'items': '**/Assets/gltf/*.gltf',
        'characters': {'Skeleton_Warrior': 'skeleton warrior with a helmet', 'Skeleton_Mage': 'skeleton mage in a hat',
                       'Skeleton_Rogue': 'hooded skeleton rogue', 'Skeleton_Minion': 'cloaked skeleton minion'}},
    'quaternius-characters': {
        'url': 'https://opengameart.org/sites/default/files/ultimate_animated_character_pack_by_quaternius.zip',
        'credit': 'Ultimate Animated Character Pack by Quaternius (CC0)', 'files': '**/Blends/{name}.blend',
        'characters': {n: n.replace('_', ' ').lower() for n in (
            'BaseCharacter BlueSoldier_Female BlueSoldier_Male Casual2_Female Casual2_Male Casual3_Female Casual3_Male '
            'Casual_Bald Casual_Female Casual_Male Chef_Female Chef_Male Cowboy_Female Cowboy_Male Doctor_Female_Old '
            'Doctor_Female_Young Doctor_Male_Old Doctor_Male_Young Elf Goblin_Female Goblin_Male Kimono_Female Kimono_Male '
            'Knight_Golden_Female Knight_Golden_Male Knight_Male Ninja_Female Ninja_Male Ninja_Sand Ninja_Sand_Female '
            'OldClassy_Female OldClassy_Male Pirate_Female Pirate_Male Soldier_Female Soldier_Male Suit_Female Suit_Male '
            'Viking_Female Viking_Male Witch Wizard Worker_Female Worker_Male Zombie_Female Zombie_Male').split()},
        'animals': {'Cow': 'cow standing on two legs', 'Pug': 'pug dog standing on two legs'}},
    'quaternius-rpg': {
        'url': 'https://opengameart.org/sites/default/files/rpg_characters_-_nov_2020.zip',
        'credit': 'RPG Characters by Quaternius (CC0)', 'files': '**/{name}.blend',
        'characters': {'Cleric': 'cleric', 'Monk': 'monk', 'Ranger': 'ranger', 'Rogue': 'rogue', 'Warrior': 'warrior', 'Wizard': 'wizard'}},
    'quaternius-monsters': {
        'url': 'https://opengameart.org/sites/default/files/Animated%20Monster%20Pack%20by%20%40Quaternius.zip',
        'credit': 'Animated Monster Pack by Quaternius (CC0)', 'files': '**/{name}.blend',
        'characters': {'Skeleton': 'cartoon skeleton'},
        'creatures': {'Bat': ('flying bat', 'wings'), 'Dragon': ('small dragon', 'fourlegs'), 'Slime': ('slime blob', 'any')}},
}

# The studio's move names (games rely on these), first match wins.
MOVES = [
    ('idle', ['Idle']), ('walk', ['Walking_A', 'Walk']), ('run', ['Running_A', 'Run']),
    ('jump', ['Jump_Full_Short', 'Jump']), ('fall', ['Jump_Idle']),
    ('attack', ['1H_Melee_Attack_Chop', 'SwordSlash', 'Sword', 'Attack', 'Punch']),
    ('attack2', ['1H_Melee_Attack_Slice_Diagonal', 'Punch']), ('attack3', ['1H_Melee_Attack_Stab', 'Kick']),
    ('heavy', ['2H_Melee_Attack_Chop']), ('punch', ['Unarmed_Melee_Attack_Punch_A', 'Punch']),
    ('hurt', ['Hit_A', 'RecieveHit', 'HitReact', 'Hit']), ('die', ['Death_A', 'Death']),
    ('dodge', ['Dodge_Forward', 'Roll']), ('block', ['Block']), ('cheer', ['Cheer', 'Victory']),
    ('cast', ['Spellcast_Shoot', 'Spell']), ('shoot', ['1H_Ranged_Shoot', 'Shoot_OneHanded', 'Bow_Shoot']),
    ('throw', ['Throw']), ('interact', ['Interact', 'PickUp']), ('fly', ['Flying', 'Fly']),
]
PROPS = ('Axe', 'Sword', 'Shield', 'Mug', 'Crossbow', 'Knife', 'Throwable', 'Wand', 'Staff', 'Spellbook',
         'Icosphere', 'Blade', 'Arrow', 'Quiver', 'Bow', 'Dagger')


def slug(pack, name):
    s = name.lower().replace('_', '-')
    return s if pack.startswith('kaykit') or pack == 'quaternius-characters' else f'{s}-{pack.split("-")[1]}' if s in ('rogue', 'wizard', 'skeleton') else s


def catalogue():
    out = []
    for pack, p in PACKS.items():
        for group, body in (('characters', 'humanoid'), ('animals', 'humanoid'), ('creatures', None)):
            for name, desc in p.get(group, {}).items():
                d, b = (desc if isinstance(desc, tuple) else (desc, body))
                out.append({'name': slug(pack, name), 'pack': pack, 'file': name, 'about': d, 'body': b, 'credit': p['credit']})
    return out


def fetch(pack):
    """Download and unpack a pack once (cached on this machine)."""
    root = CACHE / pack
    if (root / '.done').exists():
        return root
    root.mkdir(parents=True, exist_ok=True)
    archive = root / 'pack.zip'
    req = urllib.request.Request(PACKS[pack]['url'], headers=UA)
    with urllib.request.urlopen(req, timeout=600) as res, open(archive, 'wb') as f:
        shutil.copyfileobj(res, f)
    with zipfile.ZipFile(archive) as z:
        z.extractall(root)
    archive.unlink()
    (root / '.done').write_text('ok')
    return root


def find(entry):
    root = fetch(entry['pack'])
    hits = sorted(root.glob(PACKS[entry['pack']]['files'].format(name=entry['file'])))
    if not hits:
        sys.exit(f'{entry["name"]}: its file is missing from the {entry["pack"]} download.')
    return hits[0]


BLENDER_SCRIPT = r'''
import bpy, sys, json
a = json.loads(sys.argv[sys.argv.index('--') + 1])
if a['src'].endswith(('.glb', '.gltf')):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=a['src'])
removed = []
if not a['keep_items']:
    for o in list(bpy.data.objects):
        if o.type == 'MESH' and any(p.lower() in o.name.lower() for p in a['props']):
            removed.append(o.name); bpy.data.objects.remove(o, do_unlink=True)
for m in bpy.data.materials:
    # Plain-colour materials from older .blend files use legacy nodes the glTF exporter
    # ignores (they come out grey), so rebuild those as one fresh node with the same colour.
    # Textured materials (KayKit) are left alone apart from the matte finish.
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next((x for x in nt.nodes if x.type == 'BSDF_PRINCIPLED'), None)
    if not any(x.type == 'TEX_IMAGE' for x in nt.nodes):
        col = tuple(bsdf.inputs['Base Color'].default_value) if bsdf else tuple(m.diffuse_color)
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.inputs['Base Color'].default_value = col
        nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    if bsdf:                                      # imports come in glossy; games want matte
        bsdf.inputs['Metallic'].default_value = 0.0
        bsdf.inputs['Roughness'].default_value = max(0.7, bsdf.inputs['Roughness'].default_value)
names = {x.name.split('|')[-1]: x for x in bpy.data.actions}
kept = {}                                         # studio name -> clip
for new, olds in a['moves']:
    old = next((o for o in olds if o in names), None)
    if old:
        kept[new] = names[old]
if not a['all_anims']:
    keep = {id(x) for x in kept.values()}
    for x in list(bpy.data.actions):
        if id(x) not in keep:
            bpy.data.actions.remove(x)
used = set()
for new, act in kept.items():                     # one clip can serve two names (Punch: attack2 and punch)
    if id(act) in used:
        act = act.copy()
    used.add(id(act))
    act.name = new
def _fcurves(act):
    try:
        return list(act.fcurves)                  # older Blender
    except AttributeError:
        return [fc for layer in act.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]

rig = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if rig and a['height']:
    # Real metres, so gear built to real size (shapes.py, the hand axe) fits: scale the whole
    # character to HEIGHT, bake it in, and scale the moves' bone travel to match.
    for o in bpy.data.objects:
        if o.animation_data:
            o.animation_data.action = None
    rig.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    kids = [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == rig]
    zs = [(o.matrix_world @ v.co).z for o in kids for v in o.data.vertices]
    k = a['height'] / max(max(zs) - min(zs), 1e-6)
    # Scale the skeleton and every skinned part in the skeleton's own space (no operators:
    # they refuse to run in some saved files).
    from mathutils import Matrix
    S = Matrix.Scale(k, 4)
    rig.data.transform(S)
    for o in kids:
        L = o.matrix_parent_inverse @ o.matrix_basis
        o.data.transform(L.inverted() @ S @ L)
    for act in bpy.data.actions:
        for fc in _fcurves(act):
            if fc.data_path.endswith('location'):
                for kp in fc.keyframe_points:
                    kp.co[1] *= k; kp.handle_left[1] *= k; kp.handle_right[1] *= k
    rig.data.pose_position = 'POSE'
for o in bpy.data.objects:                        # nothing left playing at export
    if o.animation_data:
        o.animation_data.action = None
parts = sorted(o.name for o in bpy.data.objects if o.type == 'MESH')
mats = sorted({s.material.name for o in bpy.data.objects if o.type == 'MESH' for s in o.material_slots if s.material})
bpy.ops.export_scene.gltf(filepath=a['out'], export_format='GLB', export_animations=True, export_animation_mode='ACTIONS')
print('LIBRARY_RESULT ' + json.dumps({'parts': parts, 'materials': mats, 'removed': removed,
      'moves': sorted(x.name for x in bpy.data.actions), 'bones': [b.name for b in rig.data.bones if b.use_deform] if rig else []}))
'''


def blender_run(script, blend=None, args=None):
    sys.path.insert(0, str(HERE))
    from detailed import ensure_blender
    exe = ensure_blender()
    if not exe:
        sys.exit('Blender could not be set up on this machine.')
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, dir=os.environ.get('TMPDIR')) as f:
        f.write(script)
    cmd = [str(exe), '-b'] + ([str(blend)] if blend else []) + ['--python', f.name, '--', json.dumps(args or {})]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    os.unlink(f.name)
    return proc


def get(name, out, keep_items=False, all_anims=False):
    entries = catalogue()
    entry = next((e for e in entries if e['name'] == name.lower() or e['file'].lower() == name.lower()), None)
    if not entry:
        close = [e['name'] for e in entries if name.lower().split('-')[0] in e['name']]
        sys.exit(f'No library character "{name}".' + (f' Did you mean: {", ".join(close[:8])}?' if close else ' See: library.py list'))
    src = find(entry)
    args = {'src': str(src), 'out': str(Path(out).resolve()), 'keep_items': keep_items, 'all_anims': all_anims,
            'height': 1.8 if entry['body'] == 'humanoid' else None,
            'props': list(PROPS), 'moves': MOVES}
    proc = blender_run(BLENDER_SCRIPT, blend=src if src.suffix == '.blend' else None, args=args)
    line = next((l for l in proc.stdout.splitlines() if l.startswith('LIBRARY_RESULT ')), None)
    if proc.returncode or not line or not Path(out).exists():
        sys.exit('Converting it failed: ' + (proc.stderr or proc.stdout)[-1200:])
    info = json.loads(line[len('LIBRARY_RESULT '):])
    basics = {'idle', 'walk', 'run', 'jump', 'hurt', 'die'}
    missing = sorted(basics - set(info['moves'])) if entry['body'] == 'humanoid' else []
    print(json.dumps({'ok': True, 'out': str(out), 'name': entry['name'], 'about': entry['about'], 'body': entry['body'] or 'any',
                      'credit': entry['credit'], 'source': str(src), **info, 'missing_basics': missing,
                      'next': 'Render it, then edit it with blender_edit.py (colours, build, parts, gear) if the request needs changes.'
                              + (f' Add missing moves with model_tool.py add-anims ({", ".join(missing)}).' if missing else '')}, indent=1))


def items(pack=None):
    out = []
    for p, spec in PACKS.items():
        if 'items' not in spec or (pack and pack != p):
            continue
        root = fetch(p)
        out += [{'pack': p, 'item': f.stem, 'file': str(f)} for f in sorted(root.glob(spec['items']))]
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('action', choices=['list', 'get', 'items'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--keep-items', action='store_true')
    ap.add_argument('--all-anims', action='store_true')
    a = ap.parse_args()
    if a.action == 'list':
        words = [w.lower() for w in a.args]
        rows = [e for e in catalogue() if all(w in (e['name'] + ' ' + e['about'] + ' ' + e['pack']) for w in words)]
        print(json.dumps([{k: e[k] for k in ('name', 'about', 'body', 'pack')} for e in rows], indent=1))
    elif a.action == 'get':
        if len(a.args) != 2:
            sys.exit('usage: library.py get NAME OUT.glb')
        get(a.args[0], a.args[1], a.keep_items, a.all_anims)
    else:
        items(a.args[0] if a.args else None)


if __name__ == '__main__':
    main()
