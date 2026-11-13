"""제출자는 검토 중에도 기록을 고쳐 다시 낼 수 있다(rev_1m4vjwr 3번째 런: 분석한 뒤 보유 효과를 고쳐 제출 아이디가 바뀜).
그래서 ① 분석 직전에 이 건의 최신 제출 정보를 사이트에서 다시 받고, ② 결정 · 메모를 보내기 직전에 그동안 바뀌지 않았는지 확인한다.
사이트에 건 하나만 받는 API 가 없어서(/api/bot/reviews/<id> 는 404) 대기열 쪽을 넘기며 찾는다(100건씩).

fetch_item(rev)         최신 건 dict, 이미 결정되어 대기열에서 사라졌으면 None
fingerprint(item)       제출 내용(종류 · 런 아이디 · payload)의 해시
save(rev, item)         runs/<rev>/fingerprint.txt 에 지문을 적는다
changed(rev)            (바뀜 여부, 최신 건) — 지문 파일이 없으면 바뀌지 않은 것으로 본다. 건이 사라졌으면 (True, None)"""
import os, sys, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mod_api            # noqa: E402
from paths import RUNS    # noqa: E402


def fetch_item(rev):
    page = 1
    while page <= 50:
        r = mod_api.call('GET', f'/api/bot/reviews?limit=100&page={page}')
        got = r.get('reviews') or []
        for x in got:
            if x['id'] == rev:
                return x
        if not got or page * 100 >= int(r.get('total') or 0):
            return None
        page += 1
    return None


def fingerprint(item):
    body = {'kind': item.get('kind'), 'run_ids': item.get('run_ids'), 'payload': item.get('payload')}
    return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode('utf8')).hexdigest()[:16]


def _path(rev):
    return os.path.join(RUNS, rev, 'fingerprint.txt')


def save(rev, item):
    os.makedirs(os.path.join(RUNS, rev), exist_ok=True)
    open(_path(rev), 'w').write(fingerprint(item))


def changed(rev):
    try:
        old = open(_path(rev)).read().strip()
    except OSError:
        return False, None
    cur = fetch_item(rev)
    if cur is None:
        return True, None
    return fingerprint(cur) != old, cur


def guard(rev):
    """결정 · 메모를 보내기 직전 확인(work/_fin*.py). 지문 파일이 없으면 work/queue.json 에 받아 둔 건과 견준다.
    바뀌었거나 사라졌으면 이유 문자열(보내지 말 것), 아니면 None."""
    from paths import WORK
    try:
        old = open(_path(rev)).read().strip()
    except OSError:
        try:
            q = {x['id']: x for x in json.load(open(os.path.join(WORK, 'queue.json'), encoding='utf8'))}
            old = fingerprint(q[rev])
        except (OSError, KeyError, ValueError):
            return None
    cur = fetch_item(rev)
    if cur is None:
        return 'already decided or gone'
    if fingerprint(cur) != old:
        return 'submission changed since it was analysed - re-run it (python tools/run_queue.py %s)' % rev
    return None
