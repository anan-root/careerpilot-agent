"""Shared recruitment platform labels and aliases."""

from __future__ import annotations

PLATFORM_LABELS: dict[str, str] = {
    "boss": "BOSS直聘",
    "boss_drission": "BOSS直聘（登录浏览器）",
    "boss_cookie": "BOSS直聘（Cookie）",
    "zhilian": "智联招聘",
    "51job": "前程无忧",
    "liepin": "猎聘",
    "lagou": "拉勾",
    "nowcoder": "牛客网",
    "yingjiesheng": "应届生",
    "guopin": "国聘网",
    "dingxiang": "丁香人才网",
    "jobonline": "就业在线",
    "curated": "本地兜底",
    "manual": "手动导入",
}

PLATFORM_ORDER: list[str] = [
    "boss",
    "zhilian",
    "51job",
    "liepin",
    "lagou",
    "nowcoder",
    "yingjiesheng",
    "guopin",
    "dingxiang",
    "jobonline",
    "curated",
]

DEFAULT_PLATFORM_CODES: list[str] = ["boss", "zhilian", "51job"]

PLATFORM_ALIASES: dict[str, str] = {
    "boss": "boss",
    "Boss": "boss",
    "BOSS": "boss",
    "boss直聘": "boss",
    "BOSS直聘": "boss",
    "智联": "zhilian",
    "智联招聘": "zhilian",
    "zhaopin": "zhilian",
    "51job": "51job",
    "前程无忧": "51job",
    "猎聘": "liepin",
    "liepin": "liepin",
    "拉勾": "lagou",
    "拉钩": "lagou",
    "lagou": "lagou",
    "牛客": "nowcoder",
    "牛客网": "nowcoder",
    "nowcoder": "nowcoder",
    "应届生": "yingjiesheng",
    "应届生求职": "yingjiesheng",
    "yingjiesheng": "yingjiesheng",
    "国聘": "guopin",
    "国聘网": "guopin",
    "guopin": "guopin",
    "丁香": "dingxiang",
    "丁香人才": "dingxiang",
    "丁香人才网": "dingxiang",
    "dxy": "dingxiang",
    "jobmd": "dingxiang",
    "就业在线": "jobonline",
    "国家就业在线": "jobonline",
    "jobonline": "jobonline",
}


def platform_label(code: str) -> str:
    return PLATFORM_LABELS.get(str(code), str(code))


def platform_labels(codes: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    return [platform_label(code) for code in (codes or [])]


def platform_label_text(codes: list[str] | tuple[str, ...] | set[str] | None) -> str:
    labels = platform_labels(codes)
    return "、".join(labels) if labels else "全部"


def normalize_platform(value: str) -> str:
    text = str(value or "").strip()
    return PLATFORM_ALIASES.get(text, text)


def normalize_platforms(values: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        code = normalize_platform(str(value))
        if code and code not in result:
            result.append(code)
    return result
