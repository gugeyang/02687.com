---
title: "Installing Open edX with Tutor and Docker: Production Guide"
date: 2026-06-01T00:09:09+08:00
image: "images/blog/blog-post-7.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud"]
tags: ["Docker", "Open edX"]
description: "Learn how to perform a production-ready open edx tutor install using open edx docker with my step-by-step performance optimizations and configurations."
---

I spent 14 consecutive hours in a cold server room in Singapore debugging a catastrophic database deadlock on a fresh Open edX installation. It was the first day of the semester for 12,000 students, and the default Docker Compose configuration had simply choked under the sudden wave of logins. Elasticsearch ran out of memory, which triggered a cascade that caused Django to pool connections until MySQL refused any new inputs. The native platform crashed, returning a cold 502 Bad Gateway to thousands of angry students. 

If you are deploying Open edX today, you are likely using Tutor, the community-approved, Docker-based orchestration tool. While Tutor makes the initial setup feel as simple as running a single CLI command, deploying it in a high-concurrency production environment requires deep, non-standard architectural configurations. Here is my battle-tested guide to getting an **open edx tutor install** running on **open edx docker** containers without experiencing the same production outages I had to learn from the hard way.

## The 32GB Trap: Sizing Your Open edX Docker Hardware Correctly

Many tutorials claim you can run Open edX on a 4GB or 8GB RAM virtual machine. That is a flat lie for production environments. While Tutor can boot on an 8GB instance for local development, a production stack spawns over two dozen Docker containers: the LMS, CMS (Studio), MySQL, MongoDB, Elasticsearch, Redis, Caddy, and various worker processes. 

If you attempt to run a production load on anything less than **32GB of RAM and 8 vCPUs**, the Linux Out-Of-Memory (OOM) killer will eventually terminate your Elasticsearch or MySQL container during a background cron job or a grading run. 

For up to 8,000 active users with a target response time under 300ms, my baseline recommendation is:

*   **Compute:** 8 vCPUs (Intel Xeon or AMD EPYC dedicated cores; avoid shared-CPU instances)
*   **Memory:** 32GB RAM (with at least 4GB of swap space configured on NVMe)
*   **Storage:** 150GB NVMe SSD. Open edX is highly I/O dependent, especially during forum database writes and course state saves.
*   **OS:** Ubuntu 22.04 LTS (Docker Engine runs cleanest here with the native systemd driver)

I wish someone had told me before starting that Open edX's default logging configuration inside Docker containers is non-existent. Without custom Docker log rotation, JSON log files will grow unchecked, consuming 100GB of disk space in under 45 days, causing the Docker daemon to lock up completely.

## Production-Ready Open edX Tutor Install Configuration

Before initializing Tutor, we must craft a robust config file. Do not run the interactive quickstart wizard blindly. Instead, write a declarative configuration that limits resources and prepares your instance for production scaling.

If you are running a multi-tenant university environment, you will likely need a unified identity provider; in my past projects, I integrated this setup by [building a campus-wide single sign-on (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/) to handle centralized student identities across both Moodle and Open edX.

Create your configurations at `$(tutor config printroot)/config.yml`. Here is a production-hardened configuration file that isolates the database hosts, sets production domains, and enforces strict security protocols:

```yaml
# /home/ubuntu/.local/share/tutor/config.yml
AMQP_HOST: rabbitmq
AMQP_PASSWORD: 'your-ultra-secure-rabbitmq-password-here'
AMQP_PORT: 5672
AMQP_USER: guest
CADDY_HTTP_PORT: 80
CADDY_HTTPS_PORT: 443
CMS_HOST: studio.academy.edu
LMS_HOST: lms.academy.edu
DATABASE_HOST: mysql
DATABASE_PASSWORD: 'your-highly-random-mysql-password-993'
DATABASE_USER: tutor
EDX_PLATFORM_REPOSITORY: https://github.com/openedx/edx-platform.git
EDX_PLATFORM_VERSION: open-release/redwood.master
ELASTICSEARCH_HOST: elasticsearch
ELASTICSEARCH_PORT: 9200
ENABLE_STUDIO: true
ENABLE_HTTPS: true
MONGODB_HOST: mongodb
MONGODB_PORT: 27017
MYSQL_DATABASE: openedx
REDIS_HOST: redis
REDIS_PORT: 6379
SECRET_KEY: 'generate-a-128-character-random-string-for-production-signing'
TUTOR_EDX_APP_SETTINGS_PRODUCTION: |
  # Custom Django Settings
  MAX_STUDENT_ENROLLMENTS_PER_COURSE = 10000
  FEATURES['ENABLE_DISCUSSION_SERVICE'] = True
  FEATURES['PREVIEW_LMS_BASE'] = "preview.academy.edu"
```

## Step-by-Step Shell Script for Orchestrating the Open edX Docker Deployment

With the configuration initialized, we run a deployment script to configure Docker, apply security parameters, download dependencies, and boot the containers. Run this sequence as a non-root user with `sudo` privileges.

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Update OS and install absolute prerequisites
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl git apt-transport-https ca-certificates gnupg lsb-release

# 2. Install Docker Engine cleanly (do not use snap)
if ! command -v docker &> /dev/null; then
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker $USER
fi

# 3. Configure Docker Daemon JSON for log rotation to prevent disk exhaustion
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  },
  "exec-opts": ["native.cgroupdriver=systemd"]
}
EOF
sudo systemctl restart docker

# 4. Install Tutor binary
TUTOR_VERSION="v18.0.0" # Use the latest stable release (e.g., Redwood)
sudo curl -L "https://github.com/overhangio/tutor/releases/download/${TUTOR_VERSION}/tutor-$(uname -s)-$(uname -m)" -o /usr/local/bin/tutor
sudo chmod +x /usr/local/bin/tutor

# 5. Initialize config directory and move customized config.yml
mkdir -p ~/.local/share/tutor
# (Make sure config.yml from previous step is located at ~/.local/share/tutor/config.yml)

# 6. Run non-interactive initialization
tutor config save
tutor local launch --non-interactive
```

This launch phase will download all required base images from Docker Hub, configure Caddy to generate automatic Let's Encrypt TLS certificates, run database migrations, compile asset pipelines (Sass and Webpack), and spin up the background Celery workers.

## The Three Gotchas That Will Crash Your Production Tutor Environment

After performing dozen of migrations and emergency recoveries across the Asia-Pacific region, I have noticed three recurring failure modes that routinely drop production sites offline.

### Gotcha 1: Elasticsearch JVM Heap Under-Allocation
Tutor's default Docker compose configuration runs Elasticsearch without specifying JVM heap sizes. In a standard setup, Elasticsearch tries to allocate up to 50% of system memory, which triggers Docker OOM faults, or it uses far too little, resulting in search indexing timeouts when students search through forum threads or course pages.

*   **The Fix:** Create a Tutor patch to set the JVM options. Run `tutor plugins save` with a custom patch that overrides the environment variables of the Elasticsearch service, forcing:
    ```yaml
    ES_JAVA_OPTS: "-Xms4g -Xmx4g"
    ```
    This guarantees that Elasticsearch gets a stable, non-leaking memory partition.

### Gotcha 2: MongoDB Journaling Disk Saturation
When 5,000+ students are interacting with course blocks, the `edxapp` service writes persistent states to MongoDB. If your database write speed falls behind, MongoDB threads will block. 

*   **The Fix:** You must map the MongoDB data volumes to an NVMe drive with high input/output operations per second (IOPS) and verify your kernel scheduler uses `none` or `kyber` instead of the legacy `mq-deadline` to avoid I/O bottlenecks.

### Gotcha 3: Database Migration Deadlocks During Upgrades
When transitioning between major Open edX versions (for example, upgrading from Palm to Redwood), the MySQL schema migrations (`tutor local upgrade --check`) often attempt to drop index tables while background tasks are still running.

*   **The Fix:** Always spin down the Celery workers first before running any database migrations:
    ```bash
    tutor local stop lms-worker cms-worker
    tutor local upgrade --check
    tutor local start -d
    ```

When managing high-volume enrollments, relying solely on manual registrations or native Open edX APIs can slow down your operations; having worked on both platforms, I found that [automating Canvas LMS enrollments using Python and REST APIs](/blog/automating-canvas-lms-enrollments/) taught me design patterns that I directly applied to writing custom sync scripts for Tutor's MySQL database.

## Architecture Trade-offs: Single-Instance Tutor vs. Multi-Node Kubernetes

I take a hard stance here: **Do not deploy Open edX on Kubernetes via the Tutor K8s plugin unless you have at least three full-time DevOps engineers dedicated to maintaining that cluster.** 

While Kubernetes offers horizontal scaling, the sheer overhead of stateful sets (MySQL, MongoDB, Elasticsearch, Redis) on Kubernetes creates a highly complex, fragile ecosystem that is incredibly difficult to debug.

For performance visualization, instead of relying on default metrics, I recommend externalizing logs to Prometheus; this is very similar to the approach I detailed on [building a student performance dashboard with Grafana and Moodle data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/) which can be adapted to Tutor's Clickhouse tracking logs to monitor slow-loading components.

Here is the trade-off matrix I present to university boards:

| Architectural Metric | Single-Instance Docker Compose (Scale Up) | Multi-Node Kubernetes (Scale Out) |
| :--- | :--- | :--- |
| **Max Concurrent Users** | ~15,000 active students | Unlimited |
| **Recovery Strategy** | Daily block-level snapshot backups | Complex cluster state (etcd) restore |
| **Monthly Cloud Bill** | ~$180 (64GB RAM Dedicated Server) | ~$950+ (EKS/GKE master + nodes + volumes) |
| **Upgrade Risk** | Low (Single CLI command rollbacks) | High (Helm chart conflicts, PV binding errors) |

My recommendation for 90% of universities is to use a vertically scaled single-instance Open edX Docker deployment. Run it on high-performance bare metal cloud servers (like those from Hetzner or OVHcloud) with automated daily off-site backups to an S3 bucket. You will save thousands of dollars a month and sleep soundly through the night.