---
title: "Moodle Performance Tuning: PHP-FPM Workers, Redis Cache, and OPcache"
date: 2026-05-05T10:00:00+08:00
image: "images/blog/blog-post-2.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud", "Dev Log"]
tags: ["Moodle", "PHP-FPM", "Redis", "OPcache", "Performance Tuning"]
description: "Production-proven Moodle performance tuning guide covering PHP-FPM worker pool sizing, Redis session and MUC cache configuration, and OPcache settings. Includes real config snippets and benchmarks from a 2,000-student deployment."
---

The semester hadn't even started and I was already staring at a Moodle dashboard showing 98% CPU utilization. It was the Friday before the Fall semester at Global Tech University鈥攕tudents were logging in to check their course enrollments鈥攁nd our Moodle instance was already on its knees with just a few hundred concurrent users. After four hours of emergency investigation, I realized the platform had been running on pure default settings for three years. Nobody had ever tuned it.

I rebuilt the entire performance stack from scratch over that weekend. What follows is every configuration change that actually moved the needle, along with the ones that sounded smart but did nothing.


## Why Moodle Degrades Under Load: The Three Bottlenecks

Before throwing hardware at the problem, you need to understand where Moodle actually spends its time. In every high-load scenario I've diagnosed, the bottleneck is always one of three things:

1. **PHP-FPM worker exhaustion** 鈥?new requests queue up while workers are stuck waiting on slow database queries.
2. **Lack of opcode caching** 鈥?PHP re-compiles the same files on every request.
3. **Session and MUC data hitting the database** 鈥?Moodle's internal caching architecture can serialize enormous amounts of data, and if it's all going to MariaDB, you will see locks.

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
; Per Moodle PHP process 鈮?60-80MB in production
; (16384MB - 2048MB OS) / 70MB 鈮?205 max children
pm.max_children = 200
pm.start_servers = 20
pm.min_spare_servers = 10
pm.max_spare_servers = 40
pm.max_requests = 500

; Critical: prevent slow scripts from holding workers
request_terminate_timeout = 60s
```

**The sizing formula**: Divide your available RAM (after subtracting ~2GB for the OS and database) by the per-process footprint. Monitor the actual footprint with `ps aux | grep php-fpm | awk '{print $6}' | sort -rn | head` 鈥?in my experience, Moodle PHP processes run 60鈥?0MB each.

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
// Redis session handler 鈥?replaces file-based sessions entirely
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

After enabling Redis in `config.php`, navigate to **Site Administration 鈫?Plugins 鈫?Caching 鈫?Configuration** and set the Application and Session caches to use your Redis store. The "Application" cache store handles the most frequently accessed data (course structures, user preferences, theme data).

## OPcache Settings That Actually Improve Moodle Response Time

PHP's OPcache stores compiled bytecode in shared memory, eliminating the parsing step on every request. The defaults are too conservative for a Moodle codebase that contains thousands of PHP files.

```ini
; /etc/php/8.1/fpm/conf.d/10-opcache.ini

opcache.enable=1
opcache.enable_cli=0
opcache.memory_consumption=256      ; MB 鈥?Moodle's codebase is large
opcache.interned_strings_buffer=32
opcache.max_accelerated_files=20000 ; Moodle has ~15k PHP files
opcache.revalidate_freq=60          ; Check for file changes every 60s
opcache.validate_timestamps=1       ; Keep ON in development, OFF in production
opcache.save_comments=1             ; Required by some Moodle plugins
opcache.fast_shutdown=1
```

The critical setting is `max_accelerated_files`. Run `find /var/www/moodle -name "*.php" | wc -l` to count your actual PHP files. If your count exceeds `max_accelerated_files`, OPcache silently stops caching the overflow files鈥攁 very hard bug to diagnose.

## Moodle Database Connection Pool Tuning for MariaDB

PHP-FPM workers don't maintain persistent database connections by default. Under high concurrency, the connect/disconnect overhead becomes measurable. In `config.php`:

```php
$CFG->dboptions = array(
    'dbpersist' => true,     // Persistent connections 鈥?use carefully
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
query_cache_type = 0          ; Disable query cache 鈥?it's a bottleneck in Moodle
```

## Things That Will Wreck You If You Skip Them

**1. Redis key eviction — the one that cost us a final exam period**

I burned four hours chasing what I thought was a Moodle session locking bug. Students were getting kicked out mid-exam, Moodle logs were clean, PHP error logs were clean. I adjusted `session_redis_lock_expire` and `session_redis_acquire_lock_timeout`. Nothing changed. I restarted PHP-FPM. Still happening.

Finally ran `redis-cli info stats` and saw `evicted_keys:14839`. Redis had been silently discarding user session keys to make room for MUC cache entries because I had a `maxmemory-policy allkeys-lru` sitting in a `redis.conf` I'd forgotten about from a previous test. Moodle had no idea — it just saw a missing session key and treated the student as logged out.

The fix: run sessions and MUC cache on **separate Redis instances** with different eviction policies. Sessions get `noeviction` (return an error if memory is full — you want to know about this). MUC gets `allkeys-lru` (evict freely, Moodle regenerates cache on next request). Full post-mortem with the complete failure timeline in our [Redis Session Outage Post-Mortem](/blog/moodle-redis-session-outage-post-mortem/).

**2. OPcache `validate_timestamps=0` is a trap you will fall into exactly once**

I turned off timestamp validation for a performance boost, then deployed a plugin update the following week. The plugin appeared in the Moodle admin panel but did nothing — OPcache was serving bytecode compiled before the update. I wasted 45 minutes checking whether the plugin had actually installed before realizing the issue was upstream entirely. After any code deployment with this flag off: run `php -r "opcache_reset();"` or restart PHP-FPM. I now have this in my deployment checklist, bolded and underlined.

**3. PHP-FPM socket vs. TCP — smaller than you think until it isn't**

Switching from TCP (`127.0.0.1:9000`) to a Unix socket (`/run/php/php8.1-fpm-moodle.sock`) shaved about 15% off Nginx→PHP connection latency in our environment. Under normal load this is invisible. At 800 concurrent users, those microseconds accumulate in ways that show up in response time percentiles. Worth doing — but verify the socket path matches in both `nginx.conf` and `www.conf` before you deploy, or you'll get a very unhelpful 502.

## Benchmark Results: Before and After

After applying all of the above to our 16-core, 32GB server:

| Metric | Before | After |
|--------|--------|-------|
| Concurrent users (stable) | ~200 | ~1,800 |
| Average page response time | 2.8s | 0.4s |
| DB queries per page (course view) | 180 | 22 |
| CPU at 500 concurrent users | 95% | 28% |

The database query reduction came almost entirely from enabling MUC with Redis 鈥?Moodle's caching layer is extremely effective once properly configured.

For monitoring this stack in production, see our [Prometheus and Grafana LMS Performance Monitoring guide](/blog/prometheus-grafana-lms-monitoring/) which covers setting up real-time alerting for PHP-FPM worker saturation and Redis memory usage.

If you're running this Moodle stack in Docker, our [Self-Hosting Educational Tools with Docker guide](/blog/self-hosting-educational-tools-docker-homelab/) covers how to properly configure Redis and PHP-FPM resource limits within a container environment.


