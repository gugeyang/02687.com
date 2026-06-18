"""
keyword_validator.py — 02687.com 免费选词校验/长尾发现器（LMS 垂直）
=====================================================================
用 Google Autocomplete（联想词）接口——免费、无需 API Key、不限流——
确认关键词是否有真实搜索需求，并把短种子词「挖」成一批真实有人搜的长尾词。

为什么需要它（和 Keyword Planner 互补）：
  - Keyword Planner：给真实搜索量 + CPC，但要手动导 CSV，且只覆盖你想到的词。
  - Autocomplete：免费实时，能发现你没想到的真实长尾、验证"有没有人搜"，
    但没有搜索量数字、没有 CPC。
  两者配合：Autocomplete 发现/验证候选 → Keyword Planner 量化 CPC/搜索量。

对外接口：
  fetch_suggestions(query)        -> [真实联想词, ...]
  has_real_demand(keyword)        -> bool（该词是否有人搜）
  expand_to_real_keywords(seed)   -> [真实且仍在 LMS 领域内的长尾词, ...]

命令行：
  python tools/keyword_validator.py "best lms for"
  python tools/keyword_validator.py "self hosted lms" --expand
"""

import sys
import json
import time
import urllib.parse
import urllib.request

# Google 联想词接口（client=firefox 返回干净 JSON: ["q", ["s1","s2",...]]）
AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"

# 强锚词：LMS/EdTech 领域的具体平台/术语。含其一即可靠判定仍在本垂直领域内。
# 刻意不放 "best"/"online"/"training" 这类通用词——它们会让联想跑题。
STRONG_ANCHORS = [
    "lms", "learning management", "moodle", "canvas", "open edx", "blackboard",
    "schoology", "chamilo", "sakai", "totara", "talentlms", "docebo", "absorb",
    "learnupon", "litmos", "360learning", "thinkific", "teachable", "kajabi",
    "scorm", "xapi", "e-learning", "elearning", "saas lms", "self hosted",
    "self-hosted", "on-premise", "on premise", "white label", "corporate training",
    "course platform", "online course",
]


def fetch_suggestions(query, lang="en", timeout=10):
    """调用 Google Autocomplete，返回真实联想词列表（失败返回 []）。"""
    params = urllib.parse.urlencode({"client": "firefox", "hl": lang, "q": query})
    url = f"{AUTOCOMPLETE_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
            return [s for s in data[1] if isinstance(s, str)]
    except Exception as e:
        print(f"[Validator] 联想词请求失败 ({query}): {e}")
    return []


def has_real_demand(keyword):
    """该关键词是否有真实搜索需求：Google 联想里出现它（或其核心前缀）即视为有人在搜。"""
    kw = keyword.lower().strip()
    sugg = fetch_suggestions(kw)
    if not sugg:
        return False
    prefix = " ".join(kw.split()[:3])
    for s in sugg:
        sl = s.lower()
        if prefix in sl or sl in kw or kw in sl:
            return True
    return len(sugg) >= 3


def _is_relevant(suggestion, seed):
    """联想词是否仍在 LMS 垂直领域内：含强锚词，或与种子共享 >=2 个实义词。"""
    sl = suggestion.lower()
    if any(a in sl for a in STRONG_ANCHORS):
        return True
    seed_words = {w for w in seed.lower().split() if len(w) > 3}
    shared = sum(1 for w in seed_words if w in sl)
    return shared >= 2


def _stem_probes(seed):
    """从（可能很长的）种子词派生由长到短的探针。Google 联想基于短词干工作，
    长句几乎无联想，但前 3-4 个词通常能挖出一大批真实长尾。"""
    words = seed.split()
    probes = []

    def add(p):
        p = p.strip()
        if p and p not in probes:
            probes.append(p)

    add(seed)
    for n in (6, 5, 4, 3, 2):
        if n < len(words):
            add(" ".join(words[:n]))
    short = " ".join(words[:3])
    add(f"best {short}")
    add(f"{short} for")
    return probes


def expand_to_real_keywords(seed, max_keywords=12):
    """以种子词为起点，用 Google Autocomplete 挖成一批真实有人搜、且仍在 LMS 领域的长尾词。"""
    real = []
    seen = set()
    for p in _stem_probes(seed):
        for s in fetch_suggestions(p):
            key = s.lower().strip()
            if key in seen:
                continue
            if _is_relevant(s, seed):
                seen.add(key)
                real.append(s.strip())
        time.sleep(0.3)
        if len(real) >= max_keywords:
            break
    return real[:max_keywords]


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "best lms for"
    print(f"种子词: {q}")
    print(f"有真实搜索需求: {has_real_demand(q)}")
    print("真实长尾联想词（仍在 LMS 领域）:")
    for k in expand_to_real_keywords(q):
        print(f"  - {k}")
