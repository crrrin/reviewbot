"""theherta.com 검토 API 를 브라우저 자동 조종(Chrome DevTools) 없이 부른다.

인증은 두 가지다. 봇 키가 있으면 봇 API(/api/bot/...)를 쓰고, 없으면 예전 방식(로그인 세션 토큰, /api/mod/...)으로 돌아간다.

[봇 키] 관리자가 만든 tga_bot_... 키. config.json 에
  "bot_key": "tga_bot_..."
를 넣거나 환경 변수 THEHERTA_BOT_KEY 로 준다(환경 변수가 먼저). 만료 · refresh 가 없다. 키는 어디에도 출력하지 않는다.
  봇 키로는 대기 중 검토만 보이고, 결정을 되돌릴 수 없다(pending 없음). 합쳐 낸 검토도 보인다(kind single|dual|multi|merge).
  [기본 꺼짐: config.json 의 "review_updated_at": true 또는 환경 변수 THEHERTA_REVIEW_UPDATED_AT=1 로 켠다 — 사이트가 큐 값에도 409 를 내서 확인 중]
  메모 · 결정에는 분석한 때의 updated_at 을 review_updated_at 으로 싣는다(runs/<rev>/updated_at.txt, 없으면 work/queue.json). 409 면 건을 다시 받아
  제출 내용이 그대로일 때만 새 값으로 한 번 다시 보내고, 바뀌었거나 사라졌으면 Stale 로 멈춘다(다시 분석).

[세션 토큰] config.json 에 mod_token · mod_refresh_token · supabase_url · supabase_anon_key (README 「토큰 얻기」).

python mod_api.py queue [--out work/queue.json]      대기열을 받아 파일로(기본 work/queue.json). 봇 키면 100건씩 쪽을 넘겨 다 받는다
python mod_api.py claim <rev_id> [ttl초]             검토 중 표시(봇 키: 60~600초, 기본 300. 길어지면 다시 보낸다)
python mod_api.py release <rev_id>                   검토 중 표시 풀기
python mod_api.py note <rev_id> <approve|reject|check> [확신도] [요약]    메모(봇 키만). 사유 · 증거는 --json 파일로
python mod_api.py decide <rev_id> approve --yes
python mod_api.py decide <rev_id> reject "사유" --yes  승인 · 거절(--yes 없으면 보내지 않고 보낼 내용만 보인다)"""
import os, sys, json, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import CONFIG, WORK, RUNS, config, save_config   # noqa: E402

BASE = os.environ.get('THEHERTA_BASE', 'https://theherta.com')


def bot_key():
    return os.environ.get('THEHERTA_BOT_KEY') or config().get('bot_key') or None


def _save_cfg(cfg):
    save_config(cfg)


def refresh(cfg):
    """refresh token 으로 새 access token(Supabase GoTrue). 성공하면 config.json 을 고쳐 쓴다. (세션 토큰 방식 전용)"""
    need = ('mod_refresh_token', 'supabase_url', 'supabase_anon_key')
    if not all(cfg.get(k) for k in need):
        raise SystemExit('access token 이 만료됐고 refresh 에 필요한 값(' + ', '.join(need) + ')이 config.json 에 없다')
    req = urllib.request.Request(cfg['supabase_url'].rstrip('/') + '/auth/v1/token?grant_type=refresh_token',
                                 data=json.dumps({'refresh_token': cfg['mod_refresh_token']}).encode(),
                                 headers={'apikey': cfg['supabase_anon_key'], 'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=30))
    cfg['mod_token'], cfg['mod_refresh_token'] = r['access_token'], r['refresh_token']
    cfg['mod_token_expires_at'] = int(time.time()) + int(r.get('expires_in', 3600))
    _save_cfg(cfg)
    return cfg


class Conflict(SystemExit):
    """HTTP 409: 보낸 review_updated_at 이 사이트의 최신과 다르다(그동안 건이 바뀜)."""


class Stale(SystemExit):
    """409 뒤에 건을 다시 받아 보니 제출 내용이 바뀌었거나 이미 결정되어 사라졌다. 보내지 말고 다시 분석해야 한다."""


def _request(method, path, body, tok):
    """연결이 끊기거나(WinError 10054) 시간이 넘으면 몇 번 다시 해 본다. HTTP 오류(4xx · 5xx)는 다시 하지 않고 그대로 올린다.
    끝내 안 되면 SystemExit 로 낸다(부르는 쪽이 모두 SystemExit 를 잡는다)."""
    last = None
    for i in range(4):
        try:
            return _request_once(method, path, body, tok)
        except urllib.error.HTTPError:
            raise
        except (OSError, TimeoutError) as e:          # ConnectionError · URLError · socket.timeout 모두 OSError
            last = e
            time.sleep(2 * (i + 1))
    raise SystemExit(f'{method} {path} -> network error: {last!r}')


def _request_once(method, path, body, tok):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json',
                                          'User-Agent': 'reviewbot'})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def call(method, path, body=None, _retry=True):
    """session 경로(/api/mod/...)와 봇 경로(/api/bot/...)를 path 로 구분한다. 봇 경로는 봇 키만 쓴다."""
    if path.startswith('/api/bot/'):
        key = bot_key()
        if not key:
            raise SystemExit('봇 키가 없다(config.json 의 bot_key 또는 환경 변수 THEHERTA_BOT_KEY)')
        try:
            return _request(method, path, body, key)
        except urllib.error.HTTPError as e:
            msg = f'{method} {path} -> HTTP {e.code}: {e.read()[:300]!r}'
            raise (Conflict(msg) if e.code == 409 else SystemExit(msg))
    cfg = config()
    tok = os.environ.get('THEHERTA_TOKEN') or cfg.get('mod_token')
    if not tok:
        raise SystemExit('config.json 에 mod_token 이 없다(README 「토큰 얻기」)')
    if not os.environ.get('THEHERTA_TOKEN') and cfg.get('mod_token_expires_at') and cfg['mod_token_expires_at'] < time.time() + 60:
        tok = refresh(cfg)['mod_token']
    try:
        return _request(method, path, body, tok)
    except urllib.error.HTTPError as e:
        if e.code == 401 and _retry and not os.environ.get('THEHERTA_TOKEN'):
            refresh(config())
            return call(method, path, body, _retry=False)
        raise SystemExit(f'{method} {path} -> HTTP {e.code}: {e.read()[:300]!r}')


def _prefix():
    return '/api/bot' if bot_key() else '/api/mod'


def queue(out=None):
    if bot_key():
        items, page = [], 1
        while True:
            r = call('GET', f'/api/bot/reviews?limit=100&page={page}')
            got = r.get('reviews') or []
            seen = {x['id'] for x in items}
            items += [x for x in got if x['id'] not in seen]     # 쪽을 넘기는 사이 밀려 겹친 것은 버린다
            if not got or len(items) >= int(r.get('total') or 0) or page >= 50:
                break
            page += 1
        notes = session_notes()
        if notes is not None:
            for x in items:
                x['latest_note'] = notes.get(x['id'])
    else:
        r = call('GET', '/api/mod/reviews?filter=pending&limit=300&order=oldest')
        items = r.get('reviews', r) if isinstance(r, dict) else r
    out = out or os.path.join(WORK, 'queue.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(items, open(out, 'w', encoding='utf8'), ensure_ascii=False, indent=1)
    return items, out


def session_notes():
    """{건 아이디: latest_note} — 봇 API 대기열에는 다른 봇이 단 메모가 없어서, 로그인 세션 토큰(mod_token)의 /api/mod 대기열에서 가져온다.
    여러 봇이 같은 건을 다시 분석하고 메모를 서로 덮어쓰지 않게 하는 데 쓴다. 토큰이 없거나 만료 · 오류면 None(그때는 거르지 않는다)."""
    cfg = config()
    if not (os.environ.get('THEHERTA_TOKEN') or cfg.get('mod_token')):
        return None
    if not os.environ.get('THEHERTA_TOKEN') and cfg.get('mod_token_expires_at') and cfg['mod_token_expires_at'] < time.time() + 60 \
            and not all(cfg.get(k) for k in ('mod_refresh_token', 'supabase_url', 'supabase_anon_key')):
        return None
    try:
        r = call('GET', '/api/mod/reviews?filter=pending&limit=300&order=oldest')
    except SystemExit:
        return None
    items = r.get('reviews', r) if isinstance(r, dict) else r
    return {x['id']: x.get('latest_note') for x in items or [] if isinstance(x, dict)}


def other_note(rev, item=None, fresh=False):
    """이 건에 나 말고 다른 쪽(다른 봇 · 사람)이 단 최신 메모. 없으면 None. fresh 면 사이트에서 다시 받는다(못 받으면 item 의 것)."""
    import coord
    me = coord.my_name()
    n = (item or {}).get('latest_note')
    if fresh:
        notes = session_notes()
        if notes is not None:
            n = notes.get(rev)
    if n and n.get('author_name') and n.get('author_name') != me:
        return n
    return None


def claim(rev, ttl=300):
    if bot_key():
        return call('POST', f'/api/bot/reviews/{rev}/claim', {'ttl': max(60, min(600, int(ttl)))})
    return call('POST', f'/api/mod/reviews/{rev}/claim')


def release(rev):
    return call('DELETE', f'{_prefix()}/reviews/{rev}/claim')


_UPDATED = {}        # 이 프로세스에서 알게 된 건별 최신 updated_at(메모를 보내면 바뀔 수 있어 응답 · 재조회로 갱신)


def _known_updated(rev):
    """분석한 때의 updated_at(runs/<rev>/updated_at.txt, fresh.save 가 적음) → 없으면 work/queue.json 에 받아 둔 값."""
    if rev in _UPDATED:
        return _UPDATED[rev]
    try:
        v = open(os.path.join(RUNS, rev, 'updated_at.txt')).read().strip()
        if v:
            return v
    except OSError:
        pass
    try:
        for x in json.load(open(os.path.join(WORK, 'queue.json'), encoding='utf8')):
            if x.get('id') == rev:
                return x.get('updated_at')
    except (OSError, ValueError):
        pass
    return None


def _post_checked(rev, path, body):
    """review_updated_at 을 실어 보낸다. 409 면 건을 다시 받아, 제출 내용이 그대로일 때만(내 메모 · 검토 중 표시로 updated_at 만 바뀐 경우)
    새 값으로 한 번 다시 보낸다. 내용이 바뀌었거나 사라졌으면 Stale(보내지 않음)."""
    if not (os.environ.get('THEHERTA_REVIEW_UPDATED_AT') or config().get('review_updated_at')):
        return call('POST', path, body)       # 꺼 둠(기본): 2026-11-15 현재 사이트가 큐의 updated_at 을 그대로 보내도 409 를 낸다
    import fresh
    ua = _known_updated(rev)
    if ua:
        body = dict(body, review_updated_at=ua)
    try:
        r = call('POST', path, body)
    except Conflict:
        cur = fresh.fetch_item(rev)
        if cur is None:
            raise Stale(f'{rev}: already decided or gone (409)')
        try:
            old = open(os.path.join(RUNS, rev, 'fingerprint.txt')).read().strip()
        except OSError:
            old = None
        if old and fresh.fingerprint(cur) != old:
            raise Stale(f'{rev}: submission changed since it was analysed (409) - re-run it')
        _UPDATED[rev] = cur.get('updated_at')
        try:
            r = call('POST', path, dict(body, review_updated_at=cur.get('updated_at')))
        except Conflict:
            raise Stale(f'{rev}: still 409 after re-fetch - re-run it')
    nu = (r or {}).get('review_updated_at') or (r or {}).get('updated_at') if isinstance(r, dict) else None
    if nu:
        _UPDATED[rev] = nu
    else:
        _UPDATED.pop(rev, None)           # 다음 보냄은 409 → 재조회 길로 새 값을 얻는다
    return r


def note(rev, verdict, confidence=None, summary=None, reasons=None, evidence=None):
    """봇 메모(카드에는 가장 새 것 하나만 보인다). 판정이 끝날 때 한 번만 보낸다."""
    if verdict not in ('approve', 'reject', 'check'):
        raise SystemExit('verdict 는 approve · reject · check')
    body = {'verdict': verdict}
    if confidence is not None:
        body['confidence'] = int(confidence)
    if summary:
        body['summary'] = summary[:500]
    if reasons:
        body['reasons'] = [r[:500] for r in reasons if r][:50]
    if evidence:
        body['evidence'] = evidence[:50]
    return _post_checked(rev, f'/api/bot/reviews/{rev}/notes', body)


def decide(rev, action, reason=None):
    body = {'action': action}
    if action == 'reject':
        body['reason'] = reason
    if bot_key():
        return _post_checked(rev, f'/api/bot/reviews/{rev}/decision', body)
    return call('POST', f'{_prefix()}/reviews/{rev}/decision', body)


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    cmd = a[0]
    if cmd == 'queue':
        items, out = queue(a[a.index('--out') + 1] if '--out' in a else None)
        free = [x for x in items if not x.get('claimed_by_name')]
        print(f'{len(items)} pending ({len(free)} not claimed) -> {out}  [{"bot key" if bot_key() else "session token"}]')
    elif cmd == 'claim':
        print(claim(a[1], a[2] if len(a) > 2 else 300))
    elif cmd == 'release':
        print(release(a[1]))
    elif cmd == 'note':
        extra = json.load(open(a[a.index('--json') + 1], encoding='utf8')) if '--json' in a else {}
        pos = [x for i, x in enumerate(a[2:], 2) if not x.startswith('--') and (i < 2 or a[i - 1] != '--json')]
        conf = int(pos[0]) if pos and pos[0].isdigit() else None
        summ = pos[1] if len(pos) > 1 else (pos[0] if pos and conf is None else None)
        print(note(a[1], a[2], conf, summ, extra.get('reasons'), extra.get('evidence')))
    elif cmd == 'decide':
        rev, action = a[1], a[2]
        if action not in ('approve', 'reject'):
            raise SystemExit('approve 또는 reject')
        reason = None
        if action == 'reject':
            reason = next((x for x in a[3:] if not x.startswith('--')), '')
            if not reason.strip():
                raise SystemExit('거절에는 사유가 있어야 한다(한 줄, 여러 문제는 「 / 」로 잇는다)')
        if '--yes' not in a:
            print('보내지 않음(--yes 가 없다):', rev, json.dumps({'action': action, 'reason': reason}, ensure_ascii=False))
        else:
            print(decide(rev, action, reason))
    else:
        print(__doc__)
        sys.exit(1)
