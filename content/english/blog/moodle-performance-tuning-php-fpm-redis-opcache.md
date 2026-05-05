---
title: "Moodle Performance Tuning: PHP-FPM Workers, Redis Cache, and OPcache"
date: 2026-05-05T10:00:00+08:00
image: "images/blog/blog-post-2.jpg"
author: "EdTech Architect"
type: "post"
categories: ["Infrastructure & Cloud", "Dev Log"]
tags: ["Moodle", "PHP-FPM", "Redis", "OPcache", "Performance Tuning"]
description: "Production-proven Moodle performance tuning guide covering PHP-FPM worker pool sizing, Redis session and MUC cache configuration, and OPcache settings. Includes real config snippets and benchmarks from a 2,000-student deployment."
---

The semester hadn't even started and I was already staring at a Moodle dashboard showing 98% CPU utilization. It was the Friday before the Fall semester at Global Tech University—students were logging in to check their course enrollments—and our Moodle instance was already on its knees with just a few hundred concurrent users. After four hours of emergency investigation, I realized the platform had been running on pure default settings for three years. Nobody had ever tuned it.

I rebuilt the entire performance stack from scratch over that weekend. What follows is every configuration change that actually moved the needle, along with the ones that sounded smart but did nothing.

<!-- ADSENSE_INSERT_HERE -->

## Why Moodle Degrades Under Load: The Three Bottlenecks

Before throwing hardware at the problem, you need to understand where Moodle actually spends its time. In every high-load scenario I've diagnosed, the bottleneck is always one of three things:

1. **PHP-FPM worker exhaustion** — new requests queue up while workers are stuck waiting on slow database queries.
2. **Lack of opcode caching** — PHP re-compiles the same files on every request.
3. **Session and MUC data hitting the database** — Moodle's internal caching architecture can serialize enormous amounts of data, and if it's all going to MariaDB, you will see locks.

Fixing these three in order is the only way to get a stable, scalable Moodle deployment.

## PHP-FPM Worker Pool Sizing for Moodle: The Formula That Works

The default `www.conf` in most PHP-FPM packages ships with `pm = dynamic` and only 5 max children. For a production Moodle serving 500+ users, this is catastrophically low.

Here is the configuration I use for a server with 16 GB RAM:

```ini
; /etc/php/8.1/fpm/pool.d/moodle.conf

[moodle]
user = www-data
group = www-data
listen = /run/php/php8.1-fpm-moodle.sock
listen.owner = www-data
listen.group = www-data

; Dynamic process management
pm = dynamic

; Sizing formula: (Total RAM - OS overhead) / per-process RAM
; Per Moodle PHP process ≈ 60-80MB in production
; (16384MB - 2048MB OS) / 70MB ≈ 205 max children
pm.max_children = 200
pm.start_servers = 20
pm.min_spare_servers = 10
pm.max_spare_servers = 40
pm.max_requests = 500

; Critical: prevent slow scripts from holding workers
request_terminate_timeout = 60s
```

**The sizing formula**: Divide your available RAM (after subtracting ~2GB for the OS and database) by the per-process footprint. Monitor the actual footprint with `ps aux | grep php-fpm | awk '{print $6}' | sort -rn | head` — in my experience, Moodle PHP processes run 60–90MB each.

## Moodle Redis Cache Configuration: MUC and Session Setup

This is the single highest-impact change you can make. By default, Moodle stores its Moodle Universal Cache (MUC) data in the database or on disk. Under exam conditions, this creates a massive write storm. Redirecting MUC to Redis collapses the database load dramatically.

### Installing the Redis PHP Extension

```bash
# Ubuntu/Debian
sudo apt install php-redis
sudo systemctl restart php8.1-fpm
```

### Configuring Moodle config.php for Redis Sessions

Add these lines to your `config.php` before the `require_once` at the bottom:

```php
// Redis session handler — replaces file-based sessions entirely
$CFG->session_handler_class = '\core\session\redis';
$CFG->session_redis_host = '127.0.0.1'; // or your Redis container IP
$CFG->session_redis_port = 6379;
$CFG->session_redis_database = 0;
$CFG->session_redis_auth = '';         // Set your Redis password here
$CFG->session_redis_prefix = 'mdl_';
$CFG->session_redis_acquire_lock_timeout = 120;
$CFG->session_redis_lock_expire = 7200;
```

### Configuring MUC Stores via the Admin Interface

After enabling Redis in `config.php`, navigate to **Site Administration → Plugins → Caching → Configuration** and set the Application and Session caches to use your Redis store. The "Application" cache store handles the most frequently accessed data (course structures, user preferences, theme data).

## OPcache Settings That Actually Improve Moodle Response Time

PHP's OPcache stores compiled bytecode in shared memory, eliminating the parsing step on every request. The defaults are too conservative for a Moodle codebase that contains thousands of PHP files.

```ini
; /etc/php/8.1/fpm/conf.d/10-opcache.ini

opcache.enable=1
opcache.enable_cli=0
opcache.memory_consumption=256      ; MB — Moodle's codebase is large
opcache.interned_strings_buffer=32
opcache.max_accelerated_files=20000 ; Moodle has ~15k PHP files
opcache.revalidate_freq=60          ; Check for file changes every 60s
opcache.validate_timestamps=1       ; Keep ON in development, OFF in production
opcache.save_comments=1             ; Required by some Moodle plugins
opcache.fast_shutdown=1
```

The critical setting is `max_accelerated_files`. Run `find /var/www/moodle -name "*.php" | wc -l` to count your actual PHP files. If your count exceeds `max_accelerated_files`, OPcache silently stops caching the overflow files—a very hard bug to diagnose.

## Moodle Database Connection Pool Tuning for MariaDB

PHP-FPM workers don't maintain persistent database connections by default. Under high concurrency, the connect/disconnect overhead becomes measurable. In `config.php`:

```php
$CFG->dboptions = array(
    'dbpersist' => true,     // Persistent connections — use carefully
    'dbsocket'  => '',
    'dbport'    => '3306',
    'dbhandlesoptions' => false,
    'dbcollation' => 'utf8mb4_unicode_ci',
);
```

Set MariaDB's `max_connections` in `/etc/mysql/mariadb.conf.d/50-server.cnf`:

```ini
max_connections = 300
innodb_buffer_pool_size = 4G  ; ~50-70% of available RAM
innodb_log_file_size = 512M
query_cache_type = 0          ; Disable query cache — it's a bottleneck in Moodle
```

## The "Gotchas" I Hit in Production

**1. Redis key eviction under memory pressure**

We ran Redis without a `maxmemory` policy set and found that under a large examination session, Redis started evicting Moodle session keys using the default LRU policy. Students started getting logged out mid-exam. The fix: set `maxmemory-policy noeviction` for the session database and use a separate Redis database for MUC with an appropriate LRU policy.

**2. OPcache `validate_timestamps=0` breaks plugin updates**

I disabled timestamp validation in production for the performance boost, then deployed a Moodle plugin update and spent 45 minutes debugging why changes weren't reflected. Always run `php -r "opcache_reset();"` or restart PHP-FPM after any code deployment when `validate_timestamps` is off.

**3. PHP-FPM socket vs. TCP**

Using a Unix socket (`/run/php/php8.1-fpm-moodle.sock`) instead of TCP (`127.0.0.1:9000`) reduced Nginx→PHP latency by about 15% in our environment. This matters at high concurrency where every millisecond of connection overhead multiplies.

## Benchmark Results: Before and After

After applying all of the above to our 16-core, 32GB server:

| Metric | Before | After |
|--------|--------|-------|
| Concurrent users (stable) | ~200 | ~1,800 |
| Average page response time | 2.8s | 0.4s |
| DB queries per page (course view) | 180 | 22 |
| CPU at 500 concurrent users | 95% | 28% |

The database query reduction came almost entirely from enabling MUC with Redis — Moodle's caching layer is extremely effective once properly configured.

For monitoring this stack in production, see our [Prometheus and Grafana LMS Performance Monitoring guide](/blog/prometheus-grafana-lms-monitoring/) which covers setting up real-time alerting for PHP-FPM worker saturation and Redis memory usage.

If you're running this Moodle stack in Docker, our [Self-Hosting Educational Tools with Docker guide](/blog/self-hosting-educational-tools-docker-homelab/) covers how to properly configure Redis and PHP-FPM resource limits within a container environment.
