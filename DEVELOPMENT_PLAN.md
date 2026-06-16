# 02687.com 网站运营操作手册 (v6.0 - AI-Ready Edition)

> ⚠️ **任何接手本项目的 AI 代理，必须首先通读本文件前两节，再开始任何操作。本文件是最高优先级操作手册。**

---

## 零、AI 代理接手速查卡（最高优先级，必读）

### 🔑 用户指令 → 正确操作 对照表

| 用户说了什么 | 正确理解 | 错误理解（禁止） |
|------------|---------|---------------|
| "帮我发布两篇文章" | 从**推荐选题列表**（第六节）选2个未写过的题目，**全新创作**两篇文章，git push | 修改或补全现有文章 |
| "更新两篇文章到网站" | 同上，选题 → 新写 → 发布 | 认为是修复已有文章的格式问题 |
| "按规范再写一篇" | 同上，选1个未覆盖的题目，新写 | 其他 |
| "修复XXX文章" | 才是去修改已有文章 | — |

> **核心原则：「发布文章」= 从零开始新写一篇，不是修复现有文章。**

### 🚀 最快接手路径（3步执行）

```
Step A → 打开 CONTENT_MASTER_RECORD.md，看哪些关键词已被覆盖
Step B → 从本文件第六节"推荐选题列表"里，选一个【未覆盖】的题目
Step C → 按本文件第五节"9步写作工作流"完整执行，git push 发布
```

### 📋 当前网站状态速览

| 项目 | 当前值 |
|------|--------|
| 已发布文章数 | 见 CONTENT_MASTER_RECORD.md |
| 技术栈 | Hugo + GitHub Actions 自动部署 |
| 作者署名 | `Alex Chen`（全站统一，见下方说明） |
| 目标 | Google AdSense 审核通过，月 $30 广告收入 |
| 文章目录 | `content/english/blog/` |

### ⚠️ 重要：作者字段当前规范

> **`author` 字段统一使用 `"Alex Chen"`**，不是 `"EdTech Architect"`。
>
> 原因：2026-05-07 执行了 Google HCU 风险规避改造，全站 author 已批量改为
> 具体可信的虚构人物 `Alex Chen`，以提升 E-E-A-T 可信度评分。
> 作者 Bio 页在 `content/english/author/alex-chen.md`。

---

## 一、项目架构速览

本项目使用 **Hugo** 静态站点生成器 + **GitHub Actions** 自动部署。

```
你写的 .md 文章文件   →   git push   →   GitHub Actions 自动编译   →   02687.com 上线
(content/english/blog/)                   (云端，无需本地操作)
```

**每一个 `.md` 文件 = 网站上的一篇文章/页面。** 你只需管理 `.md` 文件，其余全部自动化。

| 目录/文件 | 作用 | 需要动吗？ |
|-----------|------|-----------|
| `content/english/blog/*.md` | 博客文章，每文件对应一篇文章 | ✅ 主要工作区 |
| `content/english/course/*.md` | Solutions 页面的产品卡片 | 偶尔 |
| `content/english/about/_index.md` | About Us 页面 | 偶尔 |
| `content/english/author/alex-chen.md` | 作者 Bio 页面 | 几乎不动 |
| `data/en/homepage.yml` | 首页各区块文字 | 偶尔 |
| `hugo.toml` | 全站配置 | 偶尔 |
| `CONTENT_MASTER_RECORD.md` | 已发布文章总控表，防重复 | **每次发文后必填** |
| `REPLAY_OPTIMIZATION.md` | 所有历史改动记录，是项目变更的 Source of Truth | 只读参考 |
| `public/` 目录 | Hugo 编译输出，**禁止手动碰** | ❌ |
| `.github/workflows/hugo.yaml` | 自动部署脚本，**禁止修改** | ❌ |

---

## 二、GitHub 发布流程（每次发文后执行）

```powershell
cd d:\02687.com
git add .
git commit -m "add: 简短描述本次新增内容"
git push
# 约 1-2 分钟后 02687.com 自动更新
```

> 验证：访问 `https://github.com/gugeyang/02687.com/actions` 查看是否有绿色 ✅ 任务。

> **注意**：`CONTENT_MASTER_RECORD.md` 在 `.gitignore` 中，不会被 push，这是正常的。它是本地运营记录。

---

## 三、本地预览（可选）

Hugo 已安装（v0.161.1）。在 PowerShell 执行：

```powershell
cd d:\02687.com
hugo server
# 浏览器访问 http://localhost:1313，文件修改后自动刷新
# Ctrl+C 停止
```

---

## 四、核心商业目标与红线

### 商业目标

终极目标：**通过 Google AdSense 获取广告收益（目标：$1/天 = $30/月）**。

达到目标的条件：
- 月访问量 ≥ 3,000 PV（EdTech 内容 RPM 约 $8-15）
- 文章数量 ≥ 40 篇，覆盖足够多的长尾关键词
- Google AdSense 审核通过

### 零容忍红线

- **绝对禁止**：提及"卓越睿新"、"Able-Elec"等真实商业品牌。虚拟学校统一用 `"Global Tech University"`
- **绝对禁止**：随机外籍人像 Stock Photos、虚构电话/地址
- **绝对禁止**：Lorem Ipsum 占位内容出现在任何线上页面
- **官方邮箱**：`admin@02687.com`（唯一合法联系方式）
- **零死链**：导航栏所有链接必须 100% 可访问
- **禁止预埋广告占位符**：`<!-- ADSENSE_INSERT_HERE -->` 已全部移除，**新文章不得再加入此注释**（是内容农场信号）

---

## 五、写一篇新文章的完整工作流（9步强制执行）

> **AI 代理必须按此顺序执行，不得跳过任何步骤。**

---

### ★ Step 1：查阅内容总控表，选题与防重复

打开 `CONTENT_MASTER_RECORD.md`，检查：
1. 要写的**核心关键词是否已被覆盖**？（已覆盖的词不能再写同主题文章）
2. 参考第六节"推荐选题"列表优先选择未覆盖的题目

---

### ★ Step 2：确定主关键词和长尾词组

每篇文章必须在写作前确定：

| 类型 | 数量要求 | 示例 |
|------|---------|------|
| **主关键词**（文章主题，出现在 title 和 H1）| 1个 | `moodle docker production` |
| **次级长尾词**（出现在 H2/H3 标题中）| 3-5个 | `moodle redis cache setup`、`moodle php-fpm tuning` |
| **语义关联词**（自然出现在正文中）| 5-8个 | `LMS performance`、`container orchestration` |

**长尾词选择原则：**
- 优先选月搜索量 **100-1000** 的词（竞争低、精准流量）
- 词中必须包含**具体动作或场景**（how to / setup / tutorial / vs / performance）
- 避免纯品牌词（如只写 "Moodle"，太泛、太难排名）

---

### ★ Step 3：创建文件，规范命名

在 `content/english/blog/` 目录下新建文件。

**文件命名规则：**
- 全小写英文
- 用连字符 `-` 分隔单词
- 文件名**必须包含主关键词**（这直接影响 URL，是重要的 SEO 信号）

```
✅ 正确: moodle-performance-tuning-redis-php-fpm.md
✅ 正确: canvas-lms-vs-moodle-2026-comparison.md
❌ 错误: article-01.md
❌ 错误: new-blog-post.md
```

---

### ★ Step 4：填写 Front Matter（必须包含全部字段）

```yaml
---
title: "文章大标题：必须包含主关键词，格式建议「主题: 具体场景说明」"
date: 2026-05-16T10:00:00+08:00   # 填写真实写作日期（当前日期）
# ⚠️ 日期策略说明：
# - 2024年的旧文章日期【不要修改】，这是 E-E-A-T 信任建立策略（让 Google 认为站点已运营多年）
# - 新文章统一使用写作当天的真实日期（2026年）
image: "images/blog/blog-post-3.jpg"   # 可选 blog-post-1 到 blog-post-7
author: "Alex Chen"                     # 固定，不得修改（全站统一人物）
type: "post"
categories: ["Infrastructure and Cloud"]  # 只能从以下4个中选择1-2个
tags: ["Moodle", "Docker", "Redis", "PHP-FPM", "Performance"]  # 5个左右精准标签
description: "120-155字的英文摘要。必须包含主关键词和1-2个次级长尾词。这是Google搜索结果摘要，直接影响点击率，务必写得有吸引力。"
---
```

**categories 只允许以下四个值：**
- `"Infrastructure and Cloud"` — Docker、Kubernetes、服务器、Nginx、监控
- `"Data and AI"` — 数据库、知识图谱、ETL、机器学习、数据分析
- `"Security"` — SSO、SAML、身份认证、IAM、合规
- `"Dev Log"` — Python 脚本、REST API、踩坑记录、自动化

---

### ★ Step 5：按 SEO 优化结构写正文

#### 5.1 开篇规范（第1-2段，约150词）

- **第1段**：用真实的技术场景或痛点直接开篇，**禁止**使用以下套话：
  - "In today's digital era..."
  - "In conclusion..."
  - "It is important to note..."
  - "As we all know..."
- **第2段**：点明文章将解决什么具体问题，预告核心内容

#### 5.2 H2/H3 标题必须嵌入长尾词（最关键的优化点）

每个 H2/H3 标题都是 Google 独立解析的 SEO 入口点。**禁止使用无关键词的通用标题**：

```markdown
❌ 禁止（无关键词，无人搜索）：
## The Problem
## Our Solution
## What We Learned

✅ 正确（包含具体长尾词）：
## Why Moodle PHP-FPM Crashes Under Exam Load (And How to Fix It)
## Moodle Redis Session Cache: Docker Configuration That Actually Works
## Benchmarking Moodle Performance: 500 vs 1,000 Concurrent Users
```

**每篇文章的 H2 标题数量要求：4-6个**，每个 H2 都应覆盖一个独立的次级长尾词。

#### 5.3 强制内容模块（每篇文章必须包含）

| 模块 | 要求 | 原因 |
|------|------|------|
| **真实代码/配置** | 至少1个完整代码块（YAML/Python/Bash等）| 信息密度高，留存时间长 |
| **"Gotchas"踩坑小节** | 至少描述2个真实遇到的问题和解决方案 | E-E-A-T 核心信号，证明真实经验 |
| **架构权衡（Trade-offs）** | 分析为什么选这个方案、其他方案的优缺点 | 体现专业深度 |
| **内部链接** | 至少 **2个** 指向站内其他文章的链接 | 见 Step 6 |

#### 5.4 文章长度规范

- **目标**：1000-1500 英文单词
- **最低限制**：不得低于 800 词（低于此值会被 Google 判定为 thin content）
- **语言**：100% 纯正英语，零中文字符（中文会降低广告定向精度）

---

### ★ Step 6：添加内部链接（强制要求，不得省略）

内部链接是建立"主题权威性（Topical Authority）"的关键。每篇文章**至少需要 2 条**指向已发布文章的内部链接。

**链接写法：**

```markdown
For monitoring your LMS stack, see our guide on
[Prometheus and Grafana for LMS Performance Monitoring](/blog/prometheus-grafana-lms-monitoring/).

If you're also managing student identities, our
[Keycloak SSO Campus Deployment guide](/blog/building-campus-wide-sso-keycloak/)
walks through the full federation setup.
```

**现有文章内链地址速查表：**

| 文章标题 | 内链地址 |
|---------|---------|
| Self-Hosting Moodle with Docker | `/blog/self-hosting-educational-tools-docker-homelab/` |
| Knowledge Graph for Universities | `/blog/building-next-gen-knowledge-graph/` |
| Canvas LMS Python REST API | `/blog/automating-canvas-lms-enrollments/` |
| BigBlueButton 10k Students | `/blog/scaling-bigbluebutton-10k-students/` |
| SAML SSO in Moodle | `/blog/implementing-saml-sso-moodle/` |
| Serverless Plagiarism Detection | `/blog/serverless-plagiarism-detection-pipeline/` |
| LRS with xAPI | `/blog/lms-to-lrs-with-xapi/` |
| Auto-Grading with Docker | `/blog/containerizing-auto-grading-pipelines-docker/` |
| Prometheus + Grafana LMS | `/blog/prometheus-grafana-lms-monitoring/` |
| Migrating SIS to PostgreSQL | `/blog/migrating-legacy-sis-data-postgresql-python/` |
| Keycloak Campus SSO | `/blog/building-campus-wide-sso-keycloak/` |
| Nextcloud vs Google Workspace | `/blog/deploying-nextcloud-secure-alternative-google-workspace/` |
| Moodle Performance Tuning | `/blog/moodle-performance-tuning-php-fpm-redis-opcache/` |
| Installing Moodle on Ubuntu 22.04 | `/blog/installing-moodle-ubuntu-22-04-docker-compose/` |
| What is 02687.com（品牌锚点页） | `/blog/what-is-02687-edtech-platform/` |
| Moodle vs Canvas: Self-Hosted | `/blog/moodle-vs-canvas-open-source-self-hosted/` |
| Moodle Redis Session Outage Post-Mortem | `/blog/moodle-redis-session-outage-post-mortem/` |
| Moodle HTTPS Nginx Let's Encrypt | `/blog/moodle-ssl-https-nginx-letsencrypt/` |
| Moodle Backup to AWS S3 with Rclone | `/blog/moodle-automated-backup-aws-s3-rclone/` |

---

### ★ Step 7：广告占位符说明

> ❌ **新文章不得插入 `<!-- ADSENSE_INSERT_HERE -->` 注释。**
>
> 此占位符已于 2026-05-07 从全站移除（Google HCU 风险规避）。
> 等 AdSense 正式审核通过后，会统一用脚本批量插入广告代码。

---

### ★ Step 8：写作完成后的自检清单

在提交前，AI 代理必须逐项确认：

- [ ] Front matter 包含：`title`、`date`、`image`、`author`、`type`、`categories`、`tags`、`description`
- [ ] `author` 字段值为 `"Alex Chen"`（不是 EdTech Architect）
- [ ] `description` 字段是 120-155 字的精炼英文摘要，包含主关键词
- [ ] 文件名包含主关键词，全小写，连字符分隔
- [ ] 至少 4 个 H2 标题，每个都嵌入了具体的长尾词或技术词
- [ ] 包含至少 1 个完整的代码块（YAML/Python/Bash/等）
- [ ] 包含"Gotchas"或踩坑小节（至少2个真实问题+解法）
- [ ] 包含至少 2 条指向站内其他文章的内部链接（用上方速查表）
- [ ] 全文**无** `<!-- ADSENSE_INSERT_HERE -->` 占位符
- [ ] 全文无中文字符
- [ ] 全文无 Lorem Ipsum 占位文字
- [ ] 全文无"John Doe"、真实商业品牌名等违规内容
- [ ] 字数在 1000-1500 词之间

---

### ★ Step 9：登记到内容总控表 + 发布

```powershell
# 1. 打开 CONTENT_MASTER_RECORD.md，在表格末尾追加一行：
# | 2026-05-16 | 文章标题 | 分类 | 主关键词, 长尾词1, 长尾词2 | 一句话中文摘要 |

# 2. git push 发布
cd d:\02687.com
git add .
git commit -m "add: 文章标题简述"
git push
```

---

## 六、下一批推荐选题（按 SEO 优先级排序）

以下选题已经过关键词搜索量分析，按优先级排序。**写文章时优先从这里选题，已写过的划掉**：

| 优先级 | 建议文章标题 | 核心长尾词 | 估计月搜索量 | 状态 |
|--------|------------|-----------|------------|------|
| 🔴 P1 | Moodle Performance Tuning: PHP-FPM Workers, Redis Cache, and OPcache | moodle performance tuning, moodle redis cache | ~1,200 | ✅ 已发布 |
| 🔴 P1 | Installing Moodle on Ubuntu 22.04 with Docker Compose: Step-by-Step | moodle docker ubuntu, install moodle docker | ~880 | ✅ 已发布 |
| 🔴 P1 | Canvas LMS vs Moodle 2026: Technical Comparison for University IT Teams | canvas vs moodle, lms comparison university | ~720 | ✅ 已发布 |
| 🟡 P2 | Securing Moodle with HTTPS Using Let's Encrypt and Nginx Reverse Proxy | moodle ssl nginx, moodle https setup | ~590 | ✅ 已发布 |
| 🟡 P2 | Open Source LMS Comparison: Moodle vs Open edX vs Canvas vs Chamilo | open source lms comparison 2026 | ~540 | ✅ 已发布 |
| 🟡 P2 | Automated Moodle Backup to AWS S3 with Cron and rclone | moodle backup s3, moodle automated backup | ~430 | ✅ 已发布 |
| 🟢 P3 | Integrating Zoom into Canvas LMS for Hybrid Virtual Classrooms | zoom canvas lms integration | ~380 | ✅ 已发布 |
| 🟢 P3 | Building a Student Performance Dashboard with Grafana and Moodle Data | moodle grafana dashboard, lms analytics | ~290 | ✅ 已发布 |
| 🟢 P3 | Moodle Plugin Development: Building Your First Custom Activity Module | moodle plugin development, moodle custom module | ~260 | ✅ 已发布 |
| 🟢 P3 | Running Moodle on Kubernetes: Helm Chart Deployment Guide | moodle kubernetes, moodle helm chart | ~220 | ✅ 已发布 |
| 🔴 P1 | Moodle MariaDB Performance Tuning for 5,000 Concurrent Users | moodle mariadb tuning, moodle database performance | ~780 | ✅ 已发布 |
| 🔴 P1 | Moodle LDAP Authentication with Active Directory: Setup Guide | moodle ldap, moodle active directory auth | ~640 | ✅ 已发布 |
| 🟡 P2 | Installing Open edX with Tutor and Docker: Production Guide | open edx tutor install, open edx docker | ~560 | ✅ 已发布 |
| 🟡 P2 | Moodle Security Hardening Checklist for Production Servers | moodle security hardening, secure moodle server | ~520 | ✅ 已发布 |
| 🟡 P2 | Configuring Moodle SMTP Email with SPF and DKIM to Avoid Spam | moodle smtp setup, moodle email not sending | ~470 | ✅ 已发布 |
| 🟡 P2 | Load Balancing Moodle with HAProxy for High Availability | moodle haproxy, moodle high availability | ~410 | ✅ 已发布 |
| 🟢 P3 | Speeding Up Moodle Globally with Cloudflare CDN Caching | moodle cloudflare, moodle cdn setup | ~350 | ✅ 已发布 |
| 🟢 P3 | Automating Moodle Deployment with Ansible Playbooks | moodle ansible, automate moodle deployment | ~300 | ✅ 已发布 |
| 🟢 P3 | Troubleshooting Moodle Cron Jobs and Scheduled Tasks | moodle cron not running, moodle scheduled tasks | ~280 | ✅ 已发布 |
| 🟢 P3 | GDPR Compliance in Moodle: Data Privacy Configuration | moodle gdpr, moodle data privacy | ~240 | ✅ 已发布 |

### 6.1 高 CPC 买家意图选题（广告变现方向 · 真实 Keyword Planner 数据 2026-06-17）

> 数据来源：Google Keyword Planner（地区 US）。搜索量为真实区间，CPC 为页首广告高价（决定 AdSense 收入）。
> 全部为"低竞争 + 高出价"的夹缝词，新站可排。文章形态为 LMS 选型/对比/榜单（命中 `is_buyer_guide` 走买家指南 prompt）。

| 优先级 | 建议文章标题 | 核心长尾词 | 月搜索量 / CPC | 状态 |
|--------|------------|-----------|------------|------|
| 🔴 P1 | Best Self-Hosted LMS: Open-Source Platforms Compared | best self hosted lms, open source lms, open learning management system | 1K-10K / $30-59 | ⬜ 待写 |
| 🔴 P1 | Best LMS for Customer Training (2026) | customer training lms, best lms for customer training, customer lms | 100-1K / $254-269 | ⬜ 待写 |
| 🔴 P1 | Best Enterprise LMS for Corporate Training | best enterprise lms, lms for corporate training, corporate lms | 100-1K / $93-230 | ⬜ 待写 |
| 🔴 P1 | Cloud-Based LMS: The Complete Buyer's Guide | cloud based lms, cloud lms, hosted lms | 10K-100K / $86-108 | ⬜ 待写 |
| 🟡 P2 | Best LMS for Healthcare & Compliance Training | healthcare lms, lms compliance training, compliance lms | 100-1K / $116-159 | ⬜ 待写 |
| 🟡 P2 | Best LMS for Nonprofits | lms for nonprofits, best lms for nonprofits | 100-1K / $155-187 | ⬜ 待写 |
| 🟡 P2 | Best LMS for Retail, Restaurants & Hospitality | lms for retail, best lms for restaurants, hospitality lms | 100-1K / $100-450 | ⬜ 待写 |
| 🟡 P2 | What Is a SCORM-Compliant LMS? (+ Best Options) | scorm compliant lms, scorm lms | 100-1K / $68-124 | ⬜ 待写 |
| 🟢 P3 | White Label LMS Platforms Compared | white label lms, white label e learning platform | 100-1K / $123-128 | ⬜ 待写 |
| 🟢 P3 | Gamified LMS: Best Platforms for Engagement | gamified lms, gamified learning management system | 100-1K / $124 | ⬜ 待写 |
| 🟢 P3 | How Much Does an LMS Cost? Pricing Guide 2026 | lms cost, learning management system cost | 100-1K / $59-71 | ⬜ 待写 |
| 🟢 P3 | Best Free LMS Platforms (2026) | free online lms, free lms online | 100-1K / $70 | ⬜ 待写 |

**当前已覆盖的核心关键词（禁止重复）：**
- Docker + Moodle 自建 LMS
- Neo4j 知识图谱 + 教育
- Canvas LMS Python REST API
- BigBlueButton + Scalelite 扩展
- Moodle SAML2 + Azure AD SSO
- AWS Lambda 作业查重
- xAPI + LRS 替代 SCORM
- Docker 自动评分系统
- Prometheus + Grafana LMS 监控
- PostgreSQL ETL 迁移旧 SIS
- Keycloak 校园 SSO
- Nextcloud 替代 Google Workspace
- Moodle PHP-FPM + Redis 性能调优
- Moodle Docker Ubuntu 22.04 安装
- 02687 品牌关键词
- Moodle vs Canvas 对比
- Moodle Redis 故障复盘 Post-Mortem
- **Moodle HTTPS + Nginx + Let's Encrypt**
- **Moodle 自动备份 AWS S3 + rclone**

---

## 七、关键配置文件速查

| 需求 | 修改哪个文件 | 具体字段 |
|------|-------------|---------|
| 修改网站描述 | `hugo.toml` | `[params]` → `description` |
| 修改导航栏菜单 | `config/_default/menus.en.toml` | `[[main]]` 区块 |
| 修改首页文字 | `data/en/homepage.yml` | 各区块的 content 字段 |
| 修改版权年份 | `config/_default/languages.toml` | `copyright` 字段 |
| 添加 Google Analytics | `hugo.toml` | `google_analytics_id = "G-XXXXXXXXXX"` |
| 启用邮件订阅 | `hugo.toml` | `[params.subscription]` → `enable = true` + 填入 Mailchimp URL |
| 修改作者 Bio | `content/english/author/alex-chen.md` | 正文内容 |
| 配置 Giscus 评论 | `layouts/_default/single.html` | `data-repo-id` 和 `data-category-id` |

---

## 八、待配置项（目前暂时禁用）

- [ ] **Google Search Console**：立即注册并提交 `https://02687.com/sitemap.xml`（最高优先级！）
- [ ] **Google Analytics 4**：申请 GA4 → 将 Measurement ID 填入 `hugo.toml` 的 `google_analytics_id`
- [ ] **Google AdSense**：文章量达到 20+ 篇后提交申请 → 通过后统一批量插入广告代码替换各文章
- [ ] **Mailchimp 邮件订阅**：注册账号 → 创建 Audience → 获取 Form Action URL → 填入 `hugo.toml` → `enable = true`
- [ ] **Giscus 评论系统**：访问 https://giscus.app 获取真实 `data-repo-id` 和 `data-category-id`，替换 `layouts/_default/single.html` 中的占位符
