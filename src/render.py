"""④ 渲染层：把对立视角话题渲染成飞书"对比卡片"。

每个话题做成"主流 vs 另一面"的视觉对照，并诚实标注：
  · 🎯 这条是否直接挑战了你的既有立场（定制化的可见证据）；
  · 反方是「🔎 联网取证」还是「💭 模型推理」（可信度的可见证据）。
"""
import datetime as dt

_TAG_EMOJI = {
    "科技": "🔬", "商业": "💼", "社会": "👥", "政治": "🏛",
    "健康": "🩺", "环境": "🌍", "其它": "🧩",
}

_CONF_BADGE = {
    "高": "🟢 共识可靠度：高",
    "中": "🟡 共识可靠度：中",
    "低": "🔴 共识可靠度：低（尤其值得警惕）",
}


def _basis_badge(t) -> str:
    if t.get("counter_basis") == "联网取证":
        srcs = t.get("sources") or []
        if srcs:
            links = " · ".join(f"[{s['title'][:18]}]({s['url']})" for s in srcs)
            return f"🔎 反方有据：{links}"
        return "🔎 反方经联网取证"
    return "💭 反方为模型推理，请自行核实"


def _topic_md(t) -> str:
    emoji = _TAG_EMOJI.get(t.get("tag"), "🧩")
    lines = [f"**{emoji} {t['title']}**"]
    if t.get("targets_stance"):
        lines.append(f"🎯 **直击你的立场**：「{t['targets_stance']}」")
    if t.get("mainstream"):
        lines.append(f"📣 主流在说：{t['mainstream']}")
    lines.append(f"🪞 你没看到的另一面：{t['counter']}")
    if t.get("blindspot"):
        lines.append(f"🕳 集体盲点：{t['blindspot']}")
    if t.get("question"):
        lines.append(f"❓ 想一想：*{t['question']}*")
    lines.append(_CONF_BADGE.get(t.get("confidence"), _CONF_BADGE["中"]))
    lines.append(_basis_badge(t))
    return "\n".join(lines)


def build_card(topics):
    stamp = dt.datetime.now().strftime("%Y-%m-%d")

    elements = []
    if not topics:
        elements.append({
            "tag": "markdown",
            "content": "今天没归纳出值得反向审视的热点，难得的安静日 🍵",
        })
    else:
        elements.append({
            "tag": "markdown",
            "content": "> 算法每天喂你想看的。这里只给你**不想看、但该看**的另一面。",
        })
        elements.append({"tag": "hr"})
        for t in topics:
            elements.append({"tag": "markdown", "content": _topic_md(t)})
            elements.append({"tag": "hr"})
        if elements and elements[-1].get("tag") == "hr":
            elements.pop()

    elements.append({
        "tag": "note",
        "elements": [{
            "tag": "plain_text",
            "content": f"信息茧房粉碎机 · 共 {len(topics)} 个话题 · 立场仅供破壁，非事实结论",
        }],
    })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"🫧 茧房粉碎机 · {stamp}"},
                "template": "purple",
            },
            "elements": elements,
        },
    }
