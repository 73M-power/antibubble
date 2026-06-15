"""编排入口：采集主流声音 → LLM 反向加工 → 去重 → 渲染 → 推送。

用法：
    python -m src.main                # 完整跑一遍并推送到企业微信
    python -m src.main --dry-run      # 跑全链路但不推送，打印消息文本
    python -m src.main --collect-only # 只测采集（不调 LLM、不推送）
"""
import argparse
import sys

# Windows 控制台默认 GBK，强制 UTF-8 以免 emoji/中文输出报错
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from . import collect, dedup, llm, render, push


def run(dry_run=False, collect_only=False):
    settings, sources = collect.load_config()
    lookback = settings.get("lookback_hours", 30)
    max_topics = settings.get("max_topics", 6)

    print("① 采集主流声音中…")
    items, errors = collect.collect_all(sources, lookback)
    print(f"   采集到 {len(items)} 条热门原料，失败源 {len(errors)} 个")

    if collect_only:
        for it in items[:40]:
            heat = f" [{it['heat']}]" if it.get("heat") else ""
            print(f"   {it['title']}{heat}  <{it['source']}>")
        return 0

    if not items:
        print("   没采到任何原料，跳过（不推送）。")
        return 0

    print("② DeepSeek 反向加工中（识别共识 → 找最强反方 → 戳破盲点）…")
    topics = llm.break_bubble(items, max_topics)
    print(f"   归纳出 {len(topics)} 个话题")

    print("③ 去重中（同一话题不重复打扰）…")
    seen = dedup.load_seen()
    fresh = [t for t in topics if dedup.topic_id(t["title"]) not in seen]
    print(f"   新话题 {len(fresh)} 个（已过滤 {len(topics) - len(fresh)} 个近期已推）")

    if not fresh:
        print("   今日话题都近期推过，静默退出。")
        return 0

    print("④ 渲染对比消息…")
    messages = render.build_messages(fresh)

    if dry_run:
        for i, m in enumerate(messages, 1):
            print(f"\n----- 第 {i}/{len(messages)} 条 -----\n{m}")
        print("\n(--dry-run：未推送，未更新状态库)")
        return 0

    print(f"⑤ 推送到企业微信（{len(messages)} 条）…")
    push.push(messages)
    dedup.mark_seen([dedup.topic_id(t["title"]) for t in fresh], seen)
    print("   ✓ 推送完成，状态库已更新")
    return 0


def main():
    p = argparse.ArgumentParser(description="信息茧房粉碎机 · 每日反向视角推送")
    p.add_argument("--dry-run", action="store_true", help="跑全链路但不推送")
    p.add_argument("--collect-only", action="store_true", help="只测采集层")
    args = p.parse_args()
    try:
        return run(dry_run=args.dry_run, collect_only=args.collect_only)
    except Exception as e:  # noqa: BLE001
        print(f"运行失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
