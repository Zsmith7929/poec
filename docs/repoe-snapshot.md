# RePoE Snapshot Provenance

## Source

- **Mods URL:** https://repoe-fork.github.io/mods.min.json
  (gh-pages of https://github.com/repoe-fork/repoe-fork)
- **Base items URL:** https://repoe-fork.github.io/base_items.min.json
- **Fetch date:** 2026-07-18
- **Real fetch:** yes — both files downloaded successfully (22 MB mods, 2.8 MB base_items)

## Fetch Commands

```bash
# Fetch full mods
curl -fsSL "https://repoe-fork.github.io/mods.min.json" -o /tmp/repoe_mods_full.json

# Fetch base items
curl -fsSL "https://repoe-fork.github.io/base_items.min.json" -o /tmp/repoe_bases_full.json
```

## Reduction Approach

Kept only mods where:
1. `domain` in `{"item", "crafted"}`
2. `generation_type` in `{"prefix", "suffix"}`
3. At least one `spawn_weights` entry has `weight > 0` for a tag present on one of the three Phase-0 bases

Reduced from 39,292 mods to 375 mods (~255 KB).

### Phase-0 Base Items

| Base | Key | Tags |
|------|-----|------|
| Vaal Regalia | `Metadata/Items/Armours/BodyArmours/BodyInt17` | `int_armour, top_tier_base_item_type, body_armour, armour, default` |
| Titanium Spirit Shield | `Metadata/Items/Armours/Shields/ShieldInt16` | `int_armour, focus, top_tier_base_item_type, shield, armour, default` |
| Imperial Bow | `Metadata/Items/Weapons/TwoHandWeapons/Bows/Bow21` | `top_tier_base_item_type, bow, ranged, two_hand_weapon, twohand, weapon, default` |

### Schema Notes

The real RePoE `mods.min.json` uses:
- `groups` (list of strings) — not `group` (single string)
- `implicit_tags` — not `tags`

The `oracle/gamedata/schema.py` `RepoeMod` model maps `groups[0]` → `group` via a
validator, and uses `implicit_tags` as the `tags` field. See `schema.py` for details.

## Spot-Check Results

Results from `GameDataService.mod_pool(base, ilvl=86)` against vendored snapshot:

- Vaal Regalia ilvl 86: 62 prefix mods, 63 suffix mods (125 total)
- Titanium Spirit Shield ilvl 86: 107 prefix mods, 99 suffix mods (206 total)
- Imperial Bow ilvl 86: 65 prefix mods, 77 suffix mods (142 total)

Note: Counts are higher than displayed on poedb because the reduction keeps mods for
all combined base tags (int_armour, body_armour, bow, etc.) rather than a single base.
The ilvl gate and tag filtering in `mod_pool()` narrow results further at query time.

## Re-snapshot Runbook

Run the same `curl` commands above for the latest patch, then re-run
the reduction script from this document. Commit the new snapshots with
a message referencing the PoE patch version.

```python
# Re-run reduction (Python)
import json, os

all_mods = json.load(open('/tmp/repoe_mods_full.json'))
all_bases = json.load(open('/tmp/repoe_bases_full.json'))

target_names = {'Vaal Regalia', 'Titanium Spirit Shield', 'Imperial Bow'}
selected_bases = {k: v for k, v in all_bases.items() if v.get('name') in target_names}

item_tags = set()
for v in selected_bases.values():
    item_tags.update(v.get('tags', []))
item_tags.add('default')

selected_mods = {}
for mid, mod in all_mods.items():
    if mod.get('domain') not in {'item', 'crafted'}:
        continue
    if mod.get('generation_type') not in {'prefix', 'suffix'}:
        continue
    for sw in mod.get('spawn_weights', []):
        if sw.get('tag') in item_tags and sw.get('weight', 0) > 0:
            selected_mods[mid] = mod
            break

os.makedirs('snapshots/repoe', exist_ok=True)
json.dump(selected_mods, open('snapshots/repoe/mods.min.json', 'w'), separators=(',', ':'))
json.dump(selected_bases, open('snapshots/repoe/base_items.min.json', 'w'), separators=(',', ':'))
```
