import sys
sys.path.insert(0, '.')
from detect import detect

text = open('test/paper.txt', 'r', encoding='utf-8').read()
paras = text.split('\n')
max_score = 0
worst_para = ''

for p in paras:
    if len(p) > 300:
        score = detect(p).final_score
        if score > max_score:
            max_score = score
            worst_para = p

print(f'Worst score: {max_score}, len: {len(worst_para)}')
open('test/worst_para.txt', 'w', encoding='utf-8').write(worst_para)
