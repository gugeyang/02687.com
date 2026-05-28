---
title: "Moodle MariaDB Performance Tuning for 5,000 Concurrent Users"
date: 2026-05-28T23:08:41+08:00
image: "images/blog/blog-post-5.jpg"
author: "Alex Chen"
type: "post"
categories: ["Data and AI"]
tags: ["Moodle", "MariaDB", "Performance"]
description: "Unlock Moodle MariaDB tuning secrets for 5,000 concurrent users. I share my hard-won lessons, specific configurations, and fixes for real-world database performance bottlenecks."
---

I still remember the dread, clear as day. It was the first day of an online exam period for a university client in Southeast Asia. We had carefully planned for 2,000 concurrent Moodle users, but an unexpected surge pushed us past 4,500. Suddenly, Moodle pages, which typically loaded in under 500ms, were taking 10-15 seconds. The MariaDB server, a beefy VM with 64GB RAM and NVMe storage, was thrashing its CPU at 100% and showing massive disk I/O spikes, even though the Moodle application servers were barely breaking a sweat. It was a classic case of the database being the single point of failure under peak load, and I spent the next 72 hours, fueled by caffeine, digging deep into MariaDB's internals to pull us back from the brink.

This wasn't just about tweaking a few lines; it was about fundamentally understanding how Moodle interacts with MariaDB at scale. After deploying Moodle, Canvas, and Open edX instances that serve hundreds of thousands of students across the Asia-Pacific region, I've learned that getting MariaDB right for Moodle isn't optional; it's existential. My goal here is to share exactly how I tune MariaDB for high-concurrency Moodle environments, specifically targeting the challenges of 5,000 simultaneous active users.

### Diagnosing the MariaDB Bottleneck: My First 24 Hours of Panic

When that Moodle instance started grinding to a halt, my first instinct was to confirm the bottleneck. `htop` on the MariaDB server showed `mysqld` consuming all available CPU. `dstat` revealed an insane number of disk writes and reads, indicating the server was constantly swapping data between RAM and disk. The critical piece of evidence came from `mytop` and `SHOW PROCESSLIST`: numerous queries were stuck in `Sending data` or `locked` states, with many appearing to be simple reads from `mdl_logstore_standard_log` and `mdl_user` tables, but accumulating into a massive traffic jam.

I immediately enabled the `slow_query_log` (temporarily with `SET GLOBAL slow_query_log = 'ON'; SET GLOBAL long_query_time = 1;`), and within minutes, I had a treasure trove of problematic queries. Many lacked proper indexing or were performing full table scans on large tables. This confirmed it: the database itself was struggling to serve Moodle's diverse, often chatty, query patterns under heavy load. This initial diagnosis, specifically seeing the `Sending data` state for long periods for non-obvious queries, was the "aha!" moment that led me down the rabbit hole of index optimization and buffer pool sizing.

### Optimizing MariaDB Configuration Parameters for High Concurrency

MariaDB's `my.cnf` configuration is where the real magic happens. For Moodle, especially with 5,000 concurrent users, it's all about memory allocation for InnoDB and efficient connection handling. This is my go-to baseline for a dedicated MariaDB server with 64GB of RAM and NVMe SSDs:

```ini
# /etc/mysql/my.cnf or /etc/my.cnf

[mysqld]
# Basic server settings
port = 3306
bind-address = 0.0.0.0
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
skip-name-resolve
max_connections = 1200 # Moodle's dbconnectionlimit needs headroom
max_user_connections = 0 # No limit per user
wait_timeout = 600
interactive_timeout = 600
tmp_table_size = 256M # For temporary tables during complex queries
max_heap_table_size = 256M # Ensure in-memory temporary tables don't spill to disk

# Logging for diagnostics
log_error = /var/log/mysql/error.log
slow_query_log = 1
slow_query_log_file = /var/log/mysql/mariadb-slow.log
long_query_time = 1 # Log queries taking longer than 1 second
log_queries_not_using_indexes = 1 # Critical for finding optimization opportunities

# InnoDB Specific Settings (CRITICAL for Moodle performance)
innodb_buffer_pool_size = 48G # Approximately 75% of 64GB RAM for Moodle's working set
innodb_buffer_pool_instances = 8 # Multiple instances for better concurrency
innodb_file_per_table = 1 # Recommended for Moodle for better space management
innodb_flush_log_at_trx_commit = 2 # Balance durability (1) with performance (0). 2 is generally safe and fast for Moodle.
innodb_log_file_size = 1G # Larger log files reduce flushing frequency, usually 2 files.
innodb_log_files_in_group = 2
innodb_io_capacity = 2000 # Adjust based on your SSD IOPS (NVMe can handle high values)
innodb_io_capacity_max = 4000
innodb_flush_method = O_DIRECT # Bypasses OS cache, direct writes
innodb_lru_scan_depth = 2000 # Keep the LRU list well-maintained
innodb_max_dirty_pages_pct = 75 # Max percentage of dirty pages in buffer pool

# Threading and Caching
thread_cache_size = 128 # Cache threads for reuse
query_cache_size = 0 # DEPRECATED: Do NOT use the query cache for high concurrency. It causes mutex contention.
query_cache_type = 0 # Ensure it's disabled.

# MyISAM specific (Moodle mostly uses InnoDB, but keep minimal)
key_buffer_size = 32M

[client]
port = 3306
socket = /var/run/mysqld/mysqld.sock
```

The `innodb_buffer_pool_size` is the single most impactful setting. For a dedicated database server, I always allocate 70-80% of total physical RAM to it. For 64GB RAM, 48GB-52GB is a sweet spot. Anything less, and your database will be constantly hitting the disk, especially under 5,000 concurrent user load. I've spent eight hours debugging a Moodle deployment where this was set to a paltry 8GB on a 32GB machine, resulting in page loads north of 15 seconds.

One thing I truly wish someone had told me before I started my journey in EdTech infrastructure was to *never, ever* enable the `query_cache` for a high-concurrency application like Moodle. While it seems intuitively good, its global mutex becomes a severe contention point under thousands of concurrent queries, often slowing down the database rather than speeding it up. Disable it completely; Moodle's internal caching and your well-tuned InnoDB buffer pool will handle it better.

### Moodle Schema Deep Dive: Indexing and Query Optimization

Even with a perfectly tuned `my.cnf`, a poorly indexed Moodle database will choke. Moodle's schema can be complex, and certain tables receive heavy write and read traffic.

1.  **`mdl_logstore_standard_log`**: This table, especially on busy sites, can grow to hundreds of gigabytes rapidly. Ensure it's using InnoDB, and regularly review its indexes. I often find that custom reports or plugins introduce queries that hit this table without optimal WHERE clauses. If you're building a [Student Performance Dashboard with Grafana and Moodle Data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/), you *must* ensure your queries are indexed or you'll bring your production database to its knees.
2.  **`mdl_sessions`**: With 5,000 concurrent users, this table sees constant reads and writes. Ensure the `sesskey` and `userid` columns are properly indexed. Better yet, externalize Moodle sessions to Redis or Memcached to significantly reduce database load.
3.  **Custom Plugin Queries**: This is where much of my debugging time goes. A poorly written custom block or activity module can execute inefficient queries. I always advocate for `EXPLAIN` to be run against any suspect query identified by the `slow_query_log`. Look for `Using filesort` or `Using temporary` results, which indicate suboptimal query plans. Adding compound indexes (e.g., `ALTER TABLE mdl_tablename ADD INDEX idx_name (column1, column2);`) based on your `WHERE` and `ORDER BY` clauses can yield dramatic improvements, sometimes reducing query times from seconds to milliseconds.

### Hardware and OS Considerations for Moodle Databases

No amount of tuning will fix fundamentally inadequate hardware. For a Moodle instance serving 5,000 concurrent users, I demand the following minimums for the database server:

*   **RAM**: At least 64GB, preferably 96GB or 128GB. The more you can fit into `innodb_buffer_pool_size`, the less MariaDB has to hit the disk.
*   **Storage**: NVMe SSDs, in a RAID 1 or RAID 10 configuration for redundancy and performance. Spinning disks simply won't cut it for the random I/O patterns Moodle generates under heavy load. I've seen a Moodle site struggle for years on SATA SSDs until a migration to NVMe cut database I/O latency by 80%.
*   **CPU**: 8-16 fast cores. While MariaDB is often I/O and RAM bound, complex queries and high connection counts will still demand significant CPU.

On the OS front (assuming Linux, typically Ubuntu or RHEL-based distributions), two settings are crucial:

*   **`vm.swappiness`**: Set this to `1` or `0` (for RHEL/CentOS) in `/etc/sysctl.conf`. This tells the kernel to avoid swapping memory to disk unless absolutely necessary. `vm.swappiness=1` is my standard for database servers:
    ```bash
    echo "vm.swappiness=1" >> /etc/sysctl.conf
    sysctl -p
    ```
    Swapping on a database server is a performance killer.
*   **`dirty_ratio` and `dirty_background_ratio`**: These control how much dirty data the kernel holds in memory before writing it to disk. For databases with their own caching (`innodb_flush_method=O_DIRECT`), tuning these can prevent I/O spikes. I generally use lower values like `10` and `5` respectively for `dirty_background_ratio` and `dirty_ratio` to ensure data gets flushed more regularly without huge bursts.

### Gotchas: Real-World Problems and My Hard-Won Fixes

I've stumbled into these pitfalls more times than I care to admit. Learn from my pain!

1.  **The "Too Many Connections" Error**: You've set `max_connections` to 1000 in `my.cnf`, but Moodle's `dbconnectionlimit` in `config.php` defaults to a much lower value (e.g., 175). Moodle's application servers will hit *their* internal limit before MariaDB does, leading to a cascade of errors. **Fix:** First, increase `max_connections` in `my.cnf` (e.g., 1200 for 5,000 users). Second, and crucially, adjust `$CFG->dbconnectionlimit` in Moodle's `config.php` to a value like `200` to `400` per application server, depending on your PHP-FPM configuration and server capacity. Each PHP-FPM worker uses a database connection.
2.  **Phantom Slowdowns After MariaDB Restart**: You restart MariaDB, and for an hour or two, performance is terrible, then slowly improves. **Fix:** Your `innodb_buffer_pool_size` is large, and it takes time to warm up. Implement `innodb_buffer_pool_dump_at_shutdown` and `innodb_buffer_pool_load_at_startup` (enabled by default in recent MariaDB versions, but verify) to save the buffer pool state on shutdown and restore it on startup. This drastically reduces the warmup time.
3.  **`mdl_events_queue` Table Bloat**: On very busy Moodle sites, the `mdl_events_queue` table can swell massively, especially if event processing is slow or blocked. This can lead to slow Moodle cron runs and impact overall performance. **Fix:** Regularly monitor the size of this table. Ensure your Moodle cron job is running efficiently and not getting stuck. Consider enabling Moodle's asynchronous event processing (via `cli/events.php`) and offloading it to a separate worker or using a dedicated `queue` system if the problem persists. For extreme cases, manually clearing old processed events can provide temporary relief, but find the root cause. This often ties into background tasks, which might also be bottlenecked if your Moodle setup involves complex external integrations for which I often use custom Python scripts, similar to how I approach [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/).

### Trade-offs and My Recommendations

When it comes to scaling Moodle with MariaDB, there are clear choices I recommend:

*   **Prioritize Vertical Scaling First**: Before you even think about complex replication setups, invest in a single, powerful MariaDB server. Max out RAM and get the fastest NVMe storage you can afford. For 5,000 concurrent users, a single instance with 96GB+ RAM and multiple NVMe drives is often more performant and easier to manage than two smaller servers in a replication scheme. Moodle is write-heavy, limiting the benefit of read replicas for its core operations.
*   **Disable MariaDB's Query Cache**: I'm taking a firm stance here. While it might seem beneficial for read-heavy applications, Moodle's dynamic nature and high concurrency make it a bottleneck. Disable it. Rely on Moodle's internal caching layers (Memcached or Redis) for object and data caching instead.
*   **Proactive Monitoring is Non-Negotiable**: Don't wait for a crisis. Implement monitoring with tools like Prometheus and Grafana (or Percona Monitoring and Management - PMM) to track key metrics like `innodb_buffer_pool_reads`, `queries/second`, `connections_current`, and disk I/O. Set alerts for thresholds. I've seen too many universities only react when students complain. Early detection saves weeks of stress and prevents service disruption. When integrating Moodle with other campus services, like [Building a Campus-Wide Single Sign-On (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/), a holistic monitoring approach becomes even more critical to pinpoint issues across the entire stack.

Tuning MariaDB for Moodle at scale is an ongoing process, not a one-time fix. It requires vigilance, deep technical understanding, and a willingness to dive into the logs when things go south. But with the right approach, you can build a Moodle infrastructure that confidently handles thousands of concurrent users, delivering a seamless learning experience.