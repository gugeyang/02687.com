# Content Master Record (内容总控文档)

**用途**: 记录已生成的文章列表、核心摘要和关键词，确保后续生成的内容不重复，且 SEO 覆盖面不断扩大。

## 已发布文章记录表

| 日期 | 标题 | 分类 / 标签 | 核心关键词 | 摘要简述 |
| :--- | :--- | :--- | :--- | :--- |
| 2024-05-03 | Self-Hosting Educational Tools using Docker and HomeLab | Dev Log, Infrastructure & Cloud | Docker, HomeLab, Self-Hosted LMS | 探讨使用 Docker 和 HomeLab 架构自建教育基础设施（如 Moodle），包含具体 docker-compose 配置与性能避坑指南。 |
| 2024-05-04 | Building the Next-Gen Knowledge Graph for Modern Universities | Data & AI, Dev Log | Knowledge Graph, Neo4j, Python, Curriculum Mapping | 探讨知识图谱在现代教育中的应用，提供具体的 Neo4j 架构与 Python 数据注入代码，分享关系型数据库转型为图数据库的核心优势。 |
| 2024-05-05 | Automating Canvas LMS Enrollments Using Python and REST APIs | Dev Log, Infrastructure & Cloud | Canvas LMS, Python, REST API, Automation | 探讨如何使用 Python 和 Canvas REST API 自动化学生注册流程，提供重试逻辑与错误处理的代码实践。 |
| 2024-05-06 | Scaling BigBlueButton Video Conferencing for 10,000 Concurrent Students | Infrastructure & Cloud | BigBlueButton, WebRTC, Scalelite, Load Balancing | 分享横向扩展 BigBlueButton 以支持万名并发学生的架构经验，涵盖 Scalelite 负载均衡与 UDP/TURN 服务器配置。 |
| 2024-05-07 | Implementing SAML/SSO Authentication in Moodle | Security, Infrastructure & Cloud | SAML 2.0, Moodle, SSO, Azure AD | 详细讲解在 Moodle 中集成 SAML/SSO 的架构方法，解析 auth_saml2 插件配置、证书管理及 XML 属性调试技巧。 |
| 2024-05-08 | Building a Serverless Plagiarism Detection Pipeline | Dev Log, Data & AI | Serverless, AWS Lambda, Python, Plagiarism Detection | 介绍如何利用 AWS Lambda, S3 和 MOSS 引擎构建无服务器的作业查重流水线，以应对期末高并发提交的挑战。 |
| 2024-05-09 | Moving from an LMS to a Learning Record Store (LRS) with xAPI | Data & AI | xAPI, LRS, Data Lake, AWS Kinesis | 探讨从传统 SCORM LMS 向 xAPI 与 LRS 架构转型的技术细节，展示如何构建实时学习数据接入流水线。 |
| 2024-05-10 | Containerizing Auto-Grading Pipelines with Docker | Dev Log, Infrastructure & Cloud | Docker, Auto-Grading, Python, Celery | 探讨使用 Docker 和 Kubernetes 容器化自动化代码评分系统的架构设计，包含 Python 资源限制代码与并发处理指南。 |
| 2024-05-11 | Using Prometheus and Grafana for LMS Performance Monitoring | Infrastructure & Cloud | Prometheus, Grafana, LMS, Monitoring | 分享基于 Prometheus 与 Grafana 构建 LMS 性能监控流水线的实践，包含 PromQL 报警规则与 PostgreSQL 导出器配置。 |
| 2024-05-12 | Migrating Legacy SIS Data to PostgreSQL using Python | Data & AI, Dev Log | PostgreSQL, Python, ETL, Legacy SIS | 详细解析使用 Python 流式处理将传统教务系统 (SIS) 迁移至 PostgreSQL 的 ETL 方案，包含应对脏数据及编码问题的代码示例。 |
| 2024-05-13 | Building a Campus-Wide Single Sign-On (SSO) with Keycloak | Security, Infrastructure & Cloud | Keycloak, SSO, IAM, Nginx | 分享在高校部署基于 Keycloak 的统一身份认证 (SSO) 系统的经验，讲解活动目录联邦与 Nginx 反向代理配置细节。 |
| 2024-05-14 | Deploying Nextcloud as a Secure Alternative to Google Workspace for Education | Infrastructure & Cloud | Nextcloud, Ceph, S3, Kubernetes | 探讨自托管 Nextcloud 集群作为教育云存储替代方案的架构，介绍 S3/Ceph 存储后端配置及后台作业性能优化方案。 |
| 2026-05-05 | Moodle Performance Tuning: PHP-FPM Workers, Redis Cache, and OPcache | Infrastructure & Cloud, Dev Log | Moodle, PHP-FPM, Redis, OPcache, Performance Tuning | 针对生产环境的 Moodle 性能调优实战指南，涵盖 PHP-FPM Worker 池大小计算、Redis MUC 会话缓存配置、OPcache 参数设置，附基准测试数据。 |
| 2026-05-05 | Installing Moodle on Ubuntu 22.04 with Docker Compose: Step-by-Step Guide | Infrastructure & Cloud, Dev Log | Moodle, Docker Compose, Ubuntu 22.04, MariaDB, Nginx | 从零开始在 Ubuntu 22.04 上使用 Docker Compose 部署 Moodle 的完整指南，含 MariaDB、Redis、Nginx 反向代理、Let's Encrypt SSL 配置及踩坑记录。 |
