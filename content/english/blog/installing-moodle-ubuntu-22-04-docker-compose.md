---
title: "Installing Moodle on Ubuntu 22.04 with Docker Compose: Step-by-Step Guide"
date: 2026-05-05T14:00:00+08:00
image: "images/blog/blog-post-4.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud", "Dev Log"]
tags: ["Moodle", "Docker Compose", "Ubuntu 22.04", "MariaDB", "Nginx"]
description: "Complete step-by-step guide to deploying Moodle on Ubuntu 22.04 using Docker Compose with MariaDB, Redis, and Nginx reverse proxy. Includes SSL setup with Let's Encrypt and production-ready volume configuration."
---

Every time I get pulled into a new university IT project, the conversation starts the same way: "We tried to install Moodle directly on the server three years ago, and now nobody knows how it works or how to update it." The PHP version is pinned to something ancient, the MariaDB config is intertwined with another application, and a simple upgrade becomes a month-long project.

The solution I've standardized on for every Moodle deployment since 2021 is Docker Compose. Not because it's trendy, but because it solves the isolation problem completely. Every dependency鈥擯HP version, MariaDB version, Redis鈥攍ives in a container. The host machine stays clean. Upgrades become a controlled operation rather than a prayer.


## Moodle Docker Compose on Ubuntu 22.04: Prerequisites and System Preparation

Before writing a single line of YAML, prepare the host machine properly. Ubuntu 22.04 LTS is the correct choice 鈥?it's supported until 2027, ships with a modern kernel, and has well-maintained Docker packages.

```bash
# Update the system first 鈥?always
sudo apt update && sudo apt upgrade -y

# Install Docker Engine (not Docker Desktop)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to the docker group to avoid sudo on every command
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose plugin (v2 syntax: docker compose, not docker-compose)
sudo apt install docker-compose-plugin -y

# Verify installations
docker --version          # Should be 24.x or higher
docker compose version    # Should be 2.x
```

Create a dedicated directory for the Moodle stack:

```bash
sudo mkdir -p /opt/moodle-stack
sudo chown $USER:$USER /opt/moodle-stack
cd /opt/moodle-stack
```

## The Production-Ready Moodle Docker Compose File

This is the exact `docker-compose.yml` structure I deploy at institutions. It includes Redis for session caching and an internal network to keep database ports off the public interface:

```yaml
version: '3.8'

services:
  mariadb:
    image: bitnami/mariadb:10.11
    container_name: moodle_db
    environment:
      - MARIADB_USER=moodle_user
      - MARIADB_PASSWORD=${DB_PASSWORD}
      - MARIADB_DATABASE=moodle_db
      - MARIADB_ROOT_PASSWORD=${DB_ROOT_PASSWORD}
      - MARIADB_CHARACTER_SET=utf8mb4
      - MARIADB_COLLATE=utf8mb4_unicode_ci
    volumes:
      - mariadb_data:/bitnami/mariadb
    networks:
      - moodle_internal
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 30s
      timeout: 10s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: moodle_redis
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    networks:
      - moodle_internal
    restart: unless-stopped

  moodle:
    image: bitnami/moodle:4.3
    container_name: moodle_app
    depends_on:
      mariadb:
        condition: service_healthy
    environment:
      - MOODLE_DATABASE_HOST=mariadb
      - MOODLE_DATABASE_PORT_NUMBER=3306
      - MOODLE_DATABASE_USER=moodle_user
      - MOODLE_DATABASE_PASSWORD=${DB_PASSWORD}
      - MOODLE_DATABASE_NAME=moodle_db
      - MOODLE_USERNAME=admin
      - MOODLE_PASSWORD=${MOODLE_ADMIN_PASSWORD}
      - MOODLE_EMAIL=admin@02687.com
      - MOODLE_SITE_NAME=Global Tech University LMS
      - MOODLE_CACHE_DRIVER=redis
      - MOODLE_REDIS_HOST=redis
      - MOODLE_REDIS_PORT_NUMBER=6379
    volumes:
      - moodle_data:/bitnami/moodle
      - moodledata_data:/bitnami/moodledata
    networks:
      - moodle_internal
    restart: unless-stopped
    expose:
      - "8080"

  nginx:
    image: nginx:alpine
    container_name: moodle_nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - certbot_webroot:/var/www/certbot
    depends_on:
      - moodle
    networks:
      - moodle_internal
    restart: unless-stopped

volumes:
  mariadb_data:
  moodle_data:
  moodledata_data:
  redis_data:
  certbot_webroot:

networks:
  moodle_internal:
    driver: bridge
```

Create the `.env` file to keep credentials out of the YAML:

```bash
cat > .env << 'EOF'
DB_PASSWORD=choose_a_strong_password_here
DB_ROOT_PASSWORD=another_strong_root_password
MOODLE_ADMIN_PASSWORD=secure_admin_password_min_8_chars
EOF
chmod 600 .env
```

## Nginx Reverse Proxy Configuration for Moodle Docker on Ubuntu 22.04

The Nginx container handles SSL termination and proxies traffic to the Moodle container. Create `nginx.conf`:

```nginx
server {
    listen 80;
    server_name your-moodle-domain.com;

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-moodle-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-moodle-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-moodle-domain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options nosniff;

    client_max_body_size 100M;  # Moodle file upload limit

    location / {
        proxy_pass http://moodle:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
```

## SSL Certificate with Let's Encrypt for Moodle on Ubuntu

Obtain the certificate before starting Nginx with SSL enabled:

```bash
# Install certbot on the host (not in Docker)
sudo apt install certbot -y

# Obtain certificate 鈥?point DNS to this server first
sudo certbot certonly --standalone \
  --email admin@yourdomain.com \
  --agree-tos \
  -d your-moodle-domain.com

# Start the full stack
docker compose up -d
```

## First Boot and Initial Configuration

The first `docker compose up` takes 10-15 minutes 鈥?Moodle initializes its database schema on first run. Monitor progress:

```bash
docker logs -f moodle_app
# Wait until you see: "moodle setup finished!"
```

After initialization, log in at `https://your-domain.com` with the admin credentials from your `.env` file.

## The "Gotchas" of Running Moodle in Docker on Ubuntu 22.04

**1. Volume permissions with Bitnami images**

Bitnami runs containers as non-root (UID 1001). If you pre-create host directories and mount them, you'll hit `Permission denied` errors on the Moodle data directory. The fix is to either let Docker manage volumes (as in the compose file above) or manually `chown -R 1001:1001` the host directories before mounting.

**2. The `MOODLE_CACHE_DRIVER=redis` variable alone is not enough**

Setting the environment variable tells Moodle to use Redis for the file cache. But Moodle's MUC (Moodle Universal Cache) still defaults to the database for the Application and Session caches. You must log into **Site Admin 鈫?Plugins 鈫?Caching 鈫?Configuration** and manually switch the store mappings to Redis after first boot.

**3. `client_max_body_size` in Nginx vs. PHP's `upload_max_filesize`**

We had instructors complaining that large video uploads were failing at exactly 2MB 鈥?the default PHP limit inside the Bitnami container. Even after setting `client_max_body_size 100M` in Nginx, the PHP limit inside the container is separate. To override it with Bitnami, set this environment variable on the Moodle service: `PHP_UPLOAD_MAX_FILESIZE=100M`.

**4. Moodle cron must run every minute**

Moodle relies heavily on its scheduled tasks (grading, messaging, notifications). Add this to the host's crontab:

```bash
crontab -e
# Add this line:
* * * * * docker exec moodle_app php /bitnami/moodle/admin/cli/cron.php >> /var/log/moodle_cron.log 2>&1
```

Skipping cron causes a cascade of issues 鈥?gradebook calculations fall behind, assignment notifications stop, and forum digests accumulate.

For integrating Single Sign-On into this Docker deployment, see our [SAML/SSO Authentication in Moodle guide](/blog/implementing-saml-sso-moodle/), which covers the `auth_saml2` plugin configuration that works identically inside the Docker environment.

Once your Moodle instance is stable and handling load, refer to our [Moodle Performance Tuning guide](/blog/moodle-performance-tuning-php-fpm-redis-opcache/) to configure PHP-FPM pool sizes and OPcache parameters appropriate for your user count.


