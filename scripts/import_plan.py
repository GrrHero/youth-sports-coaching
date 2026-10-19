#!/usr/bin/env python3
"""Split a full weekly plan (one markdown file) into the repo's week layout.

Usage:  python3 scripts/import_plan.py WEEK SOURCE.md [--week-of "Oct 26, 2026"]
e.g.    python3 scripts/import_plan.py 4 sources/week-04-plan.md --week-of "Oct 26, 2026"

Works with the layouts used so far (Weeks 1-3). Level-2 (##) sections are routed:
  * "Session N: ..." / "Session N — ..." / "SESSION N: ..." / "N. Session N: ..."  -> session-N.md
  * a heading mentioning group / volunteer coaching at the fields               -> group-coaching.md
  * everything else (overview, how-to-teach, preview, videos, cheat sheet)       -> README.md
Text is copied verbatim. Only heading levels change (### -> ## inside session and
group files), a leading "N. " section number is dropped, and navigation links are added.
Then edit weeks/week-NN/week.json (sport per session/activity) and run scripts/build.py.
"""
import re, sys, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SESSION_RE = re.compile(r'^(?:\d+\.\s*)?session\s+(\d+)\s*(?::|—|–|-)\s*(.+)$', re.I)
GROUP_RE = re.compile(r'(coaching groups|group coaching|volunteer coaching)', re.I)


def trim(ls):
    ls = list(ls)
    while ls and ls[-1].strip() in ('', '---'):
        ls.pop()
    while ls and ls[0].strip() in ('', '---'):
        ls.pop(0)
    return ls


def demote(ls):
    """Inside session/group files the section becomes the page title, so ### -> ##, #### -> ###."""
    return [ln[1:] if re.match(r'^#{3,6} ', ln) else ln for ln in ls]


def main(week, src, week_of=None):
    lines = pathlib.Path(src).read_text().splitlines()
    title = lines[0].lstrip('# ').strip()
    i, sub = 1, []
    while i < len(lines) and not lines[i].startswith('## '):
        if lines[i].strip() not in ('', '---'):
            sub.append(lines[i])
        i += 1
    sections, cur = [], None
    for ln in lines[i:]:
        if ln.startswith('## '):
            cur = [ln[3:].strip(), []]
            sections.append(cur)
        else:
            cur[1].append(ln)

    wdir = ROOT / 'weeks' / f'week-{week:02d}'
    wdir.mkdir(parents=True, exist_ok=True)
    for old in wdir.glob('session-*.md'):
        old.unlink()
    sessions, group, other = [], None, []
    for head, ls in sections:
        h = re.sub(r'^\d+\.\s+', '', head)
        m = SESSION_RE.match(h)
        if m:
            sessions.append((int(m.group(1)), m.group(2).strip(), trim(ls)))
        elif GROUP_RE.search(h) and group is None:
            group = (h, trim(ls))
        else:
            other.append((h, trim(ls)))

    n = len(sessions)
    for num, stitle, ls in sessions:
        prev = f'[← Session {num-1}](session-{num-1}.md) · ' if num > 1 else ''
        nxt = f' · [Session {num+1} →](session-{num+1}.md)' if num < n else ''
        nav = f'{prev}[Week {week} overview](README.md){nxt}'
        out = [f'# Week {week} · Session {num}: {stitle}', '', nav, ''] + demote(ls) + ['', '---', '', nav, '']
        (wdir / f'session-{num}.md').write_text('\n'.join(out))

    gfile = wdir / 'group-coaching.md'
    if group:
        h, ls = group
        out = [f'# Week {week} · {h}', '', f'[Week {week} overview](README.md)', ''] + demote(ls)
        gfile.write_text('\n'.join(out) + '\n')
    elif gfile.exists():
        gfile.unlink()

    meta_p = wdir / 'week.json'
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    week_of = week_of or meta.get('week_of')
    out = [f'# {title}'] + sub
    if week_of and not any('Week of' in s for s in sub):
        out += ['', f'*Week of {week_of}*']
    out += ['', '[← All weeks](../../README.md)', '', '## Sessions', '']
    out += [f'- [Session {num}: {stitle}](session-{num}.md)' for num, stitle, _ in sessions]
    if group:
        out.append(f'- [{group[0]}](group-coaching.md)')
    for k, (h, ls) in enumerate(other):
        out += ['', '---', ''] if k else ['']
        out += [f'## {h}', ''] + ls
    (wdir / 'README.md').write_text('\n'.join(out) + '\n')

    if week_of:
        meta['week_of'] = week_of
    meta.setdefault('sessions', {})
    for num, stitle, _ in sessions:
        meta['sessions'].setdefault(str(num), {'sport': ''})
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + '\n')
    print(f'wrote {wdir.relative_to(ROOT)}: {n} sessions, group={"yes" if group else "no"}, '
          f'README sections={[h for h, _ in other]}')


if __name__ == '__main__':
    args = sys.argv[1:]
    wo = None
    if '--week-of' in args:
        k = args.index('--week-of'); wo = args[k + 1]; del args[k:k + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    main(int(args[0]), args[1], wo)
