"""④ 渲染层：把对立视角话题渲染成企业微信群机器人 markdown 消息。

企业微信 markdown 支持有限：加粗 **、引用 >、字体颜色 <font color="...">、
标题 #，但不支持斜体、表格、图片、分隔线 ---。单条上限约 4096 字节，
所以这里按话题切段，过长时自动拆成多条返回。
"""
import datetime as dt

MAX_BYTES = 3800  # 留出余量，低于企业微信 4096 上限

_TAG_EMOJI = {
    "科技": "🔬", "商业": "💼", "社会": "👥", "政治": "🏛",
    "健康": "🩺", "环境": "🌍", "其它": "🧩",
}

# 企业微信 markdown 仅支持 info(绿)/comment(灰)/warning(橙红) 三种颜色
_CONF_BADGE = {
    "高": '<font color="info">🟢 共识可靠度：高</font>',
    "中": '<font color="comment">🟡 共识可靠度：中</font>',
    "低": '<font color="warning">🔴 共识可靠度：低（尤其值得警惕）</font>',
}


def _topic_md(t) -> str:
    emoji = _TAG_EMOJI.get(t.get("tag"), "🧩")
    lines = [f"**{emoji} {t['title']}**"]
    if t.get("mainstream"):
        lines.append(f"📣 主流在说：{t['mainstream']}")
    lines.append(f"🪞 你没看到的另一面：{t['counter']}")
    if t.get("blindspot"):
        lines.append(f"🕳 集体盲点：{t['blindspot']}")
    if t.get("question"):
        lines.append(f'❓ 想一想：<font color="comment">{t["question"]}</font>')
    lines.append(_CONF_BADGE.get(t.get("confidence"), _CONF_BADGE["中"]))
    return "\n".join(lines)


def build_messages(topics):
    """返回 list[str]：每条是一段企业微信 markdown，已按字节上限切好。"""
    stamp = dt.datetime.now().strftime("%Y-%m-%d")
    header = (
        f"# 🫧 茧房粉碎机 · {stamp}\n"
        "> 算法每天喂你想看的。这里只给你**不想看、但该看**的另一面。"
    )

    if not topics:
        return [header + "\n\n今天没归纳出值得反向审视的热点，难得的安静日 🍵"]

    footer = (
        f'<font color="comment">信息茧房粉碎机 · 共 {len(topics)} 个话题 · '
        '立场仅供破壁，非事实结论</font>'
    )

    blocks = [_topic_md(t) for t in topics]

    # 贪心装箱：尽量把多个话题塞进一条，超出 MAX_BYTES 就开新的一条
    messages, cur, first = [], header, True
    for blk in blocks:
        candidate = cur + "\n\n" + blk
        if len(candidate.encode("utf-8")) > MAX_BYTES and cur not in (header, ""):
            messages.append(cur)
            cur = blk  # 后续分段不再重复大标题，直接以话题开头
            first = False
        else:
            cur = candidate
    if cur:
        messages.append(cur)

    # footer 挂在最后一条；若挂上去超限就单独成一条
    if len((messages[-1] + "\n\n" + footer).encode("utf-8")) <= MAX_BYTES:
        messages[-1] = messages[-1] + "\n\n" + footer
    else:
        messages.append(footer)

    # 多条时给个 (1/N) 角标，便于阅读
    if len(messages) > 1:
        n = len(messages)
        messages = [f"<font color=\"comment\">({i}/{n})</font>\n" + m
                    for i, m in enumerate(messages, 1)]
    return messages
