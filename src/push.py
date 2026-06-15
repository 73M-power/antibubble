"""⑤ 推送层：把 markdown 消息发到企业微信群机器人 Webhook。

企业微信群机器人 markdown 单条上限约 4096 字节，所以 render 层会把内容
切成若干段，这里逐段发送。
"""
import requests

from .config import WECOM_WEBHOOK


def push(messages):
    """messages: list[str]，每段是一条企业微信 markdown 内容。"""
    if not WECOM_WEBHOOK:
        raise RuntimeError("缺少 WECOM_WEBHOOK，请在 .env 或 GitHub Secrets 中配置")
    if isinstance(messages, str):
        messages = [messages]
    for content in messages:
        _send_markdown(content)


def _send_markdown(content: str):
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    r = requests.post(WECOM_WEBHOOK, json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("errcode") not in (0, None):
        raise RuntimeError(f"企业微信推送失败: {data}")
    return data
