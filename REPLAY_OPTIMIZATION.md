# REPLAY_OPTIMIZATION.md — 02687.com 网站优化变更记录

---

## [2026-05-04] 网站诊断与全面修复 (v1.0)

### 背景
对整个 Hugo 项目进行了系统性代码审查，发现并修复了严重威胁 Google AdSense 审核和 SEO 排名的多个问题。

---

### 🔴 高危修复（已完成）

#### 1. 删除 6 篇 Lorem Ipsum 占位垃圾文章
- **问题**: `blog-post-1.md` ~ `blog-post-6.md` 均包含 "Elegant Light Box Paper Cut Dioramas" 假标题、虚构作者 "John Doe"、Lorem ipsum 内容，2019 年日期严重错位。
- **影响**: Google 将此类内容定性为 "thin content"，是 AdSense 申请被拒的最高频原因。
- **修复**: 使用 `Remove-Item` 永久删除全部 6 个文件。

#### 2. 修复博客 `_index.md` 假 meta description
- **问题**: `description: "this is meta description"` —— 占位符直接暴露在 Google 搜索结果摘要中。
- **修复**: 替换为含核心关键词的真实描述（EdTech infrastructure, Docker, Canvas API...）。
- **同步**: 将 title 从 "Latest News" 改为 "Dev Log & Technical Articles"，更具 SEO 价值。

#### 3. 修复 Course 页面 `_index.md` 的 Lorem Ipsum 描述
- **问题**: `description: "Lorem ipsum dolor sit amet..."` —— 对 SEO 毫无价值，且是 AdSense 审核红灯。
- **修复**: 替换为精准描述 Solutions 页面内容的 EdTech 关键词描述。
- **同步**: 将 title 从 "Our Courses" 改为 "EdTech Solutions & Pedagogy"，与导航菜单文字一致。

#### 4. 禁用 Mailchimp 订阅（安全合规）
- **问题**: `mailchimp_form_action` 指向一个陌生账号的 URL（`u=463ee871f45d2d93748e77cad`），用户提交的邮件会流入他人账户。
- **修复**: `enable = false`，清空 form action 和 form name，添加注释说明需填入真实账号后再启用。

#### 5. 禁用 Google Maps（安全 & 合规）
- **问题 1**: `gmap_api` 字段含有硬编码的 Google Maps API Key，存在密钥暴露风险。
- **问题 2**: 坐标（51.5223477, -0.1622023）指向**伦敦 Notting Hill**，与"Global EdTech Hub"定位完全不符。
- **修复**: `enable = false`，清空 API Key 和坐标，添加注释供未来配置。

---

### 🟡 中优先级修复（已完成）

#### 6. 修正 hugo.toml 拼写错误
- **问题**: `google_analitycs_id`（少了字母 y），若日后填入 GA4 ID 配置将完全失效。
- **修复**: 改为 `google_analytics_id`。

#### 7. 更新版权年份
- **问题**: `languages.toml` 中版权年份硬编码为 2024，网站现为 2026 年运营。
- **修复**: 更新为 `Copyright © 2026 02687.com`。

#### 8. 删除博客文章中的中文括注
- **问题**: `building-next-gen-knowledge-graph.md` 第 9 行含有 `(知识图谱)`，违反纯英文要求，影响广告单价（CPC）定向。
- **修复**: 删除括号中文，保留纯英文句子。

#### 9. 为所有 12 篇正式博客文章补充 SEO 元数据
- **问题**: 所有正式文章的 front matter 均缺少 `categories`、`tags`、`description` 三个字段。
- **影响**: Google 无法进行主题聚类，内部链接权重无法传递，搜索结果摘要为空。
- **修复**: 为以下所有文章补充了精准的三元元数据：

| 文章 | categories | 关键 tags |
|------|-----------|-----------|
| self-hosting-educational-tools-docker-homelab | Infrastructure & Cloud, Dev Log | Docker, HomeLab, Moodle, Nginx |
| building-next-gen-knowledge-graph | Data & AI, Dev Log | Knowledge Graph, Neo4j, Python |
| automating-canvas-lms-enrollments | Dev Log, Infrastructure & Cloud | Canvas LMS, Python, REST API |
| building-campus-wide-sso-keycloak | Security, Infrastructure & Cloud | Keycloak, SSO, IAM, Nginx |
| containerizing-auto-grading-pipelines-docker | Dev Log, Infrastructure & Cloud | Docker, Auto-Grading, Celery |
| deploying-nextcloud-secure-alternative | Infrastructure & Cloud | Nextcloud, Ceph, S3, Kubernetes |
| implementing-saml-sso-moodle | Security, Infrastructure & Cloud | SAML 2.0, Moodle, SSO, Azure AD |
| lms-to-lrs-with-xapi | Data & AI | xAPI, LRS, AWS Kinesis, SCORM |
| migrating-legacy-sis-data-postgresql | Data & AI, Dev Log | PostgreSQL, Python, ETL |
| prometheus-grafana-lms-monitoring | Infrastructure & Cloud | Prometheus, Grafana, PromQL |
| scaling-bigbluebutton-10k-students | Infrastructure & Cloud | BigBlueButton, WebRTC, Scalelite |
| serverless-plagiarism-detection-pipeline | Dev Log, Data & AI | Serverless, AWS Lambda, MOSS |

---

### 待办事项（未来迭代）
- [ ] 注册真实 Mailchimp 账号后，填入正确的 form action URL 并重新启用订阅组件
- [ ] 申请自有 Google Maps API Key，填入正确坐标（或保持禁用状态）
- [ ] 注册 Google Analytics 4，填入 `google_analytics_id`
- [ ] 在 `CONTENT_MASTER_RECORD.md` 中更新所有文章的 categories 和 tags 信息

