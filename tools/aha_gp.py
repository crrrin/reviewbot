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
VERSION = 1
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


def scan(video, start, end, step=None, max_frames=80):
    cap = cv2.VideoCapture(video)
    dur = max(0.0, end - start)
    step = step or max(2.0, dur / max_frames)
    hits, n, t = [], 0, start + 1.0
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, f = cap.read()
        if ok:
            n += 1
            v, kind, where = match(f)
            if v >= THRESH:
                hits.append((round(t, 1), kind, round(v, 3), where))
        t += step
    cap.release()
    return {'present': len(hits) >= MIN_HITS, 'hits': hits, 'frames': n}


if __name__ == '__main__':
    r = scan(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]))
    print(r['present'], r['frames'], len(r['hits']), r['hits'][:12])
