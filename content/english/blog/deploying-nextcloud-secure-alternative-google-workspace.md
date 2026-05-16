---
title: "Deploying Nextcloud as a Self-Hosted Google Workspace Alternative for Universities"
date: "2024-05-14T10:00:00+08:00"
image: "images/blog/blog-post-5.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud"]
tags: ["Nextcloud", "Ceph", "S3", "Kubernetes", "Data Sovereignty", "Collabora Online"]
description: "Production architecture for deploying self-hosted Nextcloud to replace Google Workspace in education. Covers S3-compatible Ceph storage backend, Collabora Online document editing, LDAP provisioning, Redis tuning, and the gotchas we hit migrating 3,000 faculty and staff off Google Drive."
---

Google pulled the rug in 2022. The unlimited storage that universities had relied on for a decade suddenly came with quotas and a price tag. Our storage audit at Global Tech University showed 47TB across faculty accounts — at Google's per-user pricing, the annual bill would have been absurd. The provost's office wanted alternatives. We had six months.

We chose Nextcloud, not because it was the only option, but because it was the only self-hosted platform mature enough to handle collaborative editing, mobile sync, and federation with partner institutions without depending on a third-party SaaS vendor who might change terms again.

## Why Object Storage Beats NFS for Nextcloud at University Scale

Deploying Nextcloud for a family is trivially easy. Deploying it for 3,000 users who all sync their laptops at 8:55 AM on a Monday requires a fundamentally different storage strategy.

The default Nextcloud installation writes files to a local POSIX filesystem. In a multi-node setup, you'd typically share that filesystem over NFS. We tried this initially. NFS became the single point of contention — file locking storms during peak sync windows degraded the entire cluster. Response times climbed past 8 seconds for simple directory listings.

The fix was switching to S3-compatible object storage. We pointed Nextcloud at our existing Ceph cluster's RadosGW endpoint. The web nodes no longer needed a shared filesystem at all. File metadata stays in PostgreSQL; actual file bytes stream directly to Ceph via HTTP.

The critical `config.php` snippet — and this **must** be configured before running the Nextcloud installation wizard, not after:

```php
<?php
$CONFIG = array (
  'objectstore' => array(
    'class' => '\\OC\\Files\\ObjectStore\\S3',
    'arguments' => array(
      'bucket' => 'nextcloud-data-prod',
      'autocreate' => true,
      'key'    => 'YOUR_CEPH_ACCESS_KEY',
      'secret' => 'YOUR_CEPH_SECRET_KEY',
      'hostname' => 's3.internal.campus.edu',
      'port' => 443,
      'use_ssl' => true,
      'region' => 'us-east-1',
      'use_path_style' => true
    ),
  ),
);
```

One detail the documentation glosses over: `use_path_style` must be `true` for Ceph and MinIO. AWS-style virtual-hosted bucket URLs (`bucket.s3.region.amazonaws.com`) don't work with local S3-compatible stores. We burned half a day on mysterious `403 Forbidden` errors before figuring this out.

## Nextcloud Collabora Online Setup: Replacing Google Docs for Faculty

Telling faculty they're losing Google Docs without offering real-time collaborative editing is career suicide for an IT director. Collabora Online was the non-negotiable requirement.

We deployed Collabora as a separate Docker container behind its own Nginx virtual host, running on a dedicated 8-core VM. The reason for the dedicated VM: document rendering is CPU-intensive. Each open document spawns a LibreOffice process. During finals week, we had 120+ documents open simultaneously. Mixing Collabora and Nextcloud on the same node causes both to suffer.

The Collabora container config:

```yaml
collabora:
  image: collabora/code:24.04
  container_name: collabora_online
  environment:
    - aliasgroup1=https://cloud.campus.edu:443
    - username=admin
    - password=${COLLABORA_ADMIN_PASS}
    - extra_params=--o:ssl.enable=false --o:ssl.termination=true
  cap_add:
    - MKNOD
  ports:
    - "9980:9980"
  restart: unless-stopped
```

The `ssl.termination=true` flag tells Collabora that SSL is handled by the upstream reverse proxy, not by the container itself. Miss this, and you get a blank white screen when opening documents — no error message, just nothing.

## Nextcloud LDAP User Provisioning: Onboarding 3,000 Accounts Automatically

We were not going to create 3,000 accounts by hand. Nextcloud's LDAP/AD integration pulled users directly from our campus Active Directory. Faculty logged in with their existing campus credentials, and Nextcloud auto-provisioned their account on first login.

The tricky part was group mapping. We needed department-level shared folders — the Biology department shouldn't see Engineering's grant proposals. We mapped AD security groups to Nextcloud groups, then created group folders with the `groupfolders` app.

What caught us off guard: LDAP pagination. Our AD has over 15,000 objects. Nextcloud's default LDAP page size of 500 caused the initial sync to take 45 minutes and timeout repeatedly. Bumping `ldapPagingSize` to 1500 and setting the LDAP query filter to exclude disabled accounts (`!(userAccountControl:1.2.840.113556.1.4.803:=2)`) cut the sync to under 3 minutes.

For a deeper dive into campus identity federation patterns, our [Keycloak SSO Campus Deployment guide](/blog/building-campus-wide-sso-keycloak/) covers the broader authentication architecture that Nextcloud plugs into.

## Background Job Performance: Why AJAX Cron Destroys Nextcloud Under Load

Nextcloud offloads a surprising amount of work to background tasks — generating preview thumbnails, indexing files for full-text search, cleaning up expired shares, and processing activity notifications. The default "AJAX" mode triggers these tasks on every page load. On a 3,000-user deployment, this means random users experience 10+ second page loads because their request happened to trigger a batch of thumbnail generations.

Switch to system cron immediately. We run it via a Kubernetes CronJob that executes against a dedicated background worker pod:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nextcloud-cron
spec:
  schedule: "*/5 * * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: cron-worker
            image: registry.campus.edu/nextcloud-app:29
            command: ["/usr/local/bin/php"]
            args: ["-f", "/var/www/html/cron.php"]
            resources:
              limits:
                memory: "512Mi"
                cpu: "500m"
          restartPolicy: OnFailure
```

The `concurrencyPolicy: Forbid` line is important — it prevents overlapping cron runs when a previous job takes longer than 5 minutes, which happens during storage cleanup cycles.

## Gotchas We Hit Migrating from Google Workspace to Nextcloud

**1. Redis memory and file locking conflicts**

Nextcloud uses Redis for both transactional file locking (preventing two users from writing to the same file simultaneously) and general application caching. Under heavy load, cache entries can evict lock entries if you're running a single Redis instance with `allkeys-lru`. We split into two Redis instances — one for locking with `noeviction`, one for caching with `allkeys-lru`. Same pattern we documented in our [Moodle Redis session architecture](/blog/moodle-performance-tuning-php-fpm-redis-opcache/), and the reasoning is identical.

**2. Desktop client sync thrashing on large shared folders**

The `groupfolders` app doesn't interact well with the desktop sync client when a shared folder contains more than ~50,000 files. The sync client downloads the entire file listing on every sync cycle, even if nothing changed. This generated enough database queries to saturate our PostgreSQL connection pool during morning peak. The workaround: exclude group folders from desktop sync by default and provide WebDAV access for browsing them.

**3. PHP memory limits for preview generation**

The default PHP memory limit (128MB) is insufficient for generating previews of large TIFF files and high-resolution images common in architecture and art departments. We raised `memory_limit` to 512MB on the cron worker pods (not the web-facing pods — you don't want a single preview generation consuming web node resources).

**4. Federation polling hammers the database**

We federated with two partner universities running their own Nextcloud instances. The federation polling mechanism — checking remote servers for file updates every few minutes — generated a constant trickle of database writes that added up. We had to tune the polling interval and add dedicated PostgreSQL read replicas to absorb the load without impacting primary user operations.

## The Trade-offs: Nextcloud Self-Hosted vs Managed Google Workspace

Running Nextcloud at institutional scale is not free. Our infrastructure costs roughly $18,000/year (hardware amortization, power, a part-time sysadmin's attention). Google Workspace for Education Plus for 3,000 users would have been approximately $36,000/year at posted pricing — but that number only goes up, and you have zero leverage to negotiate when your data is already locked in.

The real value isn't the cost savings. It's the control. When the EU's data protection authority questioned where our research data was stored, we could point to a rack in our own datacenter. When a department needed a custom workflow app, we built a Nextcloud app — no vendor ticket, no feature request that disappears into a backlog.

For monitoring the infrastructure health of deployments like this — PostgreSQL query latency, Redis memory usage, PHP-FPM worker saturation — we rely on the same [Prometheus and Grafana monitoring stack](/blog/prometheus-grafana-lms-monitoring/) we use for our LMS infrastructure.

Self-hosting your institution's file platform is a serious commitment. But after two years running this stack, I would not go back to handing our data to a vendor whose pricing model we can't predict.
