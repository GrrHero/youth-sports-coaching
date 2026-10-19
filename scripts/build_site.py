#!/usr/bin/env python3
"""Build the kid-facing Goonies site data from weeks/.

    python3 scripts/build_site.py

Reads weeks/week-NN/ (same layout as build.py), merges hand-written kid
copy from data/kid_copy.json, and writes data/plan.json for the site.

Calendar Mondays (kid site):
  Week 1 → 2026-10-05  (source plan dated Oct 11; noted in plan.json)
  Week 2 → 2026-10-12
  Week 3 → 2026-10-19
  Week 4 → 2026-10-26  (picked up automatically when weeks/week-04 exists)

After editing weeks/ or kid_copy.json, rerun this script, then commit
data/plan.json with the site. New weeks appear on the calendar once
imported (scripts/import_plan.py) and this script is rerun.
"""
from __future__ import annotations
import json, re, sys, pathlib
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from build import load, LINK_RE  # noqa: E402

SPORT_EMOJI = {
    'Baseball': '⚾', 'Soccer': '⚽', 'Flag Football': '🏈',
    'Athleticism': '🏃', 'Multi-sport': '🏆', 'Play Day': '🎮', 'Rest': '😴',
}
CAL_MONDAY = {1: '2026-10-05', 2: '2026-10-12', 3: '2026-10-19', 4: '2026-10-26'}
WEEK_NOTE = {
    1: 'Plan dated Oct 11, 2026; shown as the week of Mon Oct 5 for the calendar.',
}
DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
SESS_DAY = {1: 'Mon', 2: 'Tue', 3: 'Thu', 4: 'Fri', 5: 'Sat'}

ACT_RE = re.compile(
    r'^## (Warm-up|Skill \d+|Skill [Ww]ork(?:[ ,][^:]*)?|Skill Work [A-Z]|Game|Finale|Cool-down)'
    r'(?:, (\w+))?: (.+?)(?: \(([^()]*)\))?\s*$'
)
HEAD_CUE = re.compile(r'\s*·\s*Cue:\s*\*\*(.+?)\*\*\s*$')


def yt_id(url: str):
    m = re.search(r'(?:v=|youtu\.be/|shorts/)([\w-]{11})', url)
    return m.group(1) if m else None


def slug(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def clean_cue(c: str) -> str:
    c = re.sub(r'^["“]|["”]$', '', (c or '').strip())
    c = re.sub(r'\*+', '', c)
    if '.' in c and len(c) > 28:
        c = c.split('.')[0]
    c = c.strip(' !"\'')
    return c[:36] if c else 'Go!'


def norm_sport(sp: str) -> str:
    if not sp:
        return 'Multi-sport'
    if sp.startswith('Athleticism') and 'Baseball' in sp:
        return 'Athleticism'
    if sp.startswith('Athleticism'):
        return 'Athleticism'
    if 'Mixed' in sp or 'Multi' in sp:
        return 'Multi-sport'
    for k in ('Baseball', 'Soccer', 'Flag Football', 'Athleticism'):
        if sp.startswith(k) or k in sp:
            return k
    return sp


def emoji_for(sp: str) -> str:
    sp = norm_sport(sp)
    return SPORT_EMOJI.get(sp, '⭐')


def load_kid_copy():
    p = ROOT / 'data' / 'kid_copy.json'
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def find_copy(kid: dict, week: int, session: int, name: str):
    """Match kid_copy keys like '3/1/Popcorn Ready' by prefix / substring."""
    name_clean = name.strip().strip('"')
    key_exact = f'{week}/{session}/{name_clean}'
    if key_exact in kid:
        return kid[key_exact]
    # try each key with same week/session whose name is in drill name or vice versa
    prefix = f'{week}/{session}/'
    candidates = []
    for k, v in kid.items():
        if not k.startswith(prefix):
            continue
        label = k[len(prefix):]
        if label.lower() in name_clean.lower() or name_clean.lower() in label.lower():
            candidates.append((len(label), v))
        else:
            # first significant word
            lw = re.sub(r'[^a-z0-9]+', ' ', label.lower()).split()
            nw = re.sub(r'[^a-z0-9]+', ' ', name_clean.lower()).split()
            if lw and nw and lw[0] == nw[0]:
                candidates.append((len(label), v))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    return None


def parse_activities(lines):
    acts = []
    for i, ln in enumerate(lines):
        if not ln.startswith('## '):
            continue
        hc = HEAD_CUE.search(ln)
        clean = HEAD_CUE.sub('', ln)
        am = ACT_RE.match(clean)
        if not am:
            continue
        typ = am.group(1)
        who = (am.group(2) or '')
        if re.search(r'5yo', typ, re.I) or who.lower() == '5yo':
            continue
        name = am.group(3).strip().strip('"').replace('"', '').strip()
        # fix "Route Cards + Laces Grip" style
        name = re.sub(r'\s*\+\s*', ' + ', name)
        acts.append({
            'i': i, 'type': typ, 'name': name,
            'time': am.group(4) or '', 'cue': hc.group(1) if hc else '',
        })
    return acts


def cue_from_body(lines, start, fallback=''):
    if fallback:
        return clean_cue(fallback)
    for j in range(start + 1, min(start + 25, len(lines))):
        if lines[j].startswith('## '):
            break
        cm = re.match(r'^(?:- )?\*\*Cue(?: words)?:\*\*\s*(.+)$', lines[j])
        if cm:
            raw = cm.group(1)
            qm = re.findall(r'["“]([^"”]+)["”]', raw)
            return clean_cue(qm[0] if qm else raw)
    return 'Go!'


def videos_for(urls, week_videos):
    out, seen = [], set()
    for url in urls:
        vid = yt_id(url)
        if not vid or vid in seen:
            continue
        seen.add(vid)
        meta = week_videos.get(url, {})
        title = meta.get('title') or 'Watch this!'
        # drop "for you" coach framing from title display — keep as-is from index
        out.append({
            'id': vid,
            'title': title,
            'url': f'https://www.youtube.com/watch?v={vid}',
            'thumb': f'https://img.youtube.com/vi/{vid}/hqdefault.jpg',
        })
    return out


def play_day(week_num, date_str):
    return {
        'day': 'Wed', 'date': date_str, 'kind': 'play', 'session': None,
        'sport': 'Play Day', 'name': '10-Minute Play Day',
        'emoji': '🎮', 'time': '10 min',
        'drills': [{
            'id': f'w{week_num}-play',
            'name': "Kid's Choice Play",
            'cue': 'Play!',
            'sport': 'Play Day',
            'emoji': '🎮',
            'kind': 'Play',
            'time': '10 min',
            'steps': [
                'Pick a favorite game from this week.',
                'No new lessons — just play!',
                'Invite Dad to play too.',
                'Stop while it is still fun.',
            ],
            'fun': 'You are the coach today. You pick the game!',
            'level_up': 'Teach Dad a new rule for your game.',
            'videos': [],
        }],
    }


def rest_day(week_num, date_str):
    return {
        'day': 'Sun', 'date': date_str, 'kind': 'rest', 'session': None,
        'sport': 'Rest', 'name': 'Rest Day',
        'emoji': '😴', 'time': '',
        'drills': [{
            'id': f'w{week_num}-rest',
            'name': 'Rest & Recover',
            'cue': 'Rest',
            'sport': 'Rest',
            'emoji': '😴',
            'kind': 'Rest',
            'time': '',
            'steps': [
                'No practice today.',
                'Play outside for fun if you want.',
                'Drink water and stretch if you feel sore.',
                'Get ready for next week!',
            ],
            'fun': 'Goonies rest so they can never say die tomorrow!',
            'level_up': 'Tell Dad your favorite drill from this week.',
            'videos': [],
        }],
    }


def week1_stations(week_videos, kid):
    """Backyard Olympics stations for W1 S5."""
    names = [
        'Flamingo Stand', 'Sprint Race', 'Castle Knockdown',
        'Catch Ladder', 'Dribble Gates', 'Flag Pull Challenge',
    ]
    sports = ['Athleticism', 'Athleticism', 'Baseball', 'Baseball', 'Soccer', 'Flag Football']
    drills = []
    for name, sport in zip(names, sports):
        cp = find_copy(kid, 1, 5, name) or {}
        drills.append({
            'id': f'w1s5-{slug(name)}',
            'name': name,
            'cue': cp.get('cue', 'Go!'),
            'sport': sport,
            'emoji': emoji_for(sport),
            'kind': 'Station',
            'time': '3-4 min',
            'steps': cp.get('steps', [f'Do {name}!']),
            'fun': cp.get('fun', 'Cheer loud!'),
            'level_up': cp.get('level_up', 'Beat your best!'),
            'videos': [],
        })
    return drills


def build_session_drills(w, s, kid):
    sf = ROOT / s['file']
    lines = sf.read_text().splitlines()

    if w['num'] == 1 and s['num'] == 5:
        return week1_stations(w['videos'], kid)

    built_by_name = {a['name'].strip('"'): a for a in s['acts']}
    drills = []
    for ar in parse_activities(lines):
        ba = built_by_name.get(ar['name'])
        if not ba:
            for nm, a in built_by_name.items():
                if ar['name'] in nm or nm in ar['name'] or slug(ar['name'])[:12] == slug(nm)[:12]:
                    ba = a
                    break

        cp = find_copy(kid, w['num'], s['num'], ar['name']) or {}
        cue = cp.get('cue') or (ba['cues'][0] if ba and ba['cues'] else '') or ar['cue']
        cue = cue_from_body(lines, ar['i'], cue)

        sport = norm_sport((ba['sport'] if ba else None) or s['sport'])
        urls = list(ba['videos']) if ba else []
        for j in range(ar['i'] + 1, min(ar['i'] + 70, len(lines))):
            if lines[j].startswith('## '):
                break
            for m in LINK_RE.finditer(lines[j]):
                if m.group(2) not in urls:
                    urls.append(m.group(2))

        name = ar['name']
        # Prefer a cleaner display name from kid_copy key match
        drills.append({
            'id': f'w{w["num"]}s{s["num"]}-{slug(name)}',
            'name': name,
            'cue': clean_cue(cue) if not cp.get('cue') else cp['cue'],
            'sport': sport,
            'emoji': emoji_for(sport),
            'kind': (ba['kind'] if ba else 'Skill Work'),
            'time': ar['time'] or (ba['time'] if ba else ''),
            'steps': cp.get('steps') or [f'Do {name} with Dad.', f'Say "{clean_cue(cue)}!"', 'Try your best!', 'High five!'],
            'fun': cp.get('fun') or 'Make it silly and cheer loud!',
            'level_up': cp.get('level_up') or f'Do it 3 times saying "{clean_cue(cue)}"!',
            'videos': videos_for(urls, w['videos']),
        })
    return drills


def build():
    kid = load_kid_copy()
    weeks_data = load()
    out = {
        'team': 'THE GOONIES',
        'tagline': 'Goonies never say die!',
        'league': 'Cedar Park Youth League · 8U Coach Pitch',
        'generated_by': 'scripts/build_site.py',
        'weeks': [],
    }

    for w in weeks_data:
        monday = CAL_MONDAY.get(w['num'])
        if not monday and w.get('week_of'):
            # try parse "Oct 26, 2026" as a Monday hint
            try:
                from datetime import datetime
                d = datetime.strptime(w['week_of'].split('·')[0].strip(), '%b %d, %Y').date()
                monday = (d - timedelta(days=d.weekday())).isoformat()
            except Exception:
                monday = ''
        week_obj = {
            'num': w['num'],
            'title': re.sub(r'^Week \d+\s*[—:\-]*\s*', '', w['title']).strip(),
            'week_of': w['week_of'],
            'monday': monday,
            'note': WEEK_NOTE.get(w['num'], ''),
            'days': [],
        }

        by_day = {}
        for s in w['sessions']:
            day = SESS_DAY[s['num']]
            drills = build_session_drills(w, s, kid)
            sp = s['sport']
            by_day[day] = {
                'day': day, 'kind': 'session', 'session': s['num'],
                'sport': sp, 'name': s['name'].strip('"'),
                'emoji': emoji_for(sp), 'time': s['time'],
                'drills': drills,
            }

        base = date.fromisoformat(monday) if monday else None
        for idx, dname in enumerate(DAY_NAMES):
            date_str = (base + timedelta(days=idx)).isoformat() if base else ''
            if dname == 'Wed':
                week_obj['days'].append(play_day(w['num'], date_str))
            elif dname == 'Sun':
                week_obj['days'].append(rest_day(w['num'], date_str))
            elif dname in by_day:
                obj = by_day[dname]
                obj['date'] = date_str
                week_obj['days'].append(obj)
            else:
                week_obj['days'].append({
                    'day': dname, 'date': date_str, 'kind': 'empty',
                    'session': None, 'sport': '', 'name': 'TBD',
                    'emoji': '📝', 'time': '', 'drills': [],
                })

        out['weeks'].append(week_obj)

    out_path = ROOT / 'data' / 'plan.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n')

    n_drills = sum(len(d['drills']) for w in out['weeks'] for d in w['days'])
    print(f'Wrote {out_path.relative_to(ROOT)} — {len(out["weeks"])} weeks, {n_drills} day-cards/drills')
    for w in out['weeks']:
        sd = sum(len(d['drills']) for d in w['days'] if d['kind'] == 'session')
        missing = [d['name'] for day in w['days'] if day['kind'] == 'session'
                   for d in day['drills'] if d['steps'] and d['steps'][0].startswith('Do ') and 'with Dad' in d['steps'][0]]
        print(f'  Week {w["num"]} (Mon {w["monday"]}): {sd} session drills'
              + (f'  ⚠ fallback steps: {missing}' if missing else ''))
    return out


if __name__ == '__main__':
    build()
