"""
content_reviewer.py — 02687.com AI 内容质量审核器
===================================================
用独立的 Gemini 调用扮演 Google Search Quality Rater，
对生成的文章进行7维度打分，返回 pass/fail + 详细反馈。

调用方式：
    from content_reviewer import ContentReviewer
    reviewer = ContentReviewer(client)
    result = reviewer.audit(content, keyword)
    if result["pass"]:
        # 发布
"""

import sys
import io
import re
import json
import time

# 审核通过分数线
PASS_SCORE = 75

# 禁止项（直接返回 False，不进入打分）
FORBIDDEN_PATTERNS = [
    (r'[\u4e00-\u9fff]',                   "包含中文字符"),
    (r'<!-- ADSENSE_INSERT_HERE -->',       "包含 ADSENSE 占位符（HCU 风险）"),
    (r'author:\s*"EdTech Architect"',      "author 字段错误（应为 Alex Chen）"),
    (r'Lorem ipsum',                       "包含 Lorem Ipsum 占位文字"),
    (r'John Doe',                          "包含违规人名 John Doe"),
]

AUDIT_PROMPT_TEMPLATE = """
You are a strict Google Search Quality Rater and an expert in detecting AI-generated content.
Your task is to evaluate the following blog article for publication on an EdTech infrastructure site (02687.com).

TARGET KEYWORD: "{keyword}"

ARTICLE CONTENT:
---
{content}
---

EVALUATION CRITERIA — Score each dimension and be CRITICAL. Your job is to find problems, not praise.

1. DE-AI-IZATION (0-25 pts)
   Deduct points for: generic openers ("In today's digital era", "In the ever-evolving landscape"),
   wishy-washy conclusions ("it depends on your use case" without specifics), overly balanced
   perspectives with no clear stance, formulaic sentence structures repeated throughout.
   Full score = reads like a practitioner sharing real experience, not an AI summarizing a topic.

2. E-E-A-T EXPERIENCE SIGNALS (0-25 pts)
   Deduct points if: no first-person experience ("I've seen", "I spent X hours debugging"),
   no specific failure scenarios with real error messages or log output, no concrete numbers
   (time spent, user counts, memory sizes), no admission of mistakes or wrong assumptions.
   Full score = reader believes a real person with real scars wrote this.

3. GOOGLE HCU COMPLIANCE (0-20 pts)
   Deduct points if: the article is "about" the topic rather than solving the specific search intent,
   if a reader searching "{keyword}" would leave unsatisfied, if it could be summarized as
   "here is a balanced overview" instead of "here is exactly how to do this".
   Full score = directly and completely answers what someone searching "{keyword}" needs.

4. TECHNICAL DEPTH (0-15 pts)
   Deduct points for: code blocks that are pseudocode or incomplete, configuration values that are
   obviously placeholders without explanation, H2 headings that contain no keywords,
   missing explanation of WHY a configuration choice was made.
   Full score = a sysadmin could follow this article and reproduce the result.

5. STRUCTURE QUALITY (0-10 pts)
   Deduct points if: fewer than 4 H2 headings, no "Gotchas" or troubleshooting section,
   internal links to other articles are missing or are at the end in a list (not woven into text),
   article is under 900 words.
   Full score = follows all structural SEO requirements.

6. OVERALL PUBLISHABILITY (0-5 pts)
   Your holistic assessment: would you be comfortable if this article ranked #1 on Google
   for "{keyword}"? Does it represent genuine expertise?

RESPONSE FORMAT — Return ONLY valid JSON, no markdown wrapper, no explanation outside the JSON:
{{
  "score": <integer 0-100>,
  "pass": <true if score >= {pass_score}, false otherwise>,
  "dimension_scores": {{
    "de_ai": <0-25>,
    "eeat": <0-25>,
    "hcu": <0-20>,
    "technical_depth": <0-15>,
    "structure": <0-10>,
    "overall": <0-5>
  }},
  "critical_issues": [
    "<specific problem 1>",
    "<specific problem 2>"
  ],
  "rewrite_instructions": "<Concrete, actionable instructions for rewriting. Be specific: name the section, quote the problematic sentence, and say exactly what to replace it with or what to add.>"
}}
"""


BUYER_GUIDE_AUDIT_PROMPT = """
You are a strict Google Search Quality Rater and an expert in detecting AI-generated, low-value
"best X" affiliate content. You are evaluating an LMS BUYER'S GUIDE / COMPARISON article for
publication on 02687.com. This is NOT a technical tutorial — judge it as a buyer would.

TARGET KEYWORD: "{keyword}"

ARTICLE CONTENT:
---
{content}
---

EVALUATION CRITERIA — Score each dimension and be CRITICAL. Your job is to find problems, not praise.

1. DE-AI-IZATION (0-20 pts)
   Deduct for: generic openers, formulaic structure, only-positive product descriptions that read
   as sponsored, vague "it depends" endings with no real recommendation.
   Full score = reads like a real consultant giving honest, opinionated buying advice.

2. FIRST-HAND EVALUATION SIGNALS / E-E-A-T (0-20 pts)
   Deduct if: no first-person evaluation experience ("when I deployed X for a client", "I'd avoid Y because"),
   no specific scenarios, no sense the author actually used these products.
   Full score = reader believes a real practitioner who has used these tools wrote this.

3. BUYER-INTENT SATISFACTION / HCU (0-20 pts)
   Deduct if: a reader searching "{keyword}" still wouldn't know which to choose after reading,
   if it's a generic overview rather than decision help.
   Full score = directly helps the reader DECIDE for their situation.

4. COMPARISON DEPTH & ACCURACY (0-20 pts)
   Deduct if: fewer than 5 real products compared, missing a comparison TABLE, products covered
   with only pros and no cons, OR any sign of FABRICATED products/prices/statistics/testimonials.
   Full score = 5+ real LMS products, balanced pros/cons each, a clear comparison table, no invented facts.

5. DECISION GUIDANCE (0-10 pts)
   Deduct if: no clear winner named, no by-scenario recommendations (budget/team size/industry).
   Full score = confident, specific recommendations for different buyer situations.

6. STRUCTURE QUALITY (0-10 pts)
   Deduct if: no comparison table, no FAQ section, fewer than 4 headings, internal links missing.
   Full score = comparison table + per-product sections + FAQ + woven internal links.

RESPONSE FORMAT — Return ONLY valid JSON, no markdown wrapper, no explanation outside the JSON:
{{
  "score": <integer 0-100>,
  "pass": <true if score >= {pass_score}, false otherwise>,
  "dimension_scores": {{
    "de_ai": <0-20>,
    "eeat": <0-20>,
    "hcu": <0-20>,
    "comparison_depth": <0-20>,
    "decision_guidance": <0-10>,
    "structure": <0-10>
  }},
  "critical_issues": [
    "<specific problem 1>",
    "<specific problem 2>"
  ],
  "rewrite_instructions": "<Concrete, actionable instructions for rewriting. Be specific: name the section, quote the problematic sentence, and say exactly what to replace it with or what to add.>"
}}
"""


class ContentReviewer:
    """
    AI 内容审核器。
    使用独立的 Gemini 调用，以 Google Quality Rater 视角审核文章。
    """

    def __init__(self, client, model_name="gemini-2.0-flash"):
        self.client = client
        self.model_name = model_name
        self.fallback_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

    def _check_forbidden(self, content):
        """检测禁止项，命中任何一条直接返回失败原因"""
        for pattern, reason in FORBIDDEN_PATTERNS:
            if re.search(pattern, content):
                return reason
        return None

    def _extract_json(self, raw_text):
        """从模型输出中提取 JSON，容错处理 markdown 包裹"""
        text = raw_text.strip()
        # 移除可能的 ```json ... ``` 包裹
        text = re.sub(r'^```(?:json)?\s*\n', '', text)
        text = re.sub(r'\n```\s*$', '', text)
        text = text.strip()

        # 尝试找到 { ... } 块
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        return json.loads(text)

    def audit(self, content, keyword, content_type="technical", verbose=True):
        """
        对文章内容进行审核。

        content_type: "technical"（技术教程）或 "buyer_guide"（LMS 买家指南/对比），
                      决定用哪套评分标准。

        Returns:
            dict: {
                "pass": bool,
                "score": int,
                "dimension_scores": dict,
                "critical_issues": list,
                "rewrite_instructions": str,
                "forbidden_hit": str or None
            }
        """
        if verbose:
            print("\n[Reviewer] 开始质量审核...")

        # Step 1: 禁止项快速检测
        forbidden = self._check_forbidden(content)
        if forbidden:
            print(f"[Reviewer] ❌ 禁止项命中，直接拒绝: {forbidden}")
            return {
                "pass": False,
                "score": 0,
                "forbidden_hit": forbidden,
                "critical_issues": [forbidden],
                "rewrite_instructions": f"必须修复禁止项: {forbidden}",
                "dimension_scores": {}
            }

        # Step 2: 调用 Gemini 审核（按内容类型选评分标准）
        template = BUYER_GUIDE_AUDIT_PROMPT if content_type == "buyer_guide" else AUDIT_PROMPT_TEMPLATE
        if verbose and content_type == "buyer_guide":
            print("[Reviewer] 使用 LMS 买家指南审核标准")
        prompt = template.format(
            keyword=keyword,
            content=content[:40000],   # 放宽截断限制（Gemini 2.5 Flash 完全支持长上下文）
            pass_score=PASS_SCORE
        )

        try:
            last_err = None
            response = None
            for m in self.fallback_models:
                try:
                    response = self.client.models.generate_content(
                        model=m,
                        contents=prompt
                    )
                    break
                except Exception as fe:
                    if "429" in str(fe) or "RESOURCE_EXHAUSTED" in str(fe):
                        print(f"[Reviewer] ⚠ {m} 配额耗尽，降级...")
                        last_err = fe
                        time.sleep(3)
                        continue
                    raise fe
            if response is None:
                raise last_err
            result = self._extract_json(response.text)
            result["forbidden_hit"] = None

            # 打印审核结果
            if verbose:
                self._print_result(result)

            return result

        except json.JSONDecodeError as e:
            print(f"[Reviewer] ⚠ JSON 解析失败: {e}")
            print(f"[Reviewer] 原始输出: {response.text[:300]}")
            # 解析失败时保守处理：返回失败，要求人工检查
            return {
                "pass": False,
                "score": 0,
                "forbidden_hit": None,
                "critical_issues": ["审核器 JSON 解析失败，需要人工检查"],
                "rewrite_instructions": "审核结果解析异常，请手动检查文章质量后使用 --skip-review 参数发布。",
                "dimension_scores": {}
            }
        except Exception as e:
            print(f"[Reviewer] ❌ 审核 API 调用失败: {e}")
            return {
                "pass": False,
                "score": 0,
                "forbidden_hit": None,
                "critical_issues": [f"审核 API 异常: {str(e)}"],
                "rewrite_instructions": "审核器异常，请检查 API Key 和网络连接。",
                "dimension_scores": {}
            }

    def _print_result(self, result):
        """格式化打印审核结果"""
        score = result.get("score", 0)
        passed = result.get("pass", False)
        dims = result.get("dimension_scores", {})

        status = "✅ 通过" if passed else "❌ 未通过"
        print(f"\n[Reviewer] 审核结果: {status}  总分: {score}/100 (通过线: {PASS_SCORE})")
        # 维度标签（两套标准通用，缺失的跳过）
        labels = {
            "de_ai": "去AI化", "eeat": "E-E-A-T", "hcu": "HCU合规/买家意图",
            "technical_depth": "技术深度", "structure": "结构质量", "overall": "综合判断",
            "comparison_depth": "对比深度/准确性", "decision_guidance": "选型建议",
        }
        if dims:
            print(f"[Reviewer] 维度得分:")
            for key, val in dims.items():
                print(f"           {labels.get(key, key)}: {val}")

        issues = result.get("critical_issues", [])
        if issues:
            print(f"[Reviewer] 主要问题:")
            for issue in issues:
                print(f"           • {issue}")

        if not passed:
            instructions = result.get("rewrite_instructions", "")
            if instructions:
                print(f"[Reviewer] 重写指导: {instructions[:300]}...")
