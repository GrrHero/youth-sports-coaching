#!/usr/bin/env python3
"""Scaffold weeks/week-NN/ from the template.  Usage: python3 scripts/new_week.py 4"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
n = int(sys.argv[1])
d = ROOT / 'weeks' / f'week-{n:02d}'
if d.exists():
    sys.exit(f'{d} already exists')
d.mkdir(parents=True)
tpl = (ROOT / '_templates' / 'session-template.md').read_text()
sports = ['Baseball', 'Soccer', 'Flag Football', 'Athleticism', 'Mixed Backyard Day']
for i, sport in enumerate(sports, 1):
    t = tpl.replace('Week N · Session N: Sport:', f'Week {n} · Session {i}: {sport}:')
    t = t.replace('Week N overview', f'Week {n} overview').replace('session-N-1.md', f'session-{i-1}.md')
    t = t.replace('session-N+1.md', f'session-{i+1}.md').replace('Session N-1', f'Session {i-1}').replace('Session N+1', f'Session {i+1}')
    if i == 1:
        t = t.replace('[← Session 0](session-0.md) · ', '')
    if i == len(sports):
        t = t.replace(f' · [Session {i+1} →](session-{i+1}.md)', '')
    (d / f'session-{i}.md').write_text(t)
(d / 'README.md').write_text(f"""# Week {n} Home Training Plan: "Theme"
**Week of Monday, Mon DD, YYYY · For Greg's boys (7 & 5)**

[← All weeks](../../README.md)

## Sessions

""" + '\n'.join(f'- [Session {i}: {s}](session-{i}.md)' for i, s in enumerate(sports, 1)) + """
- [Coaching Groups at the Fields](group-coaching.md)

## Week Overview

**Theme:** ...

**What carries over from last week:**

| Last week's skill | This week's next step |
|---|---|

## Week Cue-Word Cheat Sheet

| Cue Word | Session / Activity | What it means to the kid |
|---|---|---|
""")
(d / 'group-coaching.md').write_text(f'# Week {n} · Coaching Groups at the Fields\n\n[Week {n} overview](README.md)\n\n## A. Topic\n- ...\n')
print(f'created {d}; fill it in, then run python3 scripts/build.py')
