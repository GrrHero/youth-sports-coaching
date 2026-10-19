#!/usr/bin/env python3
"""Rebuild everything that is generated from the week folders.

    python3 scripts/build.py          # indexes + README schedule + site/
    python3 scripts/build.py --no-site

Reads weeks/week-NN/{README.md, session-N.md, group-coaching.md, week.json} and writes:
  indexes/cue-words.md, videos.md, drills.md, coaching-principles.md, field-coaching.md
  the schedule table inside README.md (between the SCHEDULE markers)
  site/  (plain HTML copy of every page; needs `pip install markdown`)

week.json (per week, all keys optional):
  week_of          "Oct 19, 2026"
  sessions         {"1": {"sport": "Baseball"}, ...}       sport label per session
  activity_sport   {"<session>/<activity name>": "Soccer"} per-activity override
  video_locations  {"<url>": [["<session>", "<activity name or ''>"]]} for videos
                   that are only listed in the week README
  principles       [{"section": "<README ## heading>"} | {"block": "<line prefix>"}]
                   text copied into indexes/coaching-principles.md
"""
import re, sys, json, pathlib, collections, html

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEEKS = ROOT / 'weeks'
IDX = ROOT / 'indexes'
SPORT_ORDER = ['Baseball', 'Soccer', 'Flag Football', 'Athleticism', 'Multi-sport']
TYPE_ORDER = ['Warm-up', 'Skill Work', 'Game', 'Station', 'Cool-down']
HEAD_CUE_RE = re.compile(r'\s*·\s*Cue:\s*\*\*(.+?)\*\*\s*$')
ACT_RE = re.compile(r'^## (Warm-up|Skill \d+|Skill [Ww]ork(?: [A-Z])?|Game|Finale|Cool-down)(?:, (\w+))?: (.+?)(?: \(([^()]*)\))?\s*$')
STATION_RE = re.compile(r'^\d+\. \*\*(.+?):\*\* (.*)$')
YT = r'https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^)\s]+'
LINK_RE = re.compile(r'\[((?:[^\[\]]|\[[^\]]*\])+)\]\((' + YT + r')\)')
VIDEO_LIST_HEADS = re.compile(r'(video list|verified video links|where the videos fit)', re.I)
QUOTE_RE = re.compile(r'["“]([^"”]+)["”]')


def slug(text):
    """GitHub-style heading anchor."""
    text = re.sub(r'<[^>]+>', '', text).strip().lower()
    text = re.sub(r'[^\w\- ]', '', text, flags=re.UNICODE)
    return text.replace(' ', '-')


def esc(s):
    return s.replace('|', '\\|')


def clean_cue(c):
    return re.sub(r'[.,;:]+$', '', c.strip()).strip()


def cue_key(c):
    return re.sub(r'[^\w ]', '', c.lower()).strip()


def cues_from(text):
    """Cue words from the text after a 'Cue:' / 'Cue words:' label."""
    bold = re.findall(r'\*\*(.+?)\*\*', text)
    src = bold if bold else [text]
    out = []
    for seg in src:
        q = QUOTE_RE.findall(seg)
        out += q if q else ([seg] if bold else [])
    return [c for c in (clean_cue(x) for x in out) if c]


def kind_of(t):
    if t.startswith('Skill'):
        return 'Skill Work'
    return {'Finale': 'Game'}.get(t, t)


def sections(text, level=2):
    """{heading: [lines]} for one heading level."""
    out, cur = collections.OrderedDict(), None
    mark = '#' * level + ' '
    for ln in text.splitlines():
        if ln.startswith(mark):
            cur = ln[len(mark):].strip(); out[cur] = []
        elif cur is not None:
            out[cur].append(ln)
    return out


def cheat_meanings(readme):
    m, names_out, anchor = {}, collections.OrderedDict(), ''
    for head, ls in sections(readme).items():
        if 'cheat sheet' not in head.lower():
            continue
        anchor = slug(head)
        for ln in ls:
            if ln.startswith('|') and '**' in ln:
                cells = [c.strip() for c in ln.strip().strip('|').split('|')]
                idx = next((i for i, c in enumerate(cells) if c.startswith('**')), None)
                if idx is None:
                    continue
                names = re.match(r'\*\*(.+?)\*\*', cells[idx]).group(1).split(' / ')
                note = cells[-1] if idx == 0 else ' · '.join(c for i, c in enumerate(cells) if i != idx)
                for nm in names:
                    m.setdefault(cue_key(nm), note.strip('"'))
                    names_out.setdefault(cue_key(nm), (nm, note.strip('"')))
            else:
                b = re.match(r'^- ([^:"]+): (.+)$', ln)
                if b:
                    for q in QUOTE_RE.findall(b.group(2)):
                        m.setdefault(cue_key(q), b.group(1))
                        names_out.setdefault(cue_key(q), (q, b.group(1)))
    return m, names_out, anchor


def video_info(line, text, url, files_rank):
    """(title, channel) guessed from one line that contains the link."""
    v = re.search(r'Verified title: "(.+?)" \((.+?)\)\.?\*', line)
    if v:
        return v.group(1), v.group(2), 0
    if ' — ' in text:
        t, c = text.rsplit(' — ', 1)
        return t.strip(), c.strip(), 1
    after = line.split(url + ')', 1)[-1]
    c = re.match(r'\s*—\s*\*([^*]+?)\.?\*', after)
    if c:
        return text, c.group(1).strip(), 2
    c = re.match(r':\s*"(.+?)"\s*\((.+?)\)', after)
    if c:
        return c.group(1), c.group(2), 2
    if line.startswith('|'):
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        for i, cell in enumerate(cells):
            if url in cell and i + 1 < len(cells):
                return text, cells[i + 1], 3
    return text, '', 9


def load():
    weeks = []
    for wdir in sorted(WEEKS.glob('week-*')):
        wnum = int(wdir.name.split('-')[1])
        meta_p = wdir / 'week.json'
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        readme = (wdir / 'README.md').read_text()
        title = readme.splitlines()[0].lstrip('# ').strip()
        week_of = meta.get('week_of', '')
        if not week_of:
            m = re.search(r'\*\*Week of (?:\w+day, )?([^·*]+?)\s*·', readme)
            week_of = m.group(1).strip() if m else ''
        w = dict(num=wnum, dir=wdir, rel=f'weeks/{wdir.name}', title=title, week_of=week_of, meta=meta,
                 readme=readme, sessions=[], topics=[],
                 videos=collections.OrderedDict())
        w['meanings'], w['cheat'], w['cheat_anchor'] = cheat_meanings(readme)
        vids = w['videos']

        def add_video(url, text, line, rank_base, loc):
            t, c, q = video_info(line, text, url, rank_base)
            v = vids.setdefault(url, dict(url=url, title=t, channel=c, q=q + rank_base, label=text, locs=[]))
            if q + rank_base < v['q']:
                v.update(title=t, channel=c, q=q + rank_base)
            if not v['channel'] and c:
                v['channel'] = c
            if loc and loc not in v['locs']:
                v['locs'].append(loc)
            return v

        for sf in sorted(wdir.glob('session-*.md'), key=lambda p: int(re.findall(r'\d+', p.name)[0])):
            lines = sf.read_text().splitlines()
            sm = re.match(r'^# Week \d+ · Session (\d+): (.+)$', lines[0])
            snum, rest = int(sm.group(1)), sm.group(2)
            tm = re.search(r'\(([^()]*\d[^()]*)\)\s*$', rest)
            name = rest[:tm.start()].strip() if tm else rest
            sport = meta.get('sessions', {}).get(str(snum), {}).get('sport', '')
            pm = re.match(r'^(Baseball|Soccer|Flag Football|Athleticism|Mixed[^:]*): (.+)$', name)
            if pm:
                sport = sport or pm.group(1); name = pm.group(2)
            s = dict(num=snum, sport=sport or 'Multi-sport', name=name, time=tm.group(1) if tm else '',
                     file=f'{w["rel"]}/{sf.name}', acts=[])
            act, has_heads = None, any(ACT_RE.match(HEAD_CUE_RE.sub('', l)) for l in lines)
            for ln in lines:
                if ln.startswith('## '):
                    hc = HEAD_CUE_RE.search(ln)
                    am = ACT_RE.match(HEAD_CUE_RE.sub('', ln))
                    if am:
                        nm = am.group(3).strip()
                        act = dict(type=am.group(1), kind=kind_of(am.group(1)), who=am.group(2) or '',
                                   name=nm, time=am.group(4) or '', cues=[], anchor=slug(ln[3:]),
                                   videos=[], why='', session=s)
                        if hc:
                            act['cues'].append(hc.group(1))
                        s['acts'].append(act)
                    else:
                        act = None  # Huddle, Water break, Kid's Choice ...
                    continue
                if not has_heads:
                    st = STATION_RE.match(ln)
                    if st:
                        act = dict(type='Station', kind='Station', who='', name=st.group(1), time='',
                                   cues=[], anchor='', videos=[], why='', session=s)
                        c = re.search(r'\*Cue: (.+?)\*', st.group(2))
                        if c:
                            act['cues'] += cues_from(c.group(1))
                        s['acts'].append(act)
                        act = None  # a station is one list item; text after the list is about the whole day
                        continue
                for url_text, url in [(m.group(1), m.group(2)) for m in LINK_RE.finditer(ln)]:
                    v = add_video(url, url_text, ln, 0, (s['num'], act['name'] if act else ''))
                    if act is not None and url not in act['videos']:
                        act['videos'].append(url)
                if act is None:
                    continue
                cm = re.match(r'^\*\*Cue(?: words)?:\*\*\s*(.*)$', ln)
                if cm:
                    act['cues'] += [c for c in cues_from(cm.group(1)) if c not in act['cues']]
                wm = re.search(r'\*\*Why(?: it works)?:\*\*\s*(.*)$', ln)
                if wm and not act['why']:
                    act['why'] = wm.group(1).strip()
            w['sessions'].append(s)

        gc = wdir / 'group-coaching.md'
        if gc.exists():
            for ln in gc.read_text().splitlines():
                if ln.startswith('## '):
                    w['topics'].append(dict(name=ln[3:].strip(), anchor=slug(ln[3:]), file=f'{w["rel"]}/group-coaching.md'))
                for m in LINK_RE.finditer(ln):
                    add_video(m.group(2), m.group(1), ln, 0, ('group', ''))
        for head, ls in sections(readme).items():
            in_list = bool(VIDEO_LIST_HEADS.search(head))
            for ln in ls:
                for m in LINK_RE.finditer(ln):
                    add_video(m.group(2), m.group(1), ln, 5, None if in_list else ('readme', head))
        for url, locs in meta.get('video_locations', {}).items():
            if url in vids:
                for sn, an in locs:
                    loc = (int(sn), an)
                    if loc not in vids[url]['locs']:
                        vids[url]['locs'].append(loc)
                    for s in w['sessions']:
                        if s['num'] == int(sn):
                            for a in s['acts']:
                                if a['name'] == an and url not in a['videos']:
                                    a['videos'].append(url)
        overrides = meta.get('activity_sport', {})
        for s in w['sessions']:
            for a in s['acts']:
                a['sport'] = overrides.get(f'{s["num"]}/{a["name"]}', s['sport'] if s['sport'] in SPORT_ORDER else
                                           next((x for x in SPORT_ORDER if s['sport'].startswith(x)), 'Multi-sport'))
        weeks.append(w)
    return weeks


def link(text, path, anchor='', base='indexes'):
    rel = ('../' if base == 'indexes' else '') + path
    return f'[{esc(text)}]({rel}{"#" + anchor if anchor else ""})'


def act_link(a, w, prefix_type=False):
    s = a['session']
    label = (a['type'] + ': ' if prefix_type and a['type'] != 'Station' else '') + a['name']
    if a['who']:
        label += f' ({a["who"]})'
    return link(label, s['file'], a['anchor'])


def ws(w, s, extra=''):
    return link(f'W{w["num"]} S{s["num"]}' + (f': {extra}' if extra else ''), s['file'])


def sport_key(sp):
    return (SPORT_ORDER.index(sp) if sp in SPORT_ORDER else 99, sp)


def all_acts(weeks):
    for w in weeks:
        for s in w['sessions']:
            for a in s['acts']:
                yield w, s, a


HEADER = '<!-- Generated by scripts/build.py from the week folders. Edit the week files, then rerun the script. -->\n'



def build_cues(weeks):
    out = [HEADER, '# Cue Words (all weeks)', '', '[← Home](../README.md)', '',
           'Grouped by sport (the sport of the activity), alphabetical within each sport. '
           'Some activities use more than one cue, and some cues come back in later weeks.', '']
    by = collections.defaultdict(list)
    for w, s, a in all_acts(weeks):
        for c in a['cues']:
            by[a['sport']].append((cue_key(c), c, w, s, a))
    total = 0
    for sp in sorted(by, key=sport_key):
        out += [f'## {sp}', '', '| Cue | Activity | Week / Session | Cheat-sheet note |', '|---|---|---|---|']
        for key, c, w, s, a in sorted(by[sp], key=lambda t: (t[0], t[2]['num'], t[3]['num'])):
            note = w['meanings'].get(key, '')
            out.append(f'| **{esc(c)}** | {act_link(a, w, True)} | {ws(w, s)} | {esc(note)} |')
            total += 1
        out.append('')
    extra = []
    for w in weeks:
        used = {cue_key(c) for _, _, a in all_acts([w]) for c in a['cues']}
        for key, (name, note) in w['cheat'].items():
            if key not in used:
                extra.append(f'| **{esc(name)}** | {esc(note)} | {link("Week %d cheat sheet" % w["num"], w["rel"] + "/README.md", w["cheat_anchor"])} |')
    if extra:
        out += ['## Also on the weekly cheat sheets', '',
                'Cue words listed on a week\'s cheat sheet that are not the main cue line of a single activity.', '',
                '| Cue | Cheat-sheet note | Week |', '|---|---|---|'] + extra + ['']
        total += len(extra)
    (IDX / 'cue-words.md').write_text('\n'.join(out))
    return total


def loc_text(w, loc):
    kind, an = loc
    if kind == 'group':
        return link(f'W{w["num"]} group coaching', w['rel'] + '/group-coaching.md')
    if kind == 'readme':
        return link(f'W{w["num"]} overview: {an}', w['rel'] + '/README.md', slug(an))
    s = next(x for x in w['sessions'] if x['num'] == kind)
    a = next((x for x in s['acts'] if x['name'] == an), None)
    return ws(w, s, s['name']) + (f' · {act_link(a, w)}' if a else '')


def build_videos(weeks):
    out = [HEADER, '# Videos (all weeks)', '', '[← Home](../README.md)', '',
           'Every YouTube link in the plans, one row per video per week, in week order. These are mostly for the coach to watch, not the boys.', '',
           '| # | Video | Channel | Week | Where it is used |', '|---|---|---|---|---|']
    i = 0
    for w in weeks:
        for v in w['videos'].values():
            i += 1
            locs = '<br>'.join(loc_text(w, l) for l in v['locs']) or link(f'W{w["num"]} video list', w['rel'] + '/README.md')
            out.append(f'| {i} | [{esc(v["title"])}]({v["url"]}) | {esc(v["channel"])} | '
                       f'{link("Week %d" % w["num"], w["rel"] + "/README.md")} | {locs} |')
    out.append('')
    (IDX / 'videos.md').write_text('\n'.join(out))
    return i


def build_drills(weeks):
    out = [HEADER, '# Drills & Games Catalog (all weeks)', '', '[← Home](../README.md)', '',
           'Grouped by sport, then by activity type (warm-up, skill work, game, station, cool-down). '
           '"Stations" are the Week 1 Backyard Olympics challenges.', '']
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for w, s, a in all_acts(weeks):
        by[a['sport']][a['kind']].append((w, s, a))
    n = 0
    for sp in sorted(by, key=sport_key):
        out += [f'## {sp}', '']
        for kind in TYPE_ORDER:
            items = by[sp].get(kind)
            if not items:
                continue
            out += [f'### {kind}', '', '| Drill / game | Cue(s) | Time | Week / Session | Video |', '|---|---|---|---|---|']
            for w, s, a in items:
                vids = ', '.join(f'[{esc(w["videos"][u]["title"])}]({u})' for u in a['videos'])
                cues = ', '.join(f'**{esc(c)}**' for c in a['cues'])
                out.append(f'| {act_link(a, w)} | {cues} | {esc(a["time"])} | {ws(w, s, s["name"])} | {vids} |')
                n += 1
            out.append('')
    (IDX / 'drills.md').write_text('\n'.join(out))
    return n


# Learning ideas named inside the "Why it works" notes, normalised to one name each.
PRINCIPLES = [
    ('External focus', [r'external focus', r'outside the body']),
    ('Analogy / implicit learning', [r'analogy learning', r'\bimplicitly\b', r'\*analogy\*', r'natural reflex instead of a list']),
    ('Errorless learning (start easy, then add difficulty)', [r'errorless learning', r'catch it most of the time', r'catching most of the time']),
    ('Constraints-led games (let the setup do the coaching)', [r'constraints-led', r'\bconstraint\b', r'constraint on the environment', r'without needing you to correct']),
    ('Whole-part-whole / part practice', [r'whole-part-whole', r'part-practice', r'part-to-whole', r'whole practice', r'Freezing each part', r'teaching them separately']),
    ('Contrast (show wrong vs. right)', [r'\bcontrast\b']),
    ('Progression from easy to hard', [r'progression from easy to hard', r'Stepping down in ball size', r'Shrinking the gate', r'One new piece on top']),
    ('Just-right challenge / scaling the task', [r'just-right challenge', r'scaling the task', r'60 to 80% success', r'just hard enough', r'handicaps keep both']),
    ('Autonomy (let them choose)', [r'\bautonomy\b', r'Calling his own route', r'gives them a say']),
    ('Developmentally appropriate', [r'developmentally appropriate']),
    ('Cooperative motivation / compete against yourself', [r'\bcooperative\b', r'against himself', r'comparing himself']),
    ('Variable practice', [r'variable practice', r'random order', r'mix of spots']),
    ('Instant feedback', [r'instant, honest feedback', r'shows right away']),
    ('Reaction training', [r'reaction trigger', r'reaction time', r'react to what they see']),
    ('Teach-back (learning by teaching)', [r'Explaining a skill', r'Teaching the cue', r'teach-back where']),
    ('Mental rehearsal / recall', [r'mental rehearsal', r'Saying the cue one last time', r'recall what they learned']),
    ('Ending on a high', [r'remember the end', r'ending on a high', r'clear ending', r'clear, calm end', r'celebration day']),
]


def readme_block(readme, entry, wnum):
    lines = readme.splitlines()
    if 'section' in entry:
        secs = sections(readme)
        body = secs.get(entry['section'])
        if body is None:
            return None
        body = [('#' + l) if re.match(r'^#{3,5} ', l) else l for l in body]
        while body and body[-1].strip() in ('', '---'):
            body.pop()
        return body
    for i, l in enumerate(lines):
        if l.startswith(entry['block']):
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            return lines[i:j]
    return None


def build_principles(weeks):
    out = [HEADER, '# Coaching Principles (how to teach)', '', '[← Home](../README.md)', '',
           'The general teaching habits from each week, quoted from the weekly plans, then the learning ideas behind individual drills (quoted from each drill\'s "Why it works" note).', '',
           '## Contents', '']
    body = []
    for w in weeks:
        entries = w['meta'].get('principles', [])
        blocks = [b for b in (readme_block(w['readme'], e, w['num']) for e in entries) if b]
        if not blocks:
            continue
        h = f'Week {w["num"]} teaching habits'
        out.append(f'- [{h}](#{slug(h)})')
        body += [f'## {h}', '', f'*From the {link("Week %d overview" % w["num"], w["rel"] + "/README.md")}.*', '']
        for e, b in zip([e for e in entries if readme_block(w['readme'], e, w['num'])], blocks):
            if 'section' in e:
                body += [f'### {e["section"]}', '']
            body += b + ['']
        for t in w['topics']:
            if 'ask before tell' in t['name'].lower():
                body += [f'**Ask before tell:** see {link(t["name"], t["file"], t["anchor"])} in the Week {w["num"]} field-coaching notes.', '']
    out.append('- [Learning ideas behind the drills](#learning-ideas-behind-the-drills)')
    out += [''] + body
    out += ['## Learning ideas behind the drills', '',
            'Each idea links to the activities whose "Why it works" note uses it, with the sentence that says so.', '']
    for name, pats in PRINCIPLES:
        rows = []
        for w, s, a in all_acts(weeks):
            sentences = re.split(r'(?:(?<=[.!?])|(?<=[.!?]"))\s+(?=[A-Z*])', a['why'])
            hit = next((x for x in sentences if any(re.search(p, x, re.I) for p in pats)), None)
            if hit:
                rows.append(f'- {link("W%d S%d · %s" % (w["num"], s["num"], a["name"]), s["file"], a["anchor"])}: {hit}')
        if rows:
            out += [f'### {name}', ''] + rows + ['']
    (IDX / 'coaching-principles.md').write_text('\n'.join(out))


def build_field(weeks):
    out = [HEADER, '# Field Coaching (group practice tips, all weeks)', '', '[← Home](../README.md)', '',
           'Tips for coaching groups of kids at the baseball fields, by week. Each week adds new topics.', '']
    n = 0
    for w in weeks:
        out += [f'## Week {w["num"]}', '']
        if w['topics']:
            gtitle = (w['dir'] / 'group-coaching.md').read_text().splitlines()[0].split(' · ', 1)[-1]
            out += [f'{link(gtitle, w["rel"] + "/group-coaching.md")}', '']
            for t in w['topics']:
                out.append(f'- {link(t["name"], t["file"], t["anchor"])}')
                n += 1
        out.append('')
    (IDX / 'field-coaching.md').write_text('\n'.join(out))
    return n


def build_schedule(weeks):
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    plan = {'Mon': 1, 'Tue': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5}
    rows = ['| Week | ' + ' | '.join(f'{d} {"S%d" % plan[d] if d in plan else ("Play" if d == "Wed" else "Rest")}' for d in days) + ' |',
            '|' + '---|' * 8]
    for w in weeks:
        label = link(f'Week {w["num"]}', w['rel'] + '/README.md', base='root')
        if w['week_of']:
            label += f'<br>{w["week_of"]}'
        sess = {s['num']: s for s in w['sessions']}
        cells = []
        for d in days:
            if d == 'Wed':
                cells.append('10-min play')
            elif d == 'Sun':
                cells.append('Rest')
            elif plan[d] in sess:
                s = sess[plan[d]]
                cells.append(link(f'S{s["num"]} {s["sport"]}: {s["name"]}', s['file'], base='root'))
            else:
                cells.append('')
        rows.append(f'| {label} | ' + ' | '.join(cells) + ' |')
    readme = ROOT / 'README.md'
    t = readme.read_text()
    new = '<!-- SCHEDULE:START (generated by scripts/build.py) -->\n' + '\n'.join(rows) + '\n<!-- SCHEDULE:END -->'
    readme.write_text(re.sub(r'<!-- SCHEDULE:START.*?<!-- SCHEDULE:END -->', new, t, flags=re.S))


CSS = """body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#1f2328}
a{color:#0969da}table{border-collapse:collapse;margin:1rem 0;display:block;overflow-x:auto}th,td{border:1px solid #d0d7de;padding:6px 10px;vertical-align:top}
th{background:#f6f8fa}blockquote{border-left:4px solid #d0d7de;margin:0;padding:0 1rem;color:#59636e}code{background:#f6f8fa;padding:2px 4px;border-radius:4px}
pre{background:#f6f8fa;padding:1rem;overflow-x:auto}h1,h2{border-bottom:1px solid #d8dee4;padding-bottom:.3em}nav.top{font-size:.9em;margin-bottom:1rem}"""


def build_site():
    try:
        import markdown
    except ImportError:
        print('skip site/: run `pip install markdown` to build the HTML copy', file=sys.stderr)
        return
    import shutil
    site = ROOT / 'site'
    if site.exists():
        shutil.rmtree(site)
    files = [p for p in ROOT.rglob('*.md') if not any(part in ('site', '.git', 'sources') for part in p.relative_to(ROOT).parts)]
    for p in files:
        rel = p.relative_to(ROOT)
        out = site / rel.with_name('index.html' if rel.name == 'README.md' else rel.stem + '.html')
        out.parent.mkdir(parents=True, exist_ok=True)
        text = p.read_text()

        def fix(m):
            target = m.group(2)
            if re.match(r'https?:', target):
                return m.group(0)
            path, _, anchor = target.partition('#')
            if path.endswith('README.md'):
                path = path[:-len('README.md')] + 'index.html'
            elif path.endswith('.md'):
                path = path[:-3] + '.html'
            return f'{m.group(1)}({path}{"#" + anchor if anchor else ""})'
        text = re.sub(r'(\[(?:[^\[\]]|\[[^\]]*\])*\])\(([^)\s]+)\)', fix, text)
        body = markdown.markdown(text, extensions=['tables', 'sane_lists', 'toc'],
                                 extension_configs={'toc': {'slugify': lambda v, sep: slug(v)}})
        home = '../' * (len(rel.parts) - 1) + 'index.html'
        first = next((l for l in text.splitlines() if l.startswith('# ')), '# Youth Sports Coaching')
        title = html.escape(first.lstrip('# '))
        out.write_text(f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                       f'<title>{title}</title><style>{CSS}</style></head><body><nav class="top"><a href="{home}">🏠 Home</a></nav>{body}</body></html>\n')
    print(f'site/: {len(files)} pages')


def main():
    weeks = load()
    IDX.mkdir(exist_ok=True)
    n_cues = build_cues(weeks)
    n_vid = build_videos(weeks)
    n_act = build_drills(weeks)
    build_principles(weeks)
    n_top = build_field(weeks)
    build_schedule(weeks)
    for w in weeks:
        na = sum(len(s['acts']) for s in w['sessions'])
        nc = sum(len(a['cues']) for s in w['sessions'] for a in s['acts'])
        print(f'  week {w["num"]}: {len(w["sessions"])} sessions, {na} activities, {nc} cue entries, '
              f'{len(w["videos"])} videos, {len(w["topics"])} field topics')
    print(f'total: {len(weeks)} weeks, {n_act} activities, {n_cues} cue entries, {n_vid} videos, {n_top} field topics')
    if '--no-site' not in sys.argv:
        build_site()


if __name__ == '__main__':
    main()
