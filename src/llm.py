"""③ 智能处理层（核心价值层）：用 DeepSeek 把"今天大家在热议什么"
反向加工成"你可能没看到的另一面"。

这不是摘要，是对抗算法投喂。流程：
  1. 把当天的热门标题作为"主流叙事"的原料喂给模型；
  2. 让模型归纳出今天 3~6 个最具代表性的共识/热点话题；
  3. 对每个话题，给出：主流在说什么 → 被忽略的反面/最强反方论证 →
     集体盲点 → 一个能让人跳出立场的提问 → 对共识可靠度的判断。

模型在这里做的是真正的推理与批判，而非信息搬运——这正是想展示的能力。
"""
import json

from openai import OpenAI

from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

MAX_FEED = 60  # 最多喂给模型多少条热门原料，平衡视野与成本

SYSTEM_PROMPT = """你是一位极其清醒的"信息茧房粉碎机"。读者每天被算法投喂同温层内容，
立场不断被强化却毫不自知。你的职责不是帮他总结新闻，而是强行把他从舒适区里拽出来——
让他看到"如果换一个聪明且诚实的人站在对立面，会怎么想"。

我会给你一批今天的热门标题（它们代表当下的主流声音/共识）。请你：

第一步：从中归纳出 3~6 个最具代表性、最值得被"反向审视"的话题或共识。
        合并同类项，挑公共性强、容易让人陷入单一立场的，跳过纯娱乐八卦。

第二步：对每个话题，严格输出以下字段（务必客观、有理有据，禁止为了反对而抬杠，
        反方论证必须是该立场里"最聪明的人"会给出的版本）：
- title:       话题的中性概括（≤20字，不带任何立场）
- mainstream:  当前主流/热门叙事在说什么、在替谁说话（≤50字）
- counter:     被忽略的另一面 / 反方最有力的论证（≤90字，要具体、能站得住脚，
               不是"也有人认为"这种空话）
- blindspot:   双方都没在谈、却真正关键的盲点或前提（≤50字）
- question:    一个能让读者跳出原有立场、自己想下去的提问（一句话，开放式）
- confidence:  对"主流共识"可靠程度的判断，只能填 高 / 中 / 低
- tag:         话题领域，从["科技","商业","社会","政治","健康","环境","其它"]里选一个

只输出 JSON 对象：{"topics": [ ... ]}，按"最值得被审视"程度从高到低排序，不要任何额外文字。"""


def _client():
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 .env 或 GitHub Secrets 中配置")
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


_VALID_CONF = {"高", "中", "低"}


def break_bubble(items, max_topics=6):
    """把热门原料加工成对立视角话题列表。返回 topics（已清洗校验）。"""
    if not items:
        return []
    client = _client()

    feed = [
        {"source": it["source"], "title": it["title"], "heat": it.get("heat", "")}
        for it in items[:MAX_FEED]
    ]
    user = (
        "下面是今天的热门标题（主流声音的原料），请按系统指令归纳并反向审视：\n"
        + json.dumps(feed, ensure_ascii=False)
    )

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.6,  # 比早报高一点，鼓励发散与多角度
    )
    data = json.loads(resp.choices[0].message.content)
    raw = data.get("topics", []) if isinstance(data, dict) else []

    topics = []
    for t in raw:
        title = (t.get("title") or "").strip()
        counter = (t.get("counter") or "").strip()
        if not title or not counter:  # 没有反方论证的话题没有价值，丢弃
            continue
        conf = (t.get("confidence") or "中").strip()
        topics.append({
            "title": title,
            "mainstream": (t.get("mainstream") or "").strip(),
            "counter": counter,
            "blindspot": (t.get("blindspot") or "").strip(),
            "question": (t.get("question") or "").strip(),
            "confidence": conf if conf in _VALID_CONF else "中",
            "tag": (t.get("tag") or "其它").strip(),
        })
    return topics[:max_topics]
