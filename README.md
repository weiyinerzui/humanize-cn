# humanize-cn

中文 AIGC 检测 + 降AI改写工具链，针对朱雀、知网、维普、万方等检测系统。

## 功能

- detect.py   — 规则引擎检测（12+通用维度 + 7个朱雀专项维度）
- rewrite.py  — LLM改写引擎（Cloudflare Workers AI，支持 Qwen/Kimi/Llama 等）
- report.py   — 改写前后对比报告（评分变化、爆发度、套话数量）
- humanize.py — 统一入口，编排三阶段流水线

## 快速开始

### 配置

在 humanize-cn/ 目录下创建 .env 文件：

  QNAIGC_API_TOKEN=你的七牛云APIToken
  MODEL_ID=deepseek/deepseek-v4-pro

### 检测（不改写）

  python humanize.py 论文.txt --detect-only
  python humanize.py 论文.txt --detect-only -v   # 详细维度得分

### 改写（完整流程）

  python humanize.py 论文.txt
  python humanize.py 论文.txt --mode academic --intensity aggressive
  python humanize.py 论文.txt --rounds 2         # 两轮改写

输出文件：
  论文_rewritten.txt  — 改写正文
  论文_report.txt     — 对比报告

### stdin 模式

  echo "随着AI技术的发展..." | python humanize.py --mode general

### 参数说明

  --mode        academic（保留学术风格）| general（通用口语化）
  --intensity   conservative（保守，改20-30%）| aggressive（激进，全文重构）
  --rounds      改写轮数，1-3，默认1，评分<30自动提前停止
  --detect-only 只检测不改写
  --dry-run     打印prompt不调LLM
  -v/--verbose  详细输出

## 检测维度

### 通用维度（12个）
- 三段式套路（首先/其次/最后）
- 机械连接词（综上所述/值得注意的是/不难发现）
- 空洞宏大词（赋能/闭环/深度融合）
- AI高频词（助力/彰显/底层逻辑）
- 填充废话
- 模板句式（随着...的发展/在...背景下）
- 句长单调（爆发度 < 0.25）
- N-gram困惑度
- 情感平淡
- 过度犹豫语
- 学术套话（研究表明/具有重要意义）
- 结论段套话

### 朱雀专项维度（7个）
- ZQ_连续成果罗列（实测AIGC=0.95触发器）
- ZQ_通过实现模板（实测AIGC=0.99触发器）
- ZQ_完美总结段
- ZQ_功能描述套话
- ZQ_一是二是三是
- ZQ_AI动词
- ZQ_传导链描述

### 降权项（3个）
- 转折词（然而/不过/反而）
- 精确数字密度
- 高爆发度（句长变化大）

## 改写策略

学术模式（academic）：
1. 打破连续均匀句式（合并/插入转折）
2. 引入不完美表述（"在一定程度上"/"但仍存在..."）
3. 多样化句子长度
4. 替换机械连接词为具体化指代
5. 保留所有术语、数据、年份

通用模式（general）：
1. 打破均匀句式
2. 个人化表达（允许第一人称、口语连接词）
3. 去掉AI套话
4. 引入具体细节或类比
5. 不完美表达

## 自动强度

- detect 评分 < 60 → conservative（只改高风险句）
- detect 评分 ≥ 60 → aggressive（全文重构）

## 运行测试

  .venv\Scripts\python -m pytest tests/ -v

  # 含LLM真实调用（需QNAIGC_API_TOKEN且有配额）
  .venv\Scripts\python -m pytest tests/ -v --run-live

## 文件结构

  humanize-cn/
    detect.py          # M1 检测引擎
    rewrite.py         # M2 LLM改写引擎
    report.py          # M3 报告生成器
    humanize.py        # M4 统一入口
    ngram_model.py     # N-gram困惑度模型
    .env               # CF credentials（不提交git）
    patterns/
      patterns_base.json     # 通用词库
      patterns_zhuque.json   # 朱雀专项词库
    prompts/
      academic.txt     # 学术模式prompt
      general.txt      # 通用模式prompt
    tests/
      test_detect.py
      test_rewrite.py
      test_report.py
      test_integration.py

## 人工测试流程（P5）

1. 准备原始文本（500-3000字）
2. 运行: python humanize.py 原文.txt --mode academic
3. 打开 原文_rewritten.txt
4. 提交到朱雀/知网/维普
5. 如仍高于30%，运行: python humanize.py 原文_rewritten.txt --intensity aggressive
