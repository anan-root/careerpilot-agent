"""Controlled BOSS chat-page outreach helpers."""

from __future__ import annotations

import time
from typing import Any

from crawlers.boss_drission import _create_page, _login_state

CHAT_INPUT_SELECTORS = (
    "css:textarea",
    "css:input[placeholder*='输入']",
    "css:textarea[placeholder*='输入']",
    "css:[contenteditable='true']",
    "css:[class*='chat-input'] textarea",
    "css:[class*='input-area'] textarea",
    "css:[class*='editor'] [contenteditable='true']",
)

SEND_BUTTON_SELECTORS = (
    "css:button[class*='send']",
    "css:[class*='send-btn']",
    "css:[class*='submit']",
)

MANUAL_TEXT_HINTS = ("登录", "验证码", "滑块", "短信验证", "请完成验证")


def check_boss_chat(job_or_url: dict | str, *, dry_run: bool = True) -> dict:
    """Open a BOSS chat URL and check whether a message can be edited."""
    url = _chat_url(job_or_url)
    if not url:
        return _result("missing_chat_url", message="当前岗位没有沟通链接。")

    page_result = _open_chat(url)
    if page_result.get("status") != "opened":
        return page_result
    page = page_result["page"]

    state = _page_state(page)
    if state != "ready":
        return _result("blocked_manual_required", platform_url=url, message="页面需要你先处理后再继续。")

    input_ele = _find_input(page)
    if not input_ele:
        return _result("blocked_manual_required", platform_url=url, message="没有找到可编辑输入区。")
    return _result("dry_run_ok" if dry_run else "ready", platform_url=url, message="已找到可编辑输入区，尚未发送。")


def send_boss_message(
    job_or_url: dict | str,
    message_text: str,
    *,
    confirm_send: bool = False,
    dry_run: bool = False,
) -> dict:
    """Send one confirmed message on a BOSS chat page."""
    url = _chat_url(job_or_url)
    message = str(message_text or "").strip()
    if not url:
        return _result("missing_chat_url", message="当前岗位没有沟通链接。")
    if not message:
        return _result("empty_message", platform_url=url, message="发送文本为空。")
    if not confirm_send:
        return _result("confirm_required", platform_url=url, message="需要用户确认后才会发送。")
    if dry_run:
        return check_boss_chat(url, dry_run=True)

    page_result = _open_chat(url)
    if page_result.get("status") != "opened":
        return page_result
    page = page_result["page"]

    state = _page_state(page)
    if state != "ready":
        return _result("blocked_manual_required", platform_url=url, message="页面需要你先处理后再继续。")

    input_ele = _find_input(page)
    if not input_ele:
        return _result("blocked_manual_required", platform_url=url, message="没有找到可编辑输入区。")
    try:
        input_ele.click()
        _clear_input(input_ele)
        input_ele.input(message)
        time.sleep(0.5)
    except Exception as exc:
        return _result("blocked_manual_required", platform_url=url, error=str(exc), message="写入输入区失败。")

    send_button = _find_send_button(page)
    if not send_button:
        return _result("blocked_manual_required", platform_url=url, message="没有找到明确的发送按钮。")
    try:
        send_button.click()
        time.sleep(1.0)
        return _result("sent", platform_url=url, message="已点击发送。")
    except Exception as exc:
        return _result("blocked_manual_required", platform_url=url, error=str(exc), message="点击发送失败。")


def read_boss_chat_text(job_or_url: dict | str, limit: int = 2000) -> dict:
    """Read visible chat-page text for user-confirmed reply drafting."""
    url = _chat_url(job_or_url)
    if not url:
        return _result("missing_chat_url", message="当前岗位没有沟通链接。")
    page_result = _open_chat(url)
    if page_result.get("status") != "opened":
        return page_result
    page = page_result["page"]
    state = _page_state(page)
    if state != "ready":
        return _result("blocked_manual_required", platform_url=url, message="页面需要你先处理后再继续。")
    try:
        text = str(getattr(page, "html", "") or "")
    except Exception:
        text = ""
    return _result("read_ok", platform_url=url, message="已读取当前页面文本。", chat_text=text[: int(limit)])


def _open_chat(url: str) -> dict:
    page = _create_page()
    if page is None:
        return _result("browser_unavailable", platform_url=url, message="无法启动 BOSS 浏览器。")
    try:
        page.get(url)
        time.sleep(2.0)
    except Exception as exc:
        return _result("open_failed", platform_url=url, error=str(exc), message="打开沟通页面失败。")
    return {"status": "opened", "page": page, "platform_url": url}


def _page_state(page: Any) -> str:
    try:
        state = _login_state(page)
        if state == "logged_out":
            return "manual_required"
        html = str(getattr(page, "html", "") or "")[:6000]
        title = str(getattr(page, "title", "") or "")
        if any(hint in html or hint in title for hint in MANUAL_TEXT_HINTS):
            return "manual_required"
        return "ready"
    except Exception:
        return "manual_required"


def _find_input(page: Any):
    for selector in CHAT_INPUT_SELECTORS:
        try:
            ele = page.ele(selector, timeout=0.8)
            if ele:
                return ele
        except Exception:
            continue
    return None


def _find_send_button(page: Any):
    for selector in SEND_BUTTON_SELECTORS:
        try:
            ele = page.ele(selector, timeout=0.8)
            if ele:
                return ele
        except Exception:
            continue
    try:
        return page.ele("text:发送", timeout=0.8)
    except Exception:
        return None


def _clear_input(ele: Any) -> None:
    for method_name in ("clear", "clear_text"):
        method = getattr(ele, method_name, None)
        if callable(method):
            try:
                method()
                return
            except Exception:
                continue


def _chat_url(job_or_url: dict | str) -> str:
    if isinstance(job_or_url, str):
        return job_or_url.strip()
    if isinstance(job_or_url, dict):
        return str(job_or_url.get("chat_url") or "").strip()
    return ""


def _result(status: str, *, platform_url: str = "", message: str = "", error: str = "", chat_text: str = "") -> dict:
    return {
        "status": status,
        "platform_url": platform_url,
        "message": message,
        "error": error,
        "chat_text": chat_text,
    }
