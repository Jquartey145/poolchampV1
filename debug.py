"""
debug_espn_roster.py
--------------------
Run from project root:
    python debug_espn_roster.py

Now that we know endpoint 1 works (flat athletes list), this script:
- Confirms the fixed roster parsing
- Tests gamelog with season=2025, season=2026, and no season param
- Dumps the full seasonTypes structure so we can verify label names
"""

import requests
import json

TEAM_ID    = 150   # Duke
SEASON     = 2025
SITE_BASE  = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
WEB_BASE   = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/mens-college-basketball"

def get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        print(f"  {r.status_code}  {r.url}")
        if r.status_code == 200:
            return r.json()
        else:
            print(f"  body: {r.text[:200]}")
    except Exception as e:
        print(f"  ERR: {e}")
    return None


# ── 1. Confirm fixed roster parsing ──────────────────────────────────────────
print("\n" + "="*60)
print("1. Roster — flat list parsing (fixed)")
print("="*60)
data = get(f"{SITE_BASE}/teams/{TEAM_ID}/roster")
athletes = []
if data:
    raw_athletes = data.get("athletes", [])
    print(f"  athletes list length: {len(raw_athletes)}")
    for a in raw_athletes:
        aid      = str(a.get("id", ""))
        name     = a.get("displayName", a.get("fullName", ""))
        position = a.get("position", {}).get("abbreviation", "")
        athletes.append({"athlete_id": aid, "name": name, "position": position})
        print(f"  id={aid:<10} {name:<30} pos={position}")


# ── 2. Test gamelog with multiple season values ───────────────────────────────
if not athletes:
    print("No athletes found, can't test gamelog")
else:
    a    = athletes[0]
    aid  = a["athlete_id"]
    name = a["name"]
    print(f"\n{'='*60}")
    print(f"2. Gamelog for {name} (id={aid})")
    print("="*60)

    for season_param in [2025, 2026, None]:
        label = f"season={season_param}" if season_param else "no season param"
        print(f"\n  --- {label} ---")
        params = {"season": season_param} if season_param else None
        d = get(f"{WEB_BASE}/athletes/{aid}/gamelog", params)
        if not d:
            continue

        top_keys = list(d.keys())
        print(f"  top-level keys: {top_keys}")

        season_types = d.get("seasonTypes", [])
        print(f"  seasonTypes count: {len(season_types)}")

        for st in season_types:
            st_id   = st.get("type", {}).get("id")
            st_name = st.get("type", {}).get("name", "")
            cats    = st.get("categories", [])
            # Try all possible label field names
            labels  = [c.get("text") or c.get("abbreviation") or c.get("name", "") for c in cats]
            events  = st.get("events", [])
            print(f"\n    seasonType id={st_id!r} ({st_name})")
            print(f"    labels ({len(labels)}): {labels}")
            print(f"    events: {len(events)}")
            if events:
                print(f"    events[0] keys: {list(events[0].keys())}")
                print(f"    events[0].stats: {events[0].get('stats', [])}")
                print(f"    events[0].opponent: {events[0].get('opponent', {}).get('displayName', 'N/A')}")
                print(f"    events[0].result: {events[0].get('result', 'N/A')}")


import requests
import json

TEAM_ID    = 150   # Duke
SEASON     = 2025
SITE_BASE  = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
WEB_BASE   = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/mens-college-basketball"
CORE_BASE  = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball"

def get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        print(f"  {r.status_code}  {r.url}")
        if r.status_code == 200:
            return r.json()
        else:
            print(f"  body: {r.text[:300]}")
    except Exception as e:
        print(f"  ERR: {e}")
    return None


def dump_keys(data, indent=4):
    """Recursively show structure up to depth 3."""
    def _walk(obj, depth=0):
        pad = " " * (indent * depth)
        if isinstance(obj, dict):
            for k, v in list(obj.items())[:8]:
                if isinstance(v, (dict, list)):
                    print(f"{pad}{k}: ({type(v).__name__}, len={len(v)})")
                    if depth < 2:
                        _walk(v, depth + 1)
                else:
                    print(f"{pad}{k}: {str(v)[:80]}")
        elif isinstance(obj, list) and obj:
            print(f"{pad}[0] →")
            _walk(obj[0], depth + 1)
    _walk(data)


# ── 1. site.api.espn.com roster endpoint ────────────────────────────────────
print("\n" + "="*60)
print("1. SITE API — /teams/{id}/roster")
print("="*60)
data = get(f"{SITE_BASE}/teams/{TEAM_ID}/roster")
if data:
    print("\nTop-level keys:", list(data.keys()))
    dump_keys(data)

    # Show raw 'athletes' structure if present
    if "athletes" in data:
        aths = data["athletes"]
        print(f"\n  athletes type: {type(aths).__name__}, len={len(aths)}")
        if aths:
            first = aths[0]
            print(f"  athletes[0] type: {type(first).__name__}")
            if isinstance(first, dict):
                print(f"  athletes[0] keys: {list(first.keys())}")
                # Look for nested items
                for k, v in first.items():
                    if isinstance(v, list) and v:
                        print(f"    {k}[0] keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0])}")


# ── 2. site.api.espn.com team detail with enable=roster ─────────────────────
print("\n" + "="*60)
print("2. SITE API — /teams/{id}?enable=roster,stats")
print("="*60)
data2 = get(f"{SITE_BASE}/teams/{TEAM_ID}", {"enable": "roster,stats"})
if data2:
    print("\nTop-level keys:", list(data2.keys()))
    team = data2.get("team", {})
    print("team keys:", list(team.keys()))
    if "athletes" in team:
        print(f"  team.athletes len={len(team['athletes'])}")
        dump_keys({"athletes": team["athletes"]})
    if "roster" in team:
        print(f"  team.roster: {str(team['roster'])[:200]}")


# ── 3. core API — athletes list for team ────────────────────────────────────
print("\n" + "="*60)
print("3. CORE API — /seasons/{year}/teams/{id}/athletes")
print("="*60)
data3 = get(f"{CORE_BASE}/seasons/{SEASON}/teams/{TEAM_ID}/athletes")
if data3:
    print("\nTop-level keys:", list(data3.keys()))
    dump_keys(data3)


# ── 4. core API — team roster (different path) ───────────────────────────────
print("\n" + "="*60)
print("4. CORE API — /seasons/{year}/teams/{id}/roster")
print("="*60)
data4 = get(f"{CORE_BASE}/seasons/{SEASON}/teams/{TEAM_ID}/roster")
if data4:
    print("\nTop-level keys:", list(data4.keys()))
    dump_keys(data4)


# ── 5. If we found any athlete, test the gamelog ─────────────────────────────
# Try to pull an athlete ID from whichever endpoint worked
athlete_id = None

for d in [data, data2, data3, data4]:
    if not d:
        continue
    # Walk looking for something with "id" that looks like an athlete
    raw = json.dumps(d)
    import re
    # Heuristic: find first "displayName" near an "id"
    names = re.findall(r'"displayName"\s*:\s*"([^"]+)"', raw)
    ids   = re.findall(r'"id"\s*:\s*"?(\d{5,})"?', raw)
    if ids:
        athlete_id = ids[0]
        name = names[0] if names else "unknown"
        print(f"\n  Found athlete candidate: id={athlete_id}, name={name}")
        break

if athlete_id:
    print("\n" + "="*60)
    print(f"5. WEB API — /athletes/{athlete_id}/gamelog?season={SEASON}")
    print("="*60)
    data5 = get(f"{WEB_BASE}/athletes/{athlete_id}/gamelog", {"season": SEASON})
    if data5:
        print("\nTop-level keys:", list(data5.keys()))
        dump_keys(data5)

        # Specifically dump seasonTypes structure
        for st in data5.get("seasonTypes", []):
            st_id   = st.get("type", {}).get("id")
            st_name = st.get("type", {}).get("name", "")
            cats    = st.get("categories", [])
            labels  = [c.get("text", c.get("abbreviation", c.get("name", ""))) for c in cats]
            events  = st.get("events", [])
            print(f"\n  seasonType id={st_id!r} name={st_name!r}")
            print(f"  categories/labels: {labels}")
            print(f"  events count: {len(events)}")
            if events:
                print(f"  events[0] keys: {list(events[0].keys())}")
                print(f"  events[0].stats: {events[0].get('stats', [])[:15]}")
else:
    print("\n⚠️  Could not find any athlete ID to test gamelog endpoint.")