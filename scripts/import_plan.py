#!/usr/bin/env python3
"""Split a full weekly plan (one markdown file) into the repo's week layout.

Usage:  python3 scripts/import_plan.py 4 sources/week-04-plan.md

Expects the same shape as the Week 3 plan:
  # Week N ... title
  ## 1. Week Overview
  ## 2. Session 1: <Sport>: <Title> (NN min)   ... one per session
  ## 7. Coaching Groups at the Fields ...
  ## 8. Week N+1 Preview
  ## 9. Week N Cue-Word Cheat Sheet
  ## Video List ...
Session text is copied verbatim; only heading levels are shifted (### -> ##)
and a small navigation line is added. Afterwards run: python3 scripts/build.py
"""
import re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

def main(week, src):
    text = pathlib.Path(src).read_text()
    lines = text.splitlines()
    title = lines[0].lstrip('# ').strip()
    subtitle = lines[1].strip() if len(lines) > 1 else ''
    # split into level-2 sections
    sections, cur = [], None
    for ln in lines[2:]:
        if ln.startswith('## '):
            cur = [ln[3:].strip(), []]
            sections.append(cur)
        elif cur is not None:
            cur[1].append(ln)
    trailer = []
    def body(ls):
        ls = list(ls)
        while ls and ls[-1].strip() in ('', '---'):
            ls.pop()
        while ls and ls[0].strip() == '':
            ls.pop(0)
        return ls

    wdir = ROOT / 'weeks' / f'week-{week:02d}'
    wdir.mkdir(parents=True, exist_ok=True)
    overview, extra, sessions, group = [], [], [], None
    for head, ls in sections:
        h = re.sub(r'^\d+\.\s*', '', head)
        m = re.match(r'Session (\d+): (.+)', h)
        if m:
            sessions.append((int(m.group(1)), m.group(2), body(ls)))
        elif h.startswith('Week Overview'):
            overview = body(ls)
        elif h.startswith('Coaching Groups'):
            group = (h, body(ls))
        else:
            b = body(ls)
            # closing sign-off line after the video list stays in README
            extra.append((h, b))

    n = len(sessions)
    for num, stitle, ls in sessions:
        prev = f'[← Session {num-1}](session-{num-1}.md) · ' if num > 1 else ''
        nxt = f' · [Session {num+1} →](session-{num+1}.md)' if num < n else ''
        nav = f'{prev}[Week {week} overview](README.md){nxt}'
        out = [f'# Week {week} · Session {num}: {stitle}', '', nav, '']
        for ln in ls:
            out.append(ln[1:] if ln.startswith('### ') else ln)  # ### -> ##
        out += ['', '---', '', nav, '']
        (wdir / f'session-{num}.md').write_text('\n'.join(out))

    if group:
        h, ls = group
        out = [f'# Week {week} · {h}', '', f'[Week {week} overview](README.md)', '']
        for ln in ls:
            out.append(ln[1:] if ln.startswith('### ') else ln)
        (wdir / 'group-coaching.md').write_text('\n'.join(out) + '\n')

    out = [f'# {title}', subtitle, '', '[← All weeks](../../README.md)', '',
           '## Sessions', '']
    for num, stitle, _ in sessions:
        out.append(f'- [Session {num}: {stitle}](session-{num}.md)')
    if group:
        out.append(f'- [{group[0]}](group-coaching.md)')
    out += ['', '## Week Overview', ''] + overview
    for h, ls in extra:
        out += ['', '---', '', f'## {h}', ''] + ls
    (wdir / 'README.md').write_text('\n'.join(out) + '\n')
    print(f'wrote {wdir} ({n} sessions)')

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(int(sys.argv[1]), sys.argv[2])
