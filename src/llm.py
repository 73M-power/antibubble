"""③ 智能处理层（核心价值层）：用 DeepSeek 把"今天大家在热议什么"
反向加工成"你可能没看到的另一面"，并尽量给反方找到真实出处。

两件事让它从"泛泛破壁"升级为"对症破壁"：
  · 定制化：读入 profile.yaml 的关注领域 + 既有立场，优先挑你关心的话题，
            并让反方直接挑战「你相信的判断」（命中时标 targets_stance）。
  · 取证  ：若配置了联网检索（search.py / TAVILY_API_KEY），对每个话题搜真实
            反方材料，让 counter 有据可依（counter_basis="联网取证"）；
            没配则如实标注 counter_basis="模型推理"，不假装可信。

流程：① 识别话题+反方 → ②(可选) 联网搜证 → ③(可选) 用证据修正反方。
"""
import json

from openai import OpenAI

from . import search
from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

MAX_FEED = 60  # 最多喂给模型多少条热门原料，平衡视野与成本

_TONE = {
    "gentle": "语气温和，像朋友善意提醒，不带攻击性。",
    "balanced": "语气中立克制，只摆事实与逻辑。",
    "sharp": "语气犀利、直击要害，但只对观点不对人，绝不抬杠或扣帽子。",
}

_VALID_CONF = {"高", "中", "低"}


def _client():
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 .env 或 GitHub Secrets 中配置")
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def _profile_block(profile) -> str:
    """把 profile.yaml 渲染成提示词里的「读者画像」段落。空 profile 返回通用说明。"""
    profile = profile or {}
    interests = [str(x).strip() for x in (profile.get("interests") or []) if str(x).strip()]
    stances = [str(x).strip() for x in (profile.get("stances") or []) if str(x).strip()]
    tone = _TONE.get((profile.get("tone") or "balanced").strip(), _TONE["balanced"])

    if not interests and not stances:
        return ("【读者画像】未提供，按通用模式：挑公共性最强、最容易让人陷入"
                f"单一立场的话题。语气：{tone}")

    lines = ["【读者画像】（请据此对症破壁，而非泛泛而谈）"]
    if interests:
        lines.append("· 关注领域（归纳话题时优先覆盖）：" + "、".join(interests))
    if stances:
        lines.append("· 既有立场【重点】：以下是读者目前相信/倾向的判断。请尽量挑出与之"
                     "相关的话题，并让 counter 直接、具体地反驳对应立场（给出最有力的反方），"
                     "不要泛泛而谈：")
        for i, s in enumerate(stances, 1):
            lines.append(f"    {i}. {s}")
        lines.append("  若某话题正是在挑战上述某条立场，把该立场原文填进 targets_stance 字段；否则留空。")
    lines.append("· 语气：" + tone)
    return "\n".join(lines)


def _system_prompt(profile) -> str:
    return f"""你是一位极其清醒的"信息茧房粉碎机"。读者每天被算法投喂同温层内容，
立场不断被强化却毫不自知。你的职责不是帮他总结新闻，而是把他从舒适区里拽出来——
让他看到"如果换一个聪明且诚实的人站在对立面，会怎么想"。

{_profile_block(profile)}

我会给你一批今天的热门条目（标题+来源+摘要，代表当下的主流声音）。请你：

第一步：归纳出 3~6 个最值得"反向审视"的话题/共识，合并同类项，跳过纯娱乐八卦，
        在满足读者关注领域与立场的前提下排序。

第二步：对每个话题严格输出以下字段（务必有理有据，反方必须是该立场里"最聪明的人"
        会给出的版本，禁止抬杠或稻草人）：
- title:          话题中性概括（≤20字，不带立场）
- mainstream:     当前主流叙事在说什么、在替谁说话（≤50字）
- counter:        被忽略的另一面 / 反方最有力论证（≤90字，要具体、能站住脚）
- blindspot:      双方都没谈却关键的盲点或前提（≤50字）
- question:       一个能让读者跳出立场、自己想下去的开放式提问（一句话）
- confidence:     对"主流共识"可靠程度的判断，只能填 高 / 中 / 低
- tag:            领域，从["科技","商业","社会","政治","健康","环境","其它"]选一个
- targets_stance: 若本话题在挑战读者某条既有立场，填该立场原文；否则填 ""
- search_query:   一个用于联网检索"反驳/质疑该主流共识"的检索式（英文优先，≤12词），
                  以便后续给反方取证

只输出 JSON 对象：{{"topics": [ ... ]}}，按"最值得被审视"程度从高到低排序，不要任何额外文字。"""


_GROUND_PROMPT = """你在给一批"反方论证"做事实取证。我会给你若干话题，每个含：
原本的 counter、以及联网搜到的真实材料片段(evidence)。对每个话题：
1) 用 evidence 支撑或修正 counter，使其有据可依、更具体（≤100字）；
2) 从 evidence 里选出最多 2 条「真正支持反方」的材料，回填其 index；
3) 若 evidence 其实并不支持反方，诚实把 grounded 设为 false，并保留原 counter。

只输出 JSON：{"items":[{"index":int,"counter":str,"grounded":bool,"sources":[evidence的index,...]}]}"""


def _identify_topics(client, items, profile, max_topics):
    feed = [
        {
            "i": idx,
            "source": it["source"],
            "title": it["title"],
            "summary": (it.get("summary") or "")[:240],
        }
        for idx, it in enumerate(items[:MAX_FEED])
    ]
    user = ("下面是今天的热门条目（主流声音的原料），请按系统指令归纳并反向审视：\n"
            + json.dumps(feed, ensure_ascii=False))
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _system_prompt(profile)},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.6,
    )
    data = json.loads(resp.choices[0].message.content)
    raw = data.get("topics", []) if isinstance(data, dict) else []

    topics = []
    for t in raw:
        title = (t.get("title") or "").strip()
        counter = (t.get("counter") or "").strip()
        if not title or not counter:
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
            "targets_stance": (t.get("targets_stance") or "").strip(),
            "search_query": (t.get("search_query") or title).strip(),
            "counter_basis": "模型推理",  # 默认未取证；取证成功后改写
            "sources": [],
        })
    return topics[:max_topics]


def _ground_topics(client, topics):
    """对每个话题联网搜证，再让模型用证据修正 counter。原地更新 topics。"""
    payload, evidence_pool = [], {}
    for ti, t in enumerate(topics):
        hits = search.search(t["search_query"], max_results=3)
        if not hits:
            continue
        ev = [{"index": ei, "title": h["title"], "snippet": h["snippet"]}
              for ei, h in enumerate(hits)]
        evidence_pool[ti] = hits
        payload.append({"index": ti, "counter": t["counter"], "evidence": ev})

    if not payload:  # 全都没搜到，保持"模型推理"
        return

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _GROUND_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    data = json.loads(resp.choices[0].message.content)
    for item in (data.get("items", []) if isinstance(data, dict) else []):
        ti = item.get("index")
        if not isinstance(ti, int) or ti not in evidence_pool:
            continue
        if not item.get("grounded"):
            continue
        hits = evidence_pool[ti]
        srcs = []
        for ei in (item.get("sources") or [])[:2]:
            if isinstance(ei, int) and 0 <= ei < len(hits):
                srcs.append({"title": hits[ei]["title"], "url": hits[ei]["url"]})
        topics[ti]["counter"] = (item.get("counter") or topics[ti]["counter"]).strip()
        topics[ti]["counter_basis"] = "联网取证"
        topics[ti]["sources"] = srcs


def break_bubble(items, max_topics=6, profile=None):
    """把热门原料加工成对立视角话题列表。返回 topics（已清洗校验）。"""
    if not items:
        return []
    client = _client()
    topics = _identify_topics(client, items, profile, max_topics)
    if topics and search.enabled():
        try:
            _ground_topics(client, topics)
        except Exception as e:  # noqa: BLE001 — 取证失败不影响已生成的反方
            print(f"  ✗ 取证环节失败（已忽略）: {e}")
    return topics
