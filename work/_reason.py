"""work/_reason.py <rev> [kind ...]: auto.json 의 problem_items 를 영상 언어 거절 사유로 만든다(kind 를 주면 그것만)."""
import sys, json, os
sys.path.insert(0, 'E:/herta-review/tools')
import reasons
from paths import RUNS
rev, kinds = sys.argv[1], set(sys.argv[2:])
a = json.load(open(os.path.join(RUNS, rev, 'auto.json'), encoding='utf8'))
items = [x for x in a.get('problem_items', []) if not kinds or x['kind'] in kinds]
lang = reasons.detect_lang(rev)
print(lang)
r = reasons.render(items, lang)
print(r if isinstance(r, str) else ' / '.join(r))
