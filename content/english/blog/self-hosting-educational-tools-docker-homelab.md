---
title: "Self-Hosting Educational Tools using Docker and HomeLab"
date: 2024-05-03T10:00:00+08:00
image: "images/blog/blog-post-1.jpg"
author: "EdTech Architect"
type: "post"
categories: ["Infrastructure & Cloud", "Dev Log"]
tags: ["Docker", "HomeLab", "Self-Hosted LMS", "Moodle", "Nginx"]
description: "A practitioner's guide to self-hosting a full EdTech stack using Docker Compose. Covers Moodle, Redis caching, and Nginx reverse proxy, with real-world Gotchas on volume permissions and PHP-FPM tuning."
---

When designing IT infrastructure for higher education, the default choice for the past decade has been handing over data to massive SaaS providers. But as budget constraints tighten and data privacy concerns (GDPR, student data sovereignty) become critical, universities and independent educators are re-evaluating on-premise or privately hosted cloud solutions.

I've spent years deploying massive infrastructure. Honestly, the barrier to entry for self-hosting has completely evaporated thanks to containerization. Today, I want to talk about leveraging a HomeLab environment—or a dedicated bare-metal server—to self-host an entire educational technology stack using Docker.

<!-- ADSENSE_INSERT_HERE -->

## Why Self-Host in EdTech?

I initially thought managing a self-hosted LMS (Learning Management System) would be a maintenance nightmare because of database migrations and PHP dependencies. But it failed horribly *only* when I tried to install everything directly on a Linux VM. Once you wrap these services in Docker, the paradigm shifts entirely.

1. **Absolute Data Control:** Student analytics, gradebooks, and forum discussions stay on your disks.
2. **Cost Efficiency:** A $40/month bare-metal server can easily handle 500+ concurrent students if configured with proper caching (Redis/Memcached), whereas SaaS LMS solutions charge astronomical per-user licensing fees.
3. **Customization:** Need a specific Python-based autograder plugin? You have root access. You aren't blocked by a vendor's closed API.

## The Architecture: A Minimal EdTech Stack

Let's build a functional, production-ready stack. We need:

- A reverse proxy (Nginx) to handle SSL certificate termination automatically.
- The LMS core (we will use Moodle as an example, though Canvas LMS open-source is another option).
- A database backend (MariaDB).
- An in-memory cache (Redis) to ensure the LMS doesn't crawl to a halt during exam week.

## The Docker Compose Blueprint

Here is the exact `docker-compose.yml` structure I use when prototyping a new department-level LMS deployment. Notice how we isolate the database and cache from public access using an internal Docker network.

```yaml
version: '3.8'

services:
  mariadb:
    image: bitnami/mariadb:10.11
    environment:
      - MARIADB_USER=moodle_user
      - MARIADB_PASSWORD=super_secure_password
      - MARIADB_DATABASE=moodle_db
      - MARIADB_ROOT_PASSWORD=root_secure_password
    volumes:
      - mariadb_data:/bitnami/mariadb
    restart: always
    networks:
      - edtech_net

  redis:
    image: bitnami/redis:7.0
    environment:
      - ALLOW_EMPTY_PASSWORD=yes
    restart: always
    networks:
      - edtech_net

  moodle:
    image: bitnami/moodle:4.2
    ports:
      - "8080:8080"
      - "8443:8443"
    environment:
      - MOODLE_DATABASE_HOST=mariadb
      - MOODLE_DATABASE_PORT_NUMBER=3306
      - MOODLE_DATABASE_USER=moodle_user
      - MOODLE_DATABASE_PASSWORD=super_secure_password
      - MOODLE_DATABASE_NAME=moodle_db
      - MOODLE_CACHE_DRIVER=redis
      - MOODLE_REDIS_HOST=redis
    volumes:
      - moodle_data:/bitnami/moodle
      - moodledata_data:/bitnami/moodledata
    depends_on:
      - mariadb
      - redis
    restart: always
    networks:
      - edtech_net

volumes:
  mariadb_data:
  moodle_data:
  moodledata_data:

networks:
  edtech_net:
    driver: bridge
```

## Nginx Reverse Proxy: Terminating SSL at the Edge

Running Moodle on port 8080 internally is fine, but exposing it raw to the internet is not. We place an Nginx container in front that handles HTTPS termination and enforces secure headers:

```nginx
server {
    listen 80;
    server_name lms.yourdomain.edu;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name lms.yourdomain.edu;

    ssl_certificate     /etc/letsencrypt/live/lms.yourdomain.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lms.yourdomain.edu/privkey.pem;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";

    client_max_body_size 512M;

    location / {
        proxy_pass         http://moodle:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

The `client_max_body_size 512M` line is a frequent source of confusion. Moodle's own PHP upload limit must match this value — set `upload_max_filesize` and `post_max_size` accordingly in `php.ini`, otherwise students uploading large video assignments will get cryptic 413 errors.

## The "Gotchas" of Deployment

**1. Permissions and Volumes**

If you just spin this up on a raw Ubuntu server, you might hit `permission denied` errors on the `moodledata_data` volume. Bitnami images run as a non-root user (usually UID 1001). You have to ensure the host directory has the correct ownership before first boot.

```bash
sudo chown -R 1001:1001 /path/to/your/docker/volumes
```

**2. Handling Real-Time Traffic Spikes**

During my first large-scale pilot test at a regional institution, the system crashed during a concurrent quiz submission. The bottleneck wasn't CPU — it was PHP-FPM workers getting exhausted waiting on database locks.

The fix? Aggressive Redis caching. The `MOODLE_CACHE_DRIVER=redis` variable in the compose file above is not optional for production. It shifts session management and course structure caching directly into RAM. For a deep dive into sizing PHP-FPM worker pools correctly for your server's RAM, see our detailed guide on [Moodle Performance Tuning: PHP-FPM Workers, Redis Cache, and OPcache](/blog/moodle-performance-tuning-php-fpm-redis-opcache/).

**3. Database Slow Query Log**

MariaDB's slow query log is your best friend when diagnosing Moodle hangs. Enable it by adding these flags to your MariaDB environment block:

```yaml
- MARIADB_EXTRA_FLAGS=--slow-query-log=1 --slow-query-log-file=/tmp/slow.log --long-query-time=2
```

Queries taking more than 2 seconds almost always point to a missing database index. Moodle's built-in environment checker (`/admin/index.php`) will flag most of these, but production load sometimes reveals additional gaps.

## Scaling Beyond the LMS

Once the LMS is containerized, your HomeLab or cloud instance becomes a playground. You can easily add services like **Nextcloud** (for secure document distribution replacing Google Drive), **BigBlueButton** (for open-source video conferencing), or **Gitea** (for computer science students to submit code).

For production deployments serving hundreds of concurrent users, add a monitoring layer early. Our article on [Prometheus and Grafana for LMS Performance Monitoring](/blog/prometheus-grafana-lms-monitoring/) walks through the exact PromQL queries and alert rules we use to detect PHP-FPM saturation and database connection pool exhaustion before they become outages.

The digital transformation of education isn't just about buying new software; it's about reclaiming the infrastructure. By standardizing on Docker, institutions can deploy complex, resilient environments in minutes rather than months.

In the next post of this Dev Log, I'll walk through how we can write a custom Python script to automatically synchronize student rosters from a legacy SIS (Student Information System) directly into our new containerized LMS using its REST API. If you need a step-by-step installation walkthrough including SSL and database setup from scratch, our guide on [Installing Moodle on Ubuntu 22.04 with Docker Compose](/blog/installing-moodle-ubuntu-22-04-docker-compose/) picks up exactly where this post leaves off.
