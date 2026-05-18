#!/usr/bin/env python3
"""
batch_humanize.py - 自动分批处理长文本/长论文的封装脚本

特点:
1. 自动根据空白行/段落将超长文本切分为合理的区块 (例如 1000~1500 字/块)
2. 支持断点续传 (Checkpoint)，如果中途 API 熔断或手动停止，下次运行可直接继续
3. 自动合并最终结果
"""

import os
import sys
import json
import time
import argparse
from humanize import pipeline
from text_utils import split_sentences

def chunk_text(text, max_len=1500):
    """
    按段落拆分文本。
    如果单个段落超过 max_len，则按句子进一步拆分。
    """
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        if len(current_chunk) + len(p) < max_len:
            current_chunk += p + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            if len(p) >= max_len:
                # 段落本身超长，按句拆分
                sents = split_sentences(p)
                sub_chunk = ""
                for s in sents:
                    if len(sub_chunk) + len(s) < max_len:
                        sub_chunk += s
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk.strip())
                        sub_chunk = s
                current_chunk = sub_chunk + "\n\n"
            else:
                current_chunk = p + "\n\n"
                
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def main():
    parser = argparse.ArgumentParser(description='Batch processing for long documents.')
    parser.add_argument('file', help='Input file to process (.txt)')
    parser.add_argument('--mode', choices=['academic', 'general'], default='academic')
    parser.add_argument('--rounds', type=int, default=2, help='Pipeline rounds per chunk')
    parser.add_argument('--beam-k', type=int, default=3, help='Beam search width per chunk')
    args = parser.parse_args()

    input_file = args.file
    if not os.path.exists(input_file):
        print(f"File not found: {input_file}")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()

    chunks = chunk_text(text, max_len=1500)
    print(f"Document split into {len(chunks)} chunks.")

    checkpoint_file = f"{input_file}.checkpoint.json"
    results = {}
    
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        print(f"Resuming from checkpoint: {len(results)} chunks already processed.")

    final_chunks = []
    for i, chunk in enumerate(chunks):
        chunk_id = str(i)
        if chunk_id in results:
            final_chunks.append(results[chunk_id])
            continue
            
        print(f"\n{'='*60}\nProcessing Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...\n{'='*60}")
        try:
            res = pipeline(chunk, mode=args.mode, rounds=args.rounds, beam_k=args.beam_k)
            processed = res['rewritten']
            results[chunk_id] = processed
            final_chunks.append(processed)
            
            # Save checkpoint
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
            # Sleep to avoid hitting API rate limits continuously
            time.sleep(2)
        except Exception as e:
            print(f"Error processing chunk {i+1}: {e}")
            print("Stopping to preserve progress. Rerun to resume.")
            sys.exit(1)

    # All done
    out_file = input_file.replace('.txt', '_batch_rewritten.txt')
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(final_chunks))
        
    print(f"\nAll chunks processed successfully! Saved to {out_file}")
    
    # Optionally remove checkpoint
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

if __name__ == '__main__':
    main()
