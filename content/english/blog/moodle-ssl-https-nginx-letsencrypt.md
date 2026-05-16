---
title: "Securing Moodle with HTTPS: Nginx Reverse Proxy and Let's Encrypt SSL Setup"
date: 2026-05-16T10:00:00+08:00
image: "images/blog/blog-post-2.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud"]
tags: ["Moodle", "Nginx", "SSL", "Let's Encrypt", "HTTPS", "Docker"]
description: "Step-by-step guide to securing Moodle with HTTPS using Nginx as a reverse proxy and Let's Encrypt SSL via Certbot. Covers Docker Compose integration, automatic certificate renewal, and the config mistakes that silently break Moodle sessions after enabling SSL."
---

Running Moodle on plain HTTP in production is not just a security problem — it actively breaks functionality. Moodle's session cookies default to non-`Secure` mode, which means modern browsers will refuse to send them over mixed HTTP/HTTPS connections. The result is a login loop that confuses students and generates a flood of helpdesk tickets, all traceable back to a missing `$CFG->sslproxy` line.

This guide documents the exact Nginx reverse proxy and Let's Encrypt configuration I use in production Docker deployments, including the two `config.php` settings that most tutorials omit and that cause 80% of post-SSL-migration issues.

## Why Moodle Needs a Reverse Proxy for HTTPS (Not Just Certbot Standalone)

Let's Encrypt can issue certificates directly against your web server, but for a containerized Moodle deployment, running Nginx as an SSL-terminating reverse proxy is the correct architecture. It gives you SSL termination, HTTP/2 support, security header injection, and large file upload handling — all in one layer that sits in front of the Moodle PHP container.

The Moodle container itself runs plain HTTP internally on a private Docker network. Nginx accepts HTTPS from the outside world, strips SSL, and forwards plain HTTP to Moodle. This separation also makes certificate renewal non-disruptive: Certbot reloads Nginx without ever touching the Moodle application process.

## Nginx Configuration for Moodle SSL Reverse Proxy

Save this as `/etc/nginx/sites-available/moodle` (or as a config file inside your Docker Compose Nginx container):

```nginx
# /etc/nginx/sites-available/moodle

server {
    listen 80;
    server_name moodle.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name moodle.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/moodle.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/moodle.yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Moodle course files can be large
    client_max_body_size 512M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
        proxy_connect_timeout 30s;
        proxy_buffering off;
    }

    # ACME challenge path for Certbot renewal
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
}
```

The `X-Forwarded-Proto https` header is what Moodle reads to determine whether the incoming connection is over SSL. This header is the bridge between Nginx's HTTPS termination and Moodle's internal URL generation. Without it, Moodle generates `http://` links for embedded resources even after you've "enabled SSL" — causing mixed content warnings on every page.

## Moodle config.php: The Two Settings Most Guides Skip

Nginx handling SSL is only half the job. Moodle needs to be explicitly told it's running behind an SSL-terminating proxy. Add these three lines to `config.php`:

```php
<?php
// config.php — mandatory settings for HTTPS behind Nginx reverse proxy

$CFG->wwwroot   = 'https://moodle.yourdomain.com';  // must be https://
$CFG->sslproxy  = true;   // tells Moodle to trust X-Forwarded-Proto header
$CFG->cookiesecure = true; // marks session cookies as Secure-only
```

**`$CFG->sslproxy = true`** is the setting responsible for 80% of post-migration issues I've debugged. Without it, Moodle's URL generation functions check `$_SERVER['HTTPS']`, which is empty when the request arrives at the PHP container over plain HTTP from Nginx. Setting `sslproxy` tells Moodle to trust the `X-Forwarded-Proto` header instead, so it correctly identifies the connection as HTTPS and generates correct URLs.

After changing `config.php`, always purge Moodle's caches:

```bash
docker exec -it moodle_app php admin/cli/purge_caches.php
```

Cached pages may still contain old `http://` URLs until the cache is cleared.

## Installing Let's Encrypt and Automating Moodle SSL Certificate Renewal

With Nginx configured and port 80 available, issue the initial certificate:

```bash
# Install Certbot with Nginx plugin
sudo apt install certbot python3-certbot-nginx -y

# Issue certificate (Certbot will auto-modify your Nginx config)
sudo certbot --nginx -d moodle.yourdomain.com

# Verify certificate details
sudo certbot certificates

# Test the auto-renewal process (dry run — no actual renewal)
sudo certbot renew --dry-run
```

Certbot installs a systemd timer that checks for renewal twice daily. Let's Encrypt certificates expire after 90 days; Certbot renews at 60 days. As an additional safeguard, I add an explicit weekly cron job:

```bash
# crontab -e — runs every Monday at 03:00 AM
0 3 * * 1 /usr/bin/certbot renew --quiet && /bin/systemctl reload nginx
```

This ensures that even if the systemd timer fails silently, the certificate renews on a weekly schedule. A certificate that expires during finals week is a career-limiting event.

## Docker Compose: Running Nginx and Certbot as Containers

For fully containerized deployments where Moodle runs in Docker Compose, add Nginx and Certbot as additional services:

```yaml
# docker-compose.yml — add these services alongside your Moodle container

nginx:
  image: nginx:alpine
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx/conf.d:/etc/nginx/conf.d:ro
    - ./certbot/www:/var/www/certbot:ro
    - ./certbot/conf:/etc/letsencrypt:ro
  depends_on:
    - moodle
  restart: unless-stopped

certbot:
  image: certbot/certbot
  volumes:
    - ./certbot/www:/var/www/certbot
    - ./certbot/conf:/etc/letsencrypt
  entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
  restart: unless-stopped
```

The Certbot container runs a renewal check every 12 hours in the background. This approach keeps the entire stack portable — cloning the repo and running `docker compose up` on a new server reproduces the full HTTPS environment without any host-level configuration.

## Gotchas: What Breaks After Enabling Moodle HTTPS

**1. Moodle generates mixed-content HTTP links after SSL is enabled.**

This is almost always a missing `$CFG->sslproxy = true`. Symptoms: the browser console shows `Mixed Content: The page was loaded over HTTPS, but requested an insecure resource`. Fix: add the setting and run `php admin/cli/purge_caches.php`. If it persists, check that your Nginx config is actually sending `X-Forwarded-Proto https` and not `X-Forwarded-Proto $scheme` (which would forward `http` if Nginx's upstream connection is HTTP).

**2. Certificate renewal fails because Nginx has a syntax error.**

Certbot renews the certificate files, then calls `nginx -s reload`. If the Nginx config has a syntax error introduced since the last reload (an edited site config, a missing semicolon), the reload fails silently — the renewed certificate files exist on disk but Nginx is still serving the old ones. The site appears to work until the old cert expires.

Fix: always validate your Nginx config before reloading: `nginx -t`. Set up monitoring on certificate expiry — blackbox_exporter with Prometheus can alert you when a certificate has fewer than 14 days remaining.

**3. Large file uploads time out at Nginx before reaching Moodle.**

Moodle course files, SCORM packages, and video content can exceed 100MB. Nginx's default `client_max_body_size` is 1MB, and `proxy_read_timeout` is 60 seconds. Both need to be increased for a Moodle deployment. The values in the config above (`512M` and `120s`) cover most institutional use cases, but if you're hosting large video libraries, increase them further.

## Architecture Trade-offs: Host Nginx vs Containerized Nginx

Running Nginx directly on the host is simpler to set up initially and gives more predictable behavior when debugging certificate issues. The downside is that it creates a dependency outside your Docker stack — if you provision a new server, you have to remember to configure host Nginx separately.

Running Nginx inside Docker Compose means the entire stack is reproducible from a single `docker compose up`. The trade-off is additional complexity in the Compose file and a dependency between the Nginx container startup order and Certbot having already issued a certificate.

For new deployments, I recommend the containerized approach. For existing setups where Nginx is already managing other sites on the host, keeping Nginx on the host and only containerizing Moodle is the lower-risk option.

For performance tuning after you have HTTPS running, our [Moodle Performance Tuning: PHP-FPM Workers, Redis Cache, and OPcache](/blog/moodle-performance-tuning-php-fpm-redis-opcache/) guide covers the next layer of production hardening. To monitor whether your SSL endpoint and Moodle application stay healthy over time, see our [Prometheus and Grafana LMS Monitoring](/blog/prometheus-grafana-lms-monitoring/) setup guide.
