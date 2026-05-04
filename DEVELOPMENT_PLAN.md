# 02687.com 网站开发与内容运营规划文档 (v5.0 - SEO Production Edition)

> ⚠️ **任何接手本项目的 AI 代理，无论使用什么模型，在执行任何写代码或写文章的操作前，必须首先通读并严格遵守本文件的全部内容！本文件是最高优先级的操作手册。**

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
| `content/english/contact/_index.md` | Contact 页面 | 偶尔 |
| `content/english/privacy-policy.md` | 隐私政策 | 几乎不动 |
| `data/en/homepage.yml` | 首页各区块文字 | 偶尔 |
| `hugo.toml` | 全站配置 | 偶尔 |
| `config/_default/menus.en.toml` | 导航栏链接 | 偶尔 |
| `CONTENT_MASTER_RECORD.md` | 已发布文章总控表，防重复 | **每次发文后必填** |
| `public/` 目录 | Hugo 编译输出，**禁止手动碰** | ❌ |
| `.github/workflows/hugo.yaml` | 自动部署脚本，**禁止修改** | ❌ |

---

## 二、本地预览（可选）

Hugo 已安装（v0.161.1）。在 PowerShell 执行：

```powershell
cd d:\02687.com
hugo server
# 浏览器访问 http://localhost:1313，文件修改后自动刷新
# Ctrl+C 停止
```

---

## 三、GitHub 发布流程（每次发文后执行）

```powershell
cd d:\02687.com
git add .
git commit -m "add: 简短描述本次新增内容"
git push
# 约 1-2 分钟后 02687.com 自动更新
```

验证：访问 `https://github.com/你的用户名/02687.com/actions` 查看是否有绿色 ✅ 任务。

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

---

## 五、写一篇新文章的完整工作流（9步强制执行）

> **AI 代理必须按此顺序执行，不得跳过任何步骤。**

---

### ★ Step 1：查阅内容总控表，选题与防重复

打开 `CONTENT_MASTER_RECORD.md`，检查：
1. 要写的**核心关键词是否已被覆盖**？（已覆盖的词不能再写同主题文章）
2. 参考"下一批推荐选题"列表优先选择搜索量较高的题目

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
date: 2026-05-04T10:00:00+08:00   # 填写真实写作日期
image: "images/blog/blog-post-3.jpg"   # 可选 blog-post-1 到 blog-post-7
author: "EdTech Architect"             # 固定，不得修改
type: "post"
categories: ["Infrastructure & Cloud"]  # 只能从以下4个中选择1-2个
tags: ["Moodle", "Docker", "Redis", "PHP-FPM", "Performance"]  # 5个左右精准标签
description: "120-155字的英文摘要。必须包含主关键词和1-2个次级长尾词。这是Google搜索结果摘要，直接影响点击率，务必写得有吸引力。"
---
```

**categories 只允许以下四个值：**
- `"Infrastructure & Cloud"` — Docker、Kubernetes、服务器、Nginx、监控
- `"Data & AI"` — 数据库、知识图谱、ETL、机器学习、数据分析
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
- **第2段结束后**：插入广告占位符 `<!-- ADSENSE_INSERT_HERE -->`

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
# Hugo 中内部链接使用相对路径
For monitoring your LMS stack, see our guide on
[Prometheus and Grafana for LMS Performance Monitoring](/blog/prometheus-grafana-lms-monitoring/).

If you're also managing student identities, our
[Keycloak SSO Campus Deployment guide](/blog/building-campus-wide-sso-keycloak/)
walks through the full federation setup.
```

**内部链接选题原则：**
- 链接到**主题相关**的文章（Docker 文章 → 链接其他 Docker/Kubernetes 文章）
- 链接锚文本必须是**描述性关键词**，禁止用 "click here"、"read more" 这类无意义锚文本
- 优先链接到**流量较高**的文章（让权重从新文章流向已有排名的文章）

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

---

### ★ Step 7：插入广告占位符（位置固定）

在**第二段正文结束后**（开篇故事/背景描述结束，正式进入技术内容之前）插入：

```html
<!-- ADSENSE_INSERT_HERE -->
```

这个位置是 AdSense 广告效果最佳的热区（用户刚读完背景，进入正文前的停顿点）。

---

### ★ Step 8：写作完成后的自检清单

在提交前，AI 代理必须逐项确认：

- [ ] Front matter 包含：`title`、`date`、`image`、`author`、`type`、`categories`、`tags`、`description`
- [ ] `description` 字段是 120-155 字的精炼英文摘要，包含主关键词
- [ ] 文件名包含主关键词，全小写，连字符分隔
- [ ] 至少 4 个 H2 标题，每个都嵌入了具体的长尾词或技术词
- [ ] 包含至少 1 个完整的代码块（YAML/Python/Bash/等）
- [ ] 包含"Gotchas"或踩坑小节
- [ ] 包含至少 2 条指向站内其他文章的内部链接
- [ ] `<!-- ADSENSE_INSERT_HERE -->` 在第二段正文后
- [ ] 全文无中文字符
- [ ] 全文无 Lorem Ipsum 占位文字
- [ ] 全文无"John Doe"、真实商业品牌名等违规内容
- [ ] 字数在 1000-1500 词之间

---

### ★ Step 9：登记到内容总控表

写完文章后，立即打开 `CONTENT_MASTER_RECORD.md`，在表格末尾追加一行：

```
| 2026-05-04 | 文章标题 | 分类, Dev Log | 主关键词, 长尾词1, 长尾词2 | 一句话摘要 |
```

然后执行 git push 发布。

---

## 六、下一批推荐选题（按 SEO 优先级排序）

以下选题已经过关键词搜索量分析，按优先级排序。**写文章时优先从这里选题**：

| 优先级 | 建议文章标题 | 核心长尾词 | 估计月搜索量 |
|--------|------------|-----------|------------|
| 🔴 P1 | Moodle Performance Tuning: PHP-FPM Workers, Redis Cache, and OPcache | moodle performance tuning, moodle redis cache | ~1,200 |
| 🔴 P1 | Installing Moodle on Ubuntu 22.04 with Docker Compose: Step-by-Step | moodle docker ubuntu, install moodle docker | ~880 |
| 🔴 P1 | Canvas LMS vs Moodle 2026: Technical Comparison for University IT Teams | canvas vs moodle, lms comparison university | ~720 |
| 🟡 P2 | Securing Moodle with HTTPS Using Let's Encrypt and Nginx Reverse Proxy | moodle ssl nginx, moodle https setup | ~590 |
| 🟡 P2 | Open Source LMS Comparison: Moodle vs Open edX vs Canvas vs Chamilo | open source lms comparison 2026 | ~540 |
| 🟡 P2 | Automated Moodle Backup to AWS S3 with Cron and rclone | moodle backup s3, moodle automated backup | ~430 |
| 🟢 P3 | Integrating Zoom into Canvas LMS for Hybrid Virtual Classrooms | zoom canvas lms integration | ~380 |
| 🟢 P3 | Building a Student Performance Dashboard with Grafana and Moodle Data | moodle grafana dashboard, lms analytics | ~290 |

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
| 启用 Google Maps | `hugo.toml` | `[params.map]` → `enable = true` + 填入自己的 API Key |

---

## 八、待配置项（目前暂时禁用）

- [ ] **Google Search Console**：立即注册并提交 `https://02687.com/sitemap.xml`（最高优先级！）
- [ ] **Google Analytics 4**：申请 GA4 → 将 Measurement ID 填入 `hugo.toml` 的 `google_analytics_id`
- [ ] **Google AdSense**：文章量达到 20+ 篇后提交申请 → 通过后将广告代码替换所有 `<!-- ADSENSE_INSERT_HERE -->` 占位符
- [ ] **Mailchimp 邮件订阅**：注册账号 → 创建 Audience → 获取 Form Action URL → 填入 `hugo.toml` → `enable = true`
