"""아하 보유 효과 판독. 배너 글이 없어서 HUD 아이콘으로 본다(사용자, 2026-11-15).

아하 보유 효과가 있으면 오른쪽 아래 웃음 포인트(스킬 포인트 「n / ✦✦✦✦」 바로 위) 아이콘이 하트로 바뀐다:
  보라 하트 IconElation_1151101(aha_heart_purple.png) 또는 붉은 하트 IconElation_1511(aha_heart_red.png).
없으면 주황 왕관 얼굴 아이콘이다. 왼쪽 행동 순서 줄의 웃음 포인트 칸도 같은 하트로 바뀐다.
→ 전투 구간 곳곳의 프레임에서 두 영역(오른쪽 아래 · 왼쪽 줄)을 하트 그림과 맞춰 본다(여러 크기, 투명 부분은 가림).

scan(video, start, end) -> {'present': bool, 'hits': [(t, kind, score, where)], 'frames': n}
python aha_gp.py <video> <start> <end>"""
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = 4
TURN_STEP = 0.33      # 아하 타임은 맨 위 칸에 1초 남짓 머문다
TURN_THRESH = 0.76    # 아하 타임 0.82~0.84, 아닌 때 0.69 이하(WarNfx8RjWs 139 · 384 · 627초)
TURN_SURE = 0.80
THRESH = 0.75         # 하트 있음 0.81~0.91, 없음 0.38~0.45(rev_as8f4x · c1tmz8 · mbzfb4 · zq6u9b / z47x8e · 11axy74)
MIN_HITS = 3
_tpl = None


def templates():
    global _tpl
    if _tpl is None:
        _tpl = []
        for kind, name in (('purple', 'aha_heart_purple.png'), ('red', 'aha_heart_red.png')):
            im = cv2.imread(os.path.join(HERE, name), cv2.IMREAD_UNCHANGED)
            ys, xs = np.where(im[:, :, 3] > 32)
            im = im[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            for h in range(18, 46, 2):          # 720p 에서 약 26~32px
                w = max(1, int(round(im.shape[1] * h / im.shape[0])))
                r = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
                _tpl.append((kind, h, r[:, :, :3].copy(), (r[:, :, 3] > 128).astype(np.uint8) * 255))
    return _tpl


def regions(f):
    H, W = f.shape[:2]
    s = 720.0 / H
    g = cv2.resize(f, (int(round(W * s)), 720)) if abs(s - 1) > 0.01 else f
    H, W = g.shape[:2]
    return [('sp_hud', g[int(0.70 * H):int(0.93 * H), int(0.62 * W):int(0.90 * W)]),
            ('action_order', g[int(0.03 * H):int(0.80 * H), 0:int(0.20 * W)])]


def match(f):
    """(가장 높은 점수, 종류, 영역)"""
    best = (0.0, None, None)
    for where, roi in regions(f):
        for kind, h, img, mask in templates():
            if roi.shape[0] < img.shape[0] or roi.shape[1] < img.shape[1]:
                continue
            r = cv2.matchTemplate(roi, img, cv2.TM_CCOEFF_NORMED, mask=mask)
            r = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
            v = float(r.max())
            if v > best[0]:
                best = (v, kind, where)
    return best


_turn = None


def turn_templates():
    """아하 타임에 행동 순서 맨 위(지금 행동하는 칸)에 올라온 아하 얼굴. 환락 캐릭터가 없는 팀(aha_turn_plain.png, 청록 칸)과
    있는 팀(aha_turn_elation.png, 붉은 체크 칸 + 카드)의 모양이 다르다(사용자 갈무리, 720p 크기)."""
    global _turn
    if _turn is None:
        _turn = []
        for kind in ('plain', 'elation', 'elation2'):
            im = cv2.imread(os.path.join(HERE, f'aha_turn_{kind}.png'))
            for s in (0.8, 0.9, 1.0, 1.1, 1.2):
                _turn.append((kind, cv2.resize(im, None, fx=s, fy=s)))
    return _turn


def bars(video, start, end, n=7):
    """위아래 검은 띠 (top, bottom). 21:9 녹화를 16:9 로 담은 영상(rev_1t5x4u8, 위아래 64px)은 게임이 아래로 밀려
    맨 위 칸이 ROI 밖으로 나간다. 전투 구간 몇 장의 중앙값으로 정한다."""
    cap = cv2.VideoCapture(video)
    tops, bots = [], []
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_MSEC, (start + (end - start) * (i + 0.5) / n) * 1000)
        ok, f = cap.read()
        if not ok:
            continue
        r = f.mean(axis=(1, 2))
        lit = np.where(r > 12)[0]
        if len(lit):
            tops.append(int(lit[0]))
            bots.append(int(lit[-1]) + 1)
    cap.release()
    if not tops:
        return 0, None
    top, bot = int(np.median(tops)), int(np.median(bots))
    return (top, bot) if top >= 8 and bot - top >= 200 else (0, None)


def turn_score(f, band=(0, None)):
    """맨 위 칸이 아하인지(점수, 종류). 검은 띠를 뺀 게임 화면을 720p 로 맞춰 왼쪽 위 칸만 본다."""
    if band[0] or band[1]:
        f = f[band[0]:band[1]]
    H, W = f.shape[:2]
    g = cv2.resize(f, (int(round(W * 720.0 / H)), 720)) if H != 720 else f
    roi = g[20:110, 0:300]      # 좌우 검은 띠로 게임이 밀린 영상(rev_58ddxb, +70px)도
    return max((float(cv2.matchTemplate(roi, tp, cv2.TM_CCOEFF_NORMED).max()), k) for k, tp in turn_templates())


def scan(video, start, end, step=None, max_frames=80, turn_step=TURN_STEP):
    """전투 구간을 한 번 차례로 읽으며 ① 웃음 포인트 하트(보유 효과 장착)를 max_frames 장쯤, ② 맨 위 칸 아하(아하 타임 = 실제 발동)를
    turn_step 초마다 본다. 하트가 보여도 아하 타임이 한 번도 안 왔으면 보유 효과를 쓴 것이 아니다(사용자, 2026-11-15)."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = max(0.0, end - start)
    step = step or max(2.0, dur / max_frames)
    hits, turns, n = [], [], 0
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start) * 1000)
    t, next_heart, next_turn = max(0.0, start), start + 1.0, start
    band = bars(video, start, end)
    k = 0
    while t < end:
        if not cap.grab():
            break
        t = (cap.get(cv2.CAP_PROP_POS_MSEC) or 0) / 1000.0
        k += 1
        if t < next_turn and t < next_heart:
            continue
        ok, f = cap.retrieve()
        if not ok:
            continue
        if t >= next_turn:
            next_turn = t + turn_step
            v, kind = turn_score(f, band)
            if v >= TURN_THRESH:
                turns.append((round(t, 2), kind, round(v, 3)))
        if t >= next_heart:
            next_heart = t + step
            n += 1
            v, kind, where = match(f)
            if v >= THRESH:
                hits.append((round(t, 1), kind, round(v, 3), where))
    cap.release()
    # 아하 타임: 맨 위 칸이 아하인 읽기가 2초 안에 두 번 이상이거나, 한 번이라도 아주 또렷하면 한 번으로 센다
    events = []
    for tt, kind, v in turns:
        if events and tt - events[-1]['end'] <= 2.0:
            events[-1]['end'] = tt
            events[-1]['n'] += 1
            events[-1]['best'] = max(events[-1]['best'], v)
        else:
            events.append({'start': tt, 'end': tt, 'n': 1, 'best': v, 'kind': kind})
    events = [e for e in events if e['n'] >= 2 or e['best'] >= TURN_SURE]
    return {'present': len(hits) >= MIN_HITS, 'hits': hits, 'frames': n, 'turns': events}


if __name__ == '__main__':
    r = scan(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]))
    print('heart', r['present'], r['frames'], len(r['hits']), r['hits'][:6])
    print('aha turns', r['turns'])
