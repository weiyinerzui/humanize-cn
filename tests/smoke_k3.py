#!/usr/bin/env python3
"""Live API smoke test: Adversarial Beam v2.0 K=3 full pipeline."""
import sys
sys.path.insert(0, "/mnt/e/workspace/github/humanize-cn")
from humanize import pipeline

text = """人工智能技术的快速发展正在深刻地重塑全球产业格局。从智能制造到智慧医疗，从自动驾驶到金融风控，AI应用已经渗透到社会生产的各个层面。值得注意的是，这种技术变革不仅带来了效率的显著提升，同时也引发了对就业结构、数据隐私和伦理边界等深层次问题的广泛讨论。在数字化转型的大背景下，企业必须积极拥抱人工智能技术，通过构建智能化运营体系来实现降本增效。与此同时，政府监管部门也需要制定相应的政策框架，以确保技术创新与社会福祉的平衡发展。总而言之，人工智能的发展既充满机遇也面临挑战，需要产学研各界协同努力。"""

result = pipeline(text, mode="academic", beam_k=3, verbose=False)

before = result["detect_before"].final_score
after = result["detect_after"].final_score

print("=" * 60)
print("ORIGINAL:", result["original"][:200])
print()
print("REWRITTEN:", result["rewritten"][:600])
print()
print("Score: %d -> %d (delta: %d)" % (before, after, before - after))
print("Model:", result["rewrite_result"].get("model", "unknown"))