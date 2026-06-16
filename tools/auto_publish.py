"""
auto_publish.py — 02687.com 自动发布流水线 v1.0
=================================================
全自动从推荐选题列表选题 → Gemini 生成文章 → AI 审核 → Unsplash 封面 → git push

用法:
  python tools/auto_publish.py                # 全自动模式（推荐）
  python tools/auto_publish.py "主题关键词"   # 指定主题
  python tools/auto_publish.py --dry-run      # 预览模式（不写文件不推送）
  python tools/auto_publish.py --skip-review  # 跳过 AI 审核（紧急情况备用）
"""

import sys
import io
import os
import re
import json
import time
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Windows 终端 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ─── 路径配置 ────────────────────────────────────────────────────────────────
WORKSPACE_DIR   = Path(r"D:\02687.com")
CONTENT_DIR     = WORKSPACE_DIR / "content" / "english" / "blog"
MASTER_RECORD   = WORKSPACE_DIR / "CONTENT_MASTER_RECORD.md"
DEV_PLAN        = WORKSPACE_DIR / "DEVELOPMENT_PLAN.md"
IMAGES_DIR      = WORKSPACE_DIR / "static" / "images" / "blog"
TOOLS_DIR       = WORKSPACE_DIR / "tools"

# ─── 图片配置 ────────────────────────────────────────────────────────────────
# 现有静态封面（循环分配用）
STATIC_IMAGES   = [f"images/blog/blog-post-{i}.jpg" for i in range(1, 8)]
# Unsplash 下载图存放目录和命名前缀
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# 模型降级列表：主模型配额耗尽时自动尝试下一个
GENERATOR_MODELS = [
    "gemini-2.5-flash",       # 最新最强，优先使用
    "gemini-2.0-flash",       # 降级一档
    "gemini-2.0-flash-lite",  # 最后兜底
]
GENERATOR_MODEL = GENERATOR_MODELS[0]  # 默认主模型（日志显示用）
MAX_REVIEW_RETRIES = 2   # 审核不通过最多重写几次


# ═══════════════════════════════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════════════════════════════

def load_env():
    """从项目根目录或 tools/ 目录加载 .env 文件"""
    for env_path in [WORKSPACE_DIR / ".env", TOOLS_DIR / ".env"]:
        if env_path.exists():
            print(f"[Env] 加载配置: {env_path}")
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip()
            return
    print("[Env] 未找到 .env 文件，依赖系统环境变量。")


def init_api():
    """初始化 Gemini API，返回 client 对象（新版 google-genai SDK）"""
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[FATAL] 未找到 GEMINI_API_KEY！")
        print("        请在 .env 文件中添加: GEMINI_API_KEY=你的Key")
        sys.exit(1)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        print(f"[API] Gemini 初始化成功，生成模型: {GENERATOR_MODEL}")
        return client
    except ImportError:
        print("[FATAL] 未安装 google-genai！")
        print("        请执行: pip install google-genai")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# 选题模块（读取 DEVELOPMENT_PLAN.md）
# ═══════════════════════════════════════════════════════════════════════════════

def get_published_keywords():
    """从 CONTENT_MASTER_RECORD.md 提取已发布的关键词集合"""
    published = set()
    if not MASTER_RECORD.exists():
        return published
    content = MASTER_RECORD.read_text(encoding='utf-8')
    for line in content.splitlines():
        if line.startswith('|') and '已发布' not in line and ':---' not in line and '日期' not in line:
            # 提取第3列（分类/标签列之后）的关键词
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                # 第2列是标题
                title = parts[2].strip()
                if title:
                    published.add(title.lower())
    return published


def parse_topic_list():
    """
    从 DEVELOPMENT_PLAN.md 第六节解析推荐选题列表。
    返回 list of dict: [{priority, title, keywords, status}, ...]
    """
    if not DEV_PLAN.exists():
        print("[Error] DEVELOPMENT_PLAN.md 不存在！")
        return []

    content = DEV_PLAN.read_text(encoding='utf-8')

    # 定位第六节
    section_match = re.search(r'## 六、下一批推荐选题.*?(?=## 七)', content, re.DOTALL)
    if not section_match:
        print("[Error] 无法在 DEVELOPMENT_PLAN.md 中找到第六节推荐选题！")
        return []

    section = section_match.group(0)
    topics = []

    # 解析表格行：| 优先级 | 建议文章标题 | 核心长尾词 | 估计月搜索量 | 状态 |
    for line in section.splitlines():
        if not line.startswith('|'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 6:
            continue
        priority_cell = parts[1]
        title_cell    = parts[2]
        keywords_cell = parts[3]
        status_cell   = parts[5] if len(parts) > 5 else ""

        # 跳过表头和分隔行
        if '优先级' in priority_cell or ':---' in priority_cell or not title_cell:
            continue

        # 只处理未写过的（状态含 ⬜）
        if '⬜' not in status_cell:
            continue

        # 解析优先级
        if 'P1' in priority_cell:
            priority = 1
        elif 'P2' in priority_cell:
            priority = 2
        else:
            priority = 3

        topics.append({
            "priority": priority,
            "title": title_cell,
            "keywords": keywords_cell,
            "status": status_cell.strip()
        })

    return sorted(topics, key=lambda x: x["priority"])


def select_topic(manual_topic=None):
    """
    选择本次要写的主题。
    manual_topic: 用户命令行指定的主题（字符串）
    返回 (title, keywords) 或 None
    """
    if manual_topic:
        print(f"[Topic] 使用指定主题: {manual_topic}")
        return manual_topic, manual_topic

    topics = parse_topic_list()
    if not topics:
        print("[Error] 推荐选题列表为空，请检查 DEVELOPMENT_PLAN.md 第六节。")
        return None, None

    # 过滤掉文件已存在的选题
    for topic in topics:
        slug = keyword_to_slug(topic["title"])
        if not (CONTENT_DIR / f"{slug}.md").exists():
            print(f"[Topic] 自动选题 (P{topic['priority']}): {topic['title']}")
            print(f"[Topic] 核心关键词: {topic['keywords']}")
            return topic["title"], topic["keywords"]

    print("[Topic] 所有推荐选题均已发布完毕！")
    return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# 内链模块
# ═══════════════════════════════════════════════════════════════════════════════

def get_existing_articles():
    """扫描已有博客文章，返回 [{title, slug, url}] 列表"""
    articles = []
    if not CONTENT_DIR.exists():
        return articles
    for md_file in CONTENT_DIR.glob("*.md"):
        if md_file.name == "_index.md":
            continue
        try:
            content = md_file.read_text(encoding='utf-8', errors='ignore')
            match = re.search(r'^title:\s*"(.+?)"', content, re.MULTILINE)
            if match:
                slug = md_file.stem
                articles.append({
                    "title": match.group(1),
                    "slug": slug,
                    "url": f"/blog/{slug}/"
                })
        except Exception:
            continue
    return articles


def build_internal_links_hint(current_slug, articles, count=3):
    """生成注入 Prompt 的内链提示文字"""
    others = [a for a in articles if a["slug"] != current_slug][:count]
    if not others:
        return ""
    links = "\n".join([f'  - [{a["title"]}]({a["url"]})' for a in others])
    return f"""
INTERNAL LINKS (MANDATORY — weave these naturally into relevant paragraphs, NOT as a list at the end):
{links}
At least 2 of these links MUST appear within the body text of the article, embedded in relevant sentences.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 文章生成模块
# ═══════════════════════════════════════════════════════════════════════════════

ARTICLE_PROMPT = """You are Alex Chen, a senior EdTech infrastructure architect with 9 years of experience
deploying learning management systems at universities across Asia-Pacific. You have personally
deployed Moodle, Canvas, Open edX, and Nextcloud in production environments.

Write a comprehensive, deeply technical blog post for the 02687.com website targeting the topic: "{title}"
Primary keywords to optimize for: {keywords}

AUTHOR VOICE REQUIREMENTS (critical — this determines E-E-A-T score):
- Write in first person. Use "I", "I've seen", "I spent X hours debugging this"
- Include at least one specific failure you encountered and how you diagnosed it
- Include at least one thing you wish someone had told you before starting
- Take clear stances — avoid "it depends" without a specific recommendation
- Use specific numbers: memory sizes, user counts, response times, hours spent

MANDATORY FRONT MATTER (copy exactly, fill in the blanks):
---
title: "{title}"
date: {date}
image: "images/blog/{slug}.jpg"
author: "Alex Chen"
type: "post"
categories: {categories}
tags: {tags}
description: "[Write a compelling 140-160 character meta description that includes the primary keyword and explains exactly what the reader will learn. Do NOT use generic phrases like 'comprehensive guide'.]"
---

STRUCTURE REQUIREMENTS:
1. Opening paragraph: Start with a specific technical pain point or failure scenario. NO generic openers.
2. 4-6 H2 headings — each MUST contain specific technical keywords (not generic like "The Problem")
3. At least 1 complete, production-ready code block (YAML, Bash, PHP, or Python — NOT pseudocode)
4. A "Gotchas" section with at least 3 specific real-world problems + exact fixes
5. A "Trade-offs" or recommendation section with a clear stance
6. Closing paragraph with internal links to related articles (see below)

FORBIDDEN:
- Do NOT include <!-- ADSENSE_INSERT_HERE -->
- Do NOT use Chinese characters anywhere in the article
- Do NOT use phrases: "In today's digital era", "In conclusion", "It is important to note", "As we all know"
- Do NOT write pseudocode or incomplete code examples

WORD COUNT: 1100-1500 words

{internal_links}

Output the article starting directly with ---, no markdown wrapper around it.
"""


# ─── 买家指南 / LMS 选型对比类 Prompt（高 CPC 广告变现方向）─────────────────────
# 这类文章面向"想选购 LMS 的买家"，形态是榜单/对比/选型指南，而非命令行教程。
# 广告主在这类页面出价高（$50–450 页首出价），但内容形态完全不同：
# 不要代码块/Gotchas，要真实产品对比表、优缺点、按场景推荐、FAQ。
BUYER_GUIDE_PROMPT = """You are Alex Chen, an independent EdTech consultant with 9 years of experience.
You have personally deployed, migrated, and EVALUATED dozens of learning management systems
(Moodle, Canvas, Open edX, TalentLMS, Docebo, LearnUpon, Absorb, iSpring, Litmos, and more)
for universities, corporate training teams, and nonprofits across Asia-Pacific. You help
organizations CHOOSE the right LMS, so you have hands-on opinions about which tools fit which use case.

Write a comprehensive, genuinely useful LMS buyer's guide for the 02687.com website on: "{title}"
Primary keywords to optimize for: {keywords}

This is a BUYER'S GUIDE / COMPARISON article, NOT a server tutorial. The reader is deciding which
LMS to buy or adopt. Your job is to help them DECIDE — confidently and specifically.

AUTHOR VOICE REQUIREMENTS (critical — this determines E-E-A-T score):
- Write in first person. Use "I've deployed this for...", "When I evaluated X for a client...", "I'd avoid X if..."
- Reference concrete evaluation experience: specific scenarios, what worked, what frustrated you
- Take clear stances. NAME a winner for each use case. Never end on "it depends" without a recommendation
- Be specific about WHO each option is best for (team size, budget level, industry, technical skill)

MANDATORY FRONT MATTER (copy exactly, fill in the blanks):
---
title: "{title}"
date: {date}
image: "images/blog/{slug}.jpg"
author: "Alex Chen"
type: "post"
categories: {categories}
tags: {tags}
description: "[Write a compelling 140-160 character meta description that includes the primary keyword and names the buyer benefit. Do NOT use generic phrases like 'comprehensive guide'.]"
---

STRUCTURE REQUIREMENTS (follow this buyer-guide shape):
1. Opening: a specific decision pain the reader faces (e.g. "Most 'best LMS' lists are vendor-sponsored fluff. I've actually run these in production, so here's the honest version."). State who this guide is for.
2. A short "How I evaluated these" / "What matters for {keywords}" section — your selection criteria
3. A MARKDOWN COMPARISON TABLE of 5-7 REAL, well-known LMS products with columns like: Platform | Best for | Deployment (cloud/self-hosted) | Standout strength | Pricing model
4. Per-product mini-reviews: one H2 or H3 per product, each with a one-line "Best for", 2-3 honest pros, 1-2 real cons, and your verdict
5. A "Which should you choose?" decision section — concrete recommendations BY SCENARIO (small team, tight budget, compliance-heavy industry, etc.)
6. A short pricing-reality section (describe pricing MODELS — per-user, tiered, quote-based — qualitatively)
7. An "FAQ" section with 3-5 real questions buyers ask, each answered in 2-3 sentences
8. Closing with a clear recommendation + internal links to related articles (see below)

ACCURACY GUARDRAILS (violating these fails review):
- Only mention REAL, currently-existing LMS products. Do NOT invent products or features.
- Do NOT fabricate specific prices, exact user counts, or made-up statistics. For pricing, describe the MODEL and say readers should verify current pricing on the vendor site.
- Do NOT invent fake customer testimonials or review quotes.
- Present balanced pros AND cons for every product — a list of only-positives reads as sponsored and fails.

FORBIDDEN:
- Do NOT include <!-- ADSENSE_INSERT_HERE -->
- Do NOT use Chinese characters anywhere in the article
- Do NOT use phrases: "In today's digital era", "In conclusion", "It is important to note", "As we all know"
- Do NOT include code blocks or command-line instructions — this is a buyer guide, not a tutorial

WORD COUNT: 1400-1900 words

{internal_links}

Output the article starting directly with ---, no markdown wrapper around it.
"""


# 买家意图信号：命中即用 BUYER_GUIDE_PROMPT + 买家指南审核标准
BUYER_GUIDE_SIGNALS = re.compile(
    r'\b(best|top\s+\d+|top\s+lms|vs\.?|versus|comparison|compare|compared|vendors?|'
    r'list of|cheapest|affordable|pricing|cost|white[\s-]label|gamified|scorm|'
    r'cloud[\s-]based|free\s+lms|alternatives?|platforms?\s+for|lms\s+for|software\s+for)\b',
    re.I,
)


def is_buyer_guide(title, keywords):
    """判断选题是否属于 LMS 买家指南/对比/榜单类（决定生成 prompt 与审核标准）。"""
    return bool(BUYER_GUIDE_SIGNALS.search(f"{title} {keywords}"))


def keyword_to_slug(title):
    """将文章标题转换为 URL slug"""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug.strip())
    slug = re.sub(r'-+', '-', slug)
    return slug[:80]


# 分类规则：按词边界(\b)匹配，避免子串误判（旧版 'ai' in 'email' 把邮件文章错分到 Data and AI）。
# 末尾不带 \b 的是词干（如 deploy 匹配 deploy/deployment，automat 匹配 automation/automate）。
CATEGORY_RULES = [
    ("Infrastructure and Cloud", [
        r'\bdocker\b', r'\bkubernetes\b', r'\bk8s\b', r'\bnginx\b', r'\bapache\b',
        r'\bssl\b', r'\btls\b', r'\bhttps?\b', r'\bbackup\b', r'\bserver\b',
        r'\bcloud\b', r'\bdeploy', r'\bvps\b', r'\bproxy\b', r'\bdns\b',
        r'\bsmtp\b', r'\bemail\b', r'\bmail\b', r'\bspf\b', r'\bdkim\b', r'\bpostfix\b',
        r'\bredis\b', r'\bperformance\b', r'\bscaling\b', r'\bcdn\b', r'\bdocker-compose\b',
    ]),
    ("Dev Log", [
        r'\bapi\b', r'\bpython\b', r'\bbash\b', r'\bscript', r'\bautomat',
        r'\bplugin\b', r'\bdev\b', r'\bcode\b', r'\bwebhook\b', r'\bcli\b', r'\bgit\b',
    ]),
    ("Security", [
        r'\bsso\b', r'\bsaml\b', r'\bsecurity\b', r'\bauth', r'\bldap\b',
        r'\bkeycloak\b', r'\boauth\b', r'\bfirewall\b', r'\bgdpr\b', r'\bencryption\b',
    ]),
    ("Data and AI", [
        r'\bdata\b', r'\bdatabase\b', r'\bai\b', r'\bml\b', r'\bllm\b',
        r'\banalytics\b', r'\bgraph', r'\betl\b', r'\bxapi\b', r'\breport',
    ]),
]


def infer_categories(title, keywords):
    """根据标题和关键词推断 Hugo 分类（词边界匹配，避免 'ai' 命中 'email' 这类误判）。"""
    # 买家指南/对比类统一归到 LMS Reviews（高 CPC 广告变现方向）
    if is_buyer_guide(title, keywords):
        return ["LMS Reviews"]
    text = (title + " " + keywords).lower()
    categories = [cat for cat, patterns in CATEGORY_RULES
                  if any(re.search(p, text) for p in patterns)]
    return categories if categories else ["Infrastructure and Cloud"]


def infer_tags(title, keywords):
    """从标题和关键词中提取标签"""
    tech_terms = [
        'Moodle', 'Docker', 'Kubernetes', 'Nginx', 'Redis', 'PostgreSQL', 'MariaDB',
        'Canvas', 'Open edX', 'Chamilo', 'Nextcloud', 'Grafana', 'Prometheus',
        'AWS', 'S3', 'Rclone', 'SSL', 'HTTPS', 'PHP-FPM', 'OPcache',
        'Helm', 'Zoom', 'LMS', 'EdTech', 'Python', 'Bash', 'YAML',
        'Keycloak', 'SSO', 'SAML', 'xAPI', 'Backup', 'Performance',
        # 买家指南/对比类标签
        'SCORM', 'SaaS', 'Cloud', 'Enterprise', 'Compliance', 'Gamification',
        'TalentLMS', 'Docebo', 'Absorb', 'LearnUpon', 'Litmos', 'iSpring',
        'Corporate Training', 'Comparison', 'Self-Hosted', 'Open Source',
    ]
    text = title + " " + keywords
    found = [t for t in tech_terms if t.lower() in text.lower()]
    return found[:6] if found else ["Moodle", "EdTech", "Infrastructure"]


def assign_cover_image(slug):
    """
    策略：尝试用 Unsplash 下载专属封面图。
    失败时回退到静态循环图片。
    返回 (image_front_matter_value, local_path_or_None)
    """
    unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    if not unsplash_key:
        print("[Image] 未设置 UNSPLASH_ACCESS_KEY，使用静态封面图")
        return _fallback_image(slug), None

    return _download_unsplash(slug, unsplash_key)


def _fallback_image(slug):
    """循环分配 blog-post-1~7.jpg"""
    existing = list(CONTENT_DIR.glob("*.md"))
    n = len([f for f in existing if f.name != "_index.md"]) % 7 + 1
    return f"images/blog/blog-post-{n}.jpg"


def _download_unsplash(slug, access_key):
    """从 Unsplash 搜索并下载封面图"""
    title_words = slug.replace('-', ' ')
    queries = [
        ' '.join(title_words.split()[:4]),
        ' '.join(title_words.split()[:2]),
        "server infrastructure technology",
        "technology abstract dark"
    ]

    try:
        import requests
    except ImportError:
        print("[Image] 未安装 requests 库，使用静态封面图")
        return _fallback_image(slug), None

    photo_url = None
    for q in queries:
        search_q = urllib.parse.quote(q)
        api_url = (
            f"https://api.unsplash.com/search/photos"
            f"?query={search_q}&per_page=1&orientation=landscape"
            f"&client_id={access_key}"
        )
        try:
            resp = requests.get(api_url, headers={"Accept-Version": "v1"}, timeout=15)
            data = resp.json()
            results = data.get("results", [])
            if results:
                raw_url = results[0]["urls"]["raw"]
                photo_url = f"{raw_url}&w=1200&h=630&fit=crop&auto=format&q=85"
                print(f"[Image] Unsplash 匹配成功: '{q}'")
                break
        except Exception as e:
            print(f"[Image] Unsplash 搜索失败 ({q}): {e}")

    if not photo_url:
        print("[Image] Unsplash 搜索无结果，使用静态封面图")
        return _fallback_image(slug), None

    # 下载图片
    img_path = IMAGES_DIR / f"{slug}.jpg"
    try:
        r = requests.get(photo_url, timeout=20)
        img_path.write_bytes(r.content)
        print(f"[Image] 封面图已下载: {img_path}")
        return f"images/blog/{slug}.jpg", str(img_path)
    except Exception as e:
        print(f"[Image] 图片下载失败: {e}，使用静态封面图")
        return _fallback_image(slug), None


def generate_article(genai, title, keywords, slug, existing_articles, review_feedback=""):
    """调用 Gemini 生成文章，支持注入审核反馈进行重写"""
    model = None  # 新版 SDK 直接通过 client.models.generate_content 调用

    categories = infer_categories(title, keywords)
    tags = infer_tags(title, keywords)
    date_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    internal_links = build_internal_links_hint(slug, existing_articles)

    # 描述占位（由生成模型填写）
    # description 由 Gemini 自行生成（见 prompt 中的指令）

    # 按选题类型选择 prompt：买家指南(对比/榜单) vs 技术教程
    prompt_template = BUYER_GUIDE_PROMPT if is_buyer_guide(title, keywords) else ARTICLE_PROMPT
    print(f"[Generator] 文章类型: {'买家指南/对比' if prompt_template is BUYER_GUIDE_PROMPT else '技术教程'}")

    prompt = prompt_template.format(
        title=title,
        keywords=keywords,
        slug=slug,
        date=date_str,
        categories=json.dumps(categories),
        tags=json.dumps(tags),

        internal_links=internal_links
    )

    # 注入审核反馈（重写时使用）
    if review_feedback:
        prompt += f"""

PREVIOUS VERSION REJECTED BY QUALITY REVIEWER. Mandatory improvements for this rewrite:
{review_feedback}

Apply ALL of the above improvements. The reviewer is strict — a generic rewrite will still fail.
"""

    print(f"[Generator] 调用 Gemini 生成文章...")

    for model_name in GENERATOR_MODELS:
        print(f"[Generator] 尝试模型: {model_name}")
        try:
            response = genai.models.generate_content(
                model=model_name,
                contents=prompt
            )
            content = response.text.strip()
            content = re.sub(r'^```(?:markdown)?\s*\n', '', content)
            content = re.sub(r'\n```\s*$', '', content)
            print(f"[Generator] ✅ 模型 {model_name} 生成成功")
            return content.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                print(f"[Generator] ⚠ {model_name} 配额耗尽，尝试下一个模型...")
                time.sleep(5)
                continue
            else:
                print(f"[Generator] ❌ {model_name} 生成失败: {e}")
                return None

    print("[Generator] ❌ 所有模型均配额耗尽，请稍后再试。")
    return None



# ═══════════════════════════════════════════════════════════════════════════════
# 总控表更新
# ═══════════════════════════════════════════════════════════════════════════════

def update_master_record(title, categories, keywords_str, slug):
    """在 CONTENT_MASTER_RECORD.md 末尾追加一行记录"""
    if not MASTER_RECORD.exists():
        print("[Record] CONTENT_MASTER_RECORD.md 不存在，跳过更新")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    cat_str = ", ".join(categories)
    new_row = f"| {today} | {title} | {cat_str} | {keywords_str} | 自动发布 via auto_publish.py |\n"
    with open(MASTER_RECORD, 'a', encoding='utf-8') as f:
        f.write(new_row)
    print(f"[Record] 总控表已更新")


def update_dev_plan_status(title):
    """发布后把 DEVELOPMENT_PLAN.md 第六节对应选题的状态由 ⬜ 改为 ✅。
    匹配不到（如手动指定的非列表主题）时静默跳过。"""
    if not DEV_PLAN.exists():
        return
    lines = DEV_PLAN.read_text(encoding='utf-8').splitlines(keepends=True)
    in_section = False
    for i, line in enumerate(lines):
        if line.startswith('## 六'):
            in_section = True
            continue
        if in_section and line.startswith('## 七'):
            break
        if in_section and line.startswith('|') and '⬜' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3 and parts[2] == title:
                lines[i] = line.replace('⬜ 未写', '✅ 已发布')
                DEV_PLAN.write_text(''.join(lines), encoding='utf-8')
                print(f"[Plan] 第六节选题状态已回写: ⬜ → ✅")
                return
    print(f"[Plan] 第六节未找到匹配选题，跳过状态回写")


# ═══════════════════════════════════════════════════════════════════════════════
# Git 推送
# ═══════════════════════════════════════════════════════════════════════════════

def git_push(commit_msg):
    """git add . && commit && push"""
    print(f"[Git] 提交并推送: {commit_msg}")
    try:
        subprocess.run(["git", "add", "."], cwd=str(WORKSPACE_DIR), check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(WORKSPACE_DIR), check=True,
                       capture_output=True)
        result = subprocess.run(["git", "push"], cwd=str(WORKSPACE_DIR), check=True,
                                 capture_output=True, text=True)
        print(f"[Git] ✅ 发布成功！网站将于 1-2 分钟后更新。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[Git] ❌ 推送失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def run(manual_topic=None, dry_run=False, skip_review=False):
    print("\n" + "="*60)
    print("  02687.com 自动发布流水线 v1.0")
    print("="*60)

    # ① 初始化 API
    client = init_api()

    # ② 选题
    title, keywords = select_topic(manual_topic)
    if not title:
        return

    slug = keyword_to_slug(title)
    print(f"[Slug] {slug}")

    # 检查文件是否已存在
    target_file = CONTENT_DIR / f"{slug}.md"
    if target_file.exists():
        print(f"[Skip] 文件已存在: {target_file}，跳过发布。")
        return

    # ③ 获取已有文章（用于内链）
    existing_articles = get_existing_articles()
    print(f"[Links] 发现 {len(existing_articles)} 篇已有文章，可用于内链")

    # ④ 生成 + 审核循环
    content = None
    review_passed = False
    review_feedback = ""

    if skip_review:
        print("[Mode] ⚠ 跳过审核模式")

    for attempt in range(MAX_REVIEW_RETRIES + 1):
        if attempt > 0:
            print(f"\n[Retry] 根据审核反馈重写文章 (第 {attempt} 次重试)...")

        # 生成文章
        content = generate_article(client, title, keywords, slug, existing_articles, review_feedback)
        if not content:
            print("[Fatal] 文章生成失败，终止。")
            return

        print(f"[Generator] ✅ 生成完成，约 {len(content.split())} 词")

        # 审核
        if skip_review:
            review_passed = True
            break

        # 导入审核器
        sys.path.insert(0, str(TOOLS_DIR))
        from content_reviewer import ContentReviewer
        reviewer = ContentReviewer(client)
        content_type = "buyer_guide" if is_buyer_guide(title, keywords) else "technical"
        result = reviewer.audit(content, keywords, content_type=content_type)

        if result["pass"]:
            review_passed = True
            print(f"[Review] ✅ 审核通过！得分: {result['score']}/100")
            break
        else:
            review_feedback = result.get("rewrite_instructions", "")
            print(f"[Review] ❌ 审核未通过 (得分: {result['score']}/100)")
            if attempt >= MAX_REVIEW_RETRIES:
                print(f"[Review] 已达最大重试次数 ({MAX_REVIEW_RETRIES})，终止发布。")
                print(f"[Review] 建议：检查文章后使用 --skip-review 参数手动发布。")
                print(f"\n最后一次生成的文章预览（前800字）:\n")
                print(content[:800])
                return

    if not review_passed and not skip_review:
        return

    if dry_run:
        print(f"\n[Dry Run] 预览模式 — 不写文件，不推送")
        print(f"[Dry Run] 文件名: {slug}.md")
        print(f"[Dry Run] 内容预览（前600字）:\n")
        print(content[:600])
        print("...")
        return

    # ⑤ 分配封面图
    image_value, local_img_path = assign_cover_image(slug)
    # 将封面图路径注入文章 front matter
    content = re.sub(
        r'^image:\s*"images/blog/[^"]*"',
        f'image: "{image_value}"',
        content,
        flags=re.MULTILINE
    )

    # ⑥ 写入文件
    target_file.write_text(content, encoding='utf-8')
    print(f"[File] ✅ 文章已写入: {target_file}")

    # ⑦ 更新总控表
    categories = infer_categories(title, keywords)
    update_master_record(title, categories, keywords, slug)

    # ⑦.5 回写第六节选题状态 ⬜ → ✅
    update_dev_plan_status(title)

    # ⑧ Git 推送
    git_push(f"auto-publish: {title}")

    print("\n" + "="*60)
    print(f"  ✅ 发布完成: {title}")
    print(f"  URL: https://02687.com/blog/{slug}/")
    print("="*60)


def main():
    args = sys.argv[1:]
    dry_run      = "--dry-run"     in args
    skip_review  = "--skip-review" in args

    # 清理 flag 参数
    clean_args = [a for a in args if not a.startswith("--")]

    manual_topic = clean_args[0] if clean_args else None

    if dry_run:
        print("[Mode] 干跑模式 — 只预览，不写文件不推送")
    if skip_review:
        print("[Mode] 跳过审核 — 直接发布（慎用）")

    run(manual_topic=manual_topic, dry_run=dry_run, skip_review=skip_review)


if __name__ == "__main__":
    main()