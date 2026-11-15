"""이미 승인된 건 가운데 아하 보유 효과를 썼는데 제출하지 않았을 수 있는 것을 사람이 볼 HTML 로 모은다.
대상: 사이트 최근 승인(work/approved_recent.json, /api/mod/reviews?filter=approved) 중 Aeon ★ Aha 가 편성에 없고 아하 플래그도 없는 건.
(Aeon 이 편성에 있으면 보유 효과는 반드시 켜지므로 그런 건은 work/_aha_reject.py 로 바로 거절했다)
Elation 캐릭터가 있는 팀을 맨 위에 둔다(웃음 포인트 HUD 가 나오는 팀). 카드는 summary_html 과 같은 모양.
python aha_check_report.py [--fetch]   → work/aha_gp_check.html"""
import os, sys, json
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import WORK            # noqa: E402
import summary_html as S          # noqa: E402

OUT = os.path.join(WORK, 'aha_gp_check.html')
SRC = os.path.join(WORK, 'approved_recent.json')
HINT = 'Aha GP check: during the battle, the Elation point icon above the Skill Points (bottom right) or in the action order turns into a purple or red heart when the Aha Global Passive is active'


def fetch():
    import mod_api
    r = mod_api.call('GET', '/api/mod/reviews?filter=approved&limit=300&order=newest')
    json.dump(r.get('reviews') or [], open(SRC, 'w', encoding='utf8'), ensure_ascii=False)


def elation(sides):
    import imgrec, judge
    for s in sides:
        for i in range(1, 5):
            c = s.get(f'p{i}_char') or ''
            if c.endswith('(Elation)') or imgrec.path_of_char(judge.en_key(c)) == 'Elation':
                return True
    return False


def entry(x):
    p = x['payload']
    sides = p.get('runs') or [p]
    e = S.load(x['id'])
    if e:
        e = dict(e, auto=dict(e['auto']))
    else:
        e = {'rev': x['id'], 'side': dict(p, **sides[0]), 'runs': len(sides), 'videos': [], 'selection': None,
             'judged': {}, 'battle_vid': 0, 'build_vid': 0, 'auto': {}}
    who = x.get('decided_by_name') or '?'
    e['auto'].update(verdict='APPROVE', confidence='', problems=[],
                     check_reasons=[HINT, f"Approved by {who} at {str(x.get('decided_at') or '')[:16].replace('T', ' ')}"])
    return e


def group(title, rows):
    if not rows:
        return ''
    return (f'<div class="flex flex-col gap-1 rounded-xl border border-white/8 bg-white/[0.025] overflow-hidden rb-group">'
            f'<div class="rb-ghead px-2.5 py-1 sm:px-4 sm:py-2 border-b border-white/8 flex items-center gap-1 sm:gap-2">'
            f'<span class="theme-run-team-header-icon rb-gicon text-[10px] sm:text-sm">✦</span>'
            f'<span class="theme-run-team-header-text text-[11px] sm:text-sm font-semibold">{S.esc(title)}</span>'
            f'<span class="rb-gcount text-white/30 text-[9px] sm:text-xs">({len(rows)} entries)</span></div>'
            f'<div class="rb-gbody flex flex-col gap-1 p-0.5">{"".join(S.card(e) for e in rows)}</div></div>')


def build():
    items = json.load(open(SRC, encoding='utf8'))
    el, other = [], []
    for x in items:
        p = x['payload']
        sides = p.get('runs') or [p]
        if any((s.get(f'p{i}_char') or '').startswith('Aeon') for s in sides for i in range(1, 5)):
            continue
        if any('aha' in (s.get('flags') or '') for s in sides):
            continue
        (el if elation(sides) else other).append(entry(x))
    css = (open(S.THEME, encoding='utf8').read() + '\n' if os.path.exists(S.THEME) else '') + S.LITE_CSS
    title = 'Aha Global Passive check (approved, no Aeon on the team)'
    body = group('Teams with an Elation character', el) + group('Other teams', other)
    body = body.replace('>APPROVE %<', '>APPROVED<')
    text = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Aha GP check</title><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">'
            f'<style>{css}</style></head><body><main class="rb-wrap">'
            f'<div><div class="rb-title">{S.esc(title)}</div><div class="rb-sub">{len(el) + len(other)} records · '
            f'{S.esc(datetime.now().strftime("%Y-%m-%d %H:%M"))} · Elation teams first</div></div>{body}</main></body></html>')
    open(OUT, 'w', encoding='utf8').write(text)
    return len(el), len(other)


if __name__ == '__main__':
    if '--fetch' in sys.argv:
        fetch()
    print(build(), OUT)
