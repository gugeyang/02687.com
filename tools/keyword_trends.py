"""
keyword_trends.py — 02687.com 关键词真实热度验证工具 v1.0
=========================================================
用 Google Trends（pytrends）查关键词的**真实相对搜索热度**，
取代 DEVELOPMENT_PLAN.md 第六节里手写/AI 猜的"估计月搜索量"。

为什么是"相对热度"而不是绝对搜索量：
  Google Trends 免费接口只给 0~100 的相对热度，且每次请求内部各词
  互相归一（批内最大值=100）。要让不同批次的词互相可比，本工具在
  每一批里都插入同一个【锚点词 anchor】，再用 候选词均值 / 锚点均值
  做归一化，得到跨批次可比的 score（锚点 = 100）。

用法:
  # 直接传词
  python tools/keyword_trends.py "moodle kubernetes" "moodle ldap" "moodle gdpr"

  # 从文件读（每行一个候选词）
  python tools/keyword_trends.py --file tools/candidates.txt

  # 校验第六节现有选题的核心长尾词
  python tools/keyword_trends.py --from-plan

  可选参数:
    --anchor "moodle plugin"     归一化锚点词（默认 moodle plugin）
    --geo US                     地区（默认 ''=全球；常用 US）
    --timeframe "today 12-m"     时间范围（默认近12个月）
    --min-score 8                低于此 score 标记为【弱】建议放弃（默认 8）

输出:
  - 终端打印按 score 排序的表格
  - 写入 tools/keyword_trends_result.md（可直接对照第六节）

注意:
  Google Trends 会限流(429)。本工具自带重试+批间等待，整批跑下来需要
  一点时间，请耐心。被限流时会自动退避重试，不要手动反复重跑。
"""

import sys
import io
import re
import time
import argparse
from pathlib import Path

# Windows 终端 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pytrends.request import TrendReq

# ─── 路径配置 ────────────────────────────────────────────────────────────────
WORKSPACE_DIR = Path(r"D:\02687.com")
DEV_PLAN      = WORKSPACE_DIR / "DEVELOPMENT_PLAN.md"
RESULT_FILE   = WORKSPACE_DIR / "tools" / "keyword_trends_result.md"

# ─── 行为配置 ────────────────────────────────────────────────────────────────
DEFAULT_ANCHOR    = "moodle plugin"   # 中等热度的稳定锚点词，用于跨批归一化
BATCH_CANDIDATES  = 4                 # 每批候选词数（+1锚点=5，Trends单次上限）
BATCH_SLEEP_SEC   = 45                # 批间等待，降低被限流概率
MAX_RETRIES       = 8                 # 单批最大重试次数
RETRY_BASE_SLEEP  = 20                # 重试退避基数秒（指数退避，限流较严）
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def make_client():
    """构造 pytrends 客户端（带真实 UA，规避部分限流）。"""
    return TrendReq(
        hl='en-US', tz=0,
        requests_args={'headers': {
            'User-Agent': USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
        }},
    )


def query_batch(keywords, anchor, geo, timeframe):
    """
    查一批关键词（含锚点）的平均相对热度。
    返回 dict: {keyword: avg_interest_float}，含锚点本身。
    自带 429 退避重试；彻底失败则抛出最后一次异常。
    """
    terms = list(keywords)
    if anchor not in terms:
        terms = terms + [anchor]

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            pt = make_client()
            pt.build_payload(terms, timeframe=timeframe, geo=geo)
            df = pt.interest_over_time()
            result = {}
            for t in terms:
                if t in df.columns:
                    result[t] = float(df[t].mean())
                else:
                    result[t] = 0.0   # Trends 完全没数据 = 热度极低
            return result
        except Exception as e:
            last_err = e
            # 指数退避 + 抖动，限流(429)时给 Google 更长冷却时间
            wait = RETRY_BASE_SLEEP * (2 ** attempt)
            wait = min(wait, 180) + (attempt * 3)
            msg = str(e)[:80]
            print(f"    [retry {attempt+1}/{MAX_RETRIES}] {type(e).__name__}: {msg} — {wait}s 后重试")
            time.sleep(wait)
    raise last_err


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]


def validate(candidates, anchor, geo, timeframe):
    """
    对所有候选词分批查询并按锚点归一化。
    返回 list of dict: [{keyword, raw_avg, anchor_avg, score}], 按 score 降序。
    score: 以锚点=100 为基准的可比相对热度。
    """
    # 去重去空，保留顺序
    seen, cands = set(), []
    for k in candidates:
        k = k.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            cands.append(k)

    rows = []
    batches = list(chunked(cands, BATCH_CANDIDATES))
    for bi, batch in enumerate(batches, 1):
        print(f"[Batch {bi}/{len(batches)}] 查询: {', '.join(batch)}  (+anchor: {anchor})")
        res = query_batch(batch, anchor, geo, timeframe)
        anchor_avg = res.get(anchor, 0.0)
        for kw in batch:
            raw = res.get(kw, 0.0)
            if anchor_avg > 0:
                score = round(raw / anchor_avg * 100, 1)
            else:
                # 锚点在该批也为0（异常），退回原始均值
                score = round(raw, 1)
            rows.append({
                "keyword": kw,
                "raw_avg": round(raw, 1),
                "anchor_avg": round(anchor_avg, 1),
                "score": score,
            })
            print(f"    {kw:45s} raw={raw:5.1f}  score={score}")
        if bi < len(batches):
            print(f"    ...批间等待 {BATCH_SLEEP_SEC}s 防限流")
            time.sleep(BATCH_SLEEP_SEC)

    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def verdict(score, min_score):
    if score >= 60:
        return "🟢 强"
    if score >= min_score:
        return "🟡 可"
    return "🔴 弱(建议放弃)"


def write_result(rows, anchor, geo, timeframe, min_score):
    geo_label = geo if geo else "全球"
    lines = [
        f"# 关键词真实热度验证结果",
        "",
        f"- 数据源: Google Trends (pytrends)",
        f"- 锚点词(=100基准): `{anchor}`",
        f"- 地区: {geo_label}　时间范围: {timeframe}",
        f"- score = 候选词均值 / 锚点均值 × 100（跨批次可比）",
        f"- 判定: score≥60 强 / ≥{min_score} 可 / <{min_score} 弱(建议放弃)",
        "",
        "| 关键词 | score | 原始热度 | 判定 |",
        "|--------|-------|---------|------|",
    ]
    for r in rows:
        lines.append(f"| {r['keyword']} | {r['score']} | {r['raw_avg']} | {verdict(r['score'], min_score)} |")
    lines.append("")
    RESULT_FILE.write_text("\n".join(lines), encoding='utf-8')
    print(f"\n[Saved] 结果已写入: {RESULT_FILE}")


def parse_plan_keywords():
    """从 DEVELOPMENT_PLAN.md 第六节提取每行的'核心长尾词'（第3列），按逗号拆分。"""
    if not DEV_PLAN.exists():
        print("[Error] DEVELOPMENT_PLAN.md 不存在")
        return []
    content = DEV_PLAN.read_text(encoding='utf-8')
    m = re.search(r'## 六、下一批推荐选题.*?(?=## 七)', content, re.DOTALL)
    if not m:
        print("[Error] 找不到第六节")
        return []
    kws = []
    for line in m.group(0).splitlines():
        if not line.startswith('|'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 4 or '优先级' in parts[1] or ':---' in parts[1]:
            continue
        cell = parts[3]
        for k in cell.split(','):
            k = k.strip()
            if k:
                kws.append(k)
    return kws


def main():
    ap = argparse.ArgumentParser(description="Google Trends 关键词真实热度验证")
    ap.add_argument("keywords", nargs="*", help="候选关键词（空格分隔，含空格的用引号）")
    ap.add_argument("--file", help="从文件读候选词（每行一个）")
    ap.add_argument("--from-plan", action="store_true", help="校验第六节现有选题核心词")
    ap.add_argument("--anchor", default=DEFAULT_ANCHOR, help=f"归一化锚点词（默认 {DEFAULT_ANCHOR}）")
    ap.add_argument("--geo", default="", help="地区代码，如 US；默认全球")
    ap.add_argument("--timeframe", default="today 12-m", help="时间范围（默认 today 12-m）")
    ap.add_argument("--min-score", type=float, default=8, help="弱词阈值（默认 8）")
    args = ap.parse_args()

    candidates = list(args.keywords)
    if args.file:
        candidates += [l for l in Path(args.file).read_text(encoding='utf-8').splitlines()]
    if args.from_plan:
        candidates += parse_plan_keywords()

    candidates = [c for c in (c.strip() for c in candidates) if c]
    if not candidates:
        print("用法: python tools/keyword_trends.py \"keyword1\" \"keyword2\" ...")
        print("或:   python tools/keyword_trends.py --from-plan")
        sys.exit(1)

    print("=" * 60)
    print(f"  关键词真实热度验证 | 锚点={args.anchor} | 地区={args.geo or '全球'}")
    print(f"  候选词数: {len(candidates)}  (Trends 限流较严，请耐心)")
    print("=" * 60)

    rows = validate(candidates, args.anchor, args.geo, args.timeframe)

    print("\n" + "=" * 60)
    print("  排序结果 (score 越高越值得写)")
    print("=" * 60)
    for r in rows:
        print(f"  {verdict(r['score'], args.min_score):14s} score={r['score']:6}  {r['keyword']}")

    write_result(rows, args.anchor, args.geo, args.timeframe, args.min_score)


if __name__ == "__main__":
    main()
