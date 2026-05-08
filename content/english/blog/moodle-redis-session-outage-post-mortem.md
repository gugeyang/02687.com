---
title: "How a Missing Redis Policy Took Down Moodle During Final Exams: A Post-Mortem"
date: 2026-05-14T10:00:00+08:00
image: "images/blog/blog-post-6.jpg"
author: "Alex Chen"
type: "post"
categories: ["Dev Log", "Infrastructure and Cloud"]
tags: ["Moodle", "Redis", "Post-Mortem", "Incident Report", "Session Management"]
description: "A production post-mortem of a Moodle outage during final exams caused by a Redis memory eviction misconfiguration. Covers the failure timeline, the wrong diagnosis I chased first, and the exact fix that prevented a recurrence."
---

I should have caught this in staging. I didn't. Here's what happened.

## The Setup

This was a 4,200-student deployment. Moodle 4.1, running in Docker Compose on a dedicated bare-metal server. Redis handling both user sessions and MUC (Moodle Universal Cache). The configuration had been running stably for about five months before final exam season hit.

The Redis instance had 4GB allocated. The server had 32GB total. Seemed comfortable.

## The Timeline

**09:14** — Final exams begin for three large lecture courses, roughly 800 students starting simultaneously. Normal for this institution.

**09:31** — First support ticket: student reports being "kicked back to login screen mid-exam." Assigned to the helpdesk queue. Assumed it was a browser issue.

**09:47** — Helpdesk escalates. Now 40+ students reporting the same thing. I log into the Moodle admin panel. The dashboard loads. Everything looks normal. No PHP errors. No database connection failures.

**09:52** — I check `docker logs moodle_app`. Nothing obvious. I check MariaDB slow query log. A few queries above 2 seconds, but nothing catastrophic.

**09:58** — A student's session expires while I'm watching the logs. I can see Moodle writing a log entry: `Session not found for user X`. But the session *was* active — the student had been mid-exam for 45 minutes.

**10:03** — I finally run `redis-cli info stats`. And there it is:

```
evicted_keys:14839
```

Fourteen thousand keys evicted since Redis started. The session keys were gone. Redis had been silently discarding them for the past 30 minutes to make room for new cache entries, because I had set `maxmemory 4gb` without specifying a `maxmemory-policy`.

The default policy in this Redis version was `noeviction` — except I had a `redis.conf` entry from a previous test that had set it to `allkeys-lru`. Which means Redis was evicting the least-recently-used keys across all keyspaces. Sessions and cache entries were sharing the same pool. Exam sessions were being evicted to make room for course structure cache updates.

## The Wrong Diagnosis I Chased First

My first instinct was that this was a Moodle session lock timeout problem. Moodle's Redis session handler uses a distributed lock — if a user has two browser tabs open, the second tab waits for the first to release the session lock. Under exam conditions with many concurrent submissions, I assumed locks were expiring and dropping sessions.

I spent 20 minutes adjusting `session_redis_lock_expire` and `session_redis_acquire_lock_timeout`. This fixed nothing and cost me time I didn't have.

The actual problem was upstream of Moodle entirely. Moodle was behaving correctly — it tried to read a session key, the key didn't exist (because Redis had evicted it), so it treated the user as logged out. Moodle had no way to distinguish "session expired normally" from "Redis just deleted your session to free up memory."

## The Fix

**Immediate (during the incident):**

```bash
redis-cli config set maxmemory-policy noeviction
```

This stopped the eviction immediately. Students who were still mid-exam (hadn't been logged out yet) were stabilized. Students who had already been kicked out had to re-authenticate and lost their in-progress answers — we gave them full time extensions manually.

**Permanent fix — separate Redis instances:**

```yaml
# docker-compose.yml (revised)

redis-sessions:
  image: redis:7-alpine
  command: >
    redis-server
    --maxmemory 2gb
    --maxmemory-policy noeviction
    --save ""
    --appendonly no
  volumes:
    - redis_sessions_data:/data
  networks:
    - moodle_internal
  restart: unless-stopped

redis-cache:
  image: redis:7-alpine
  command: >
    redis-server
    --maxmemory 2gb
    --maxmemory-policy allkeys-lru
    --save ""
    --appendonly no
  networks:
    - moodle_internal
  restart: unless-stopped
```

Session Redis: `noeviction`. If it fills up, Redis returns an error rather than silently deleting a student's exam session. You want to know about this problem, not have it silently swallowed.

Cache Redis: `allkeys-lru`. Eviction is acceptable here — Moodle will just regenerate cache entries on the next request. A cache miss is a performance hit, not a data loss event.

**Moodle config.php changes:**

```php
// Session storage → dedicated Redis instance
$CFG->session_handler_class = '\core\session\redis';
$CFG->session_redis_host = 'redis-sessions';
$CFG->session_redis_port = 6379;
$CFG->session_redis_prefix = 'mdl_sess_';

// MUC cache → separate Redis instance (configured via Admin UI)
// Site Admin → Plugins → Caching → Configuration → Add Redis store
// Host: redis-cache, Port: 6379
```

## What I Added to Monitoring After This

The `evicted_keys` counter is now in my Prometheus scrape config, with an alert that fires if it increases by more than 100 in a 5-minute window:

```yaml
# prometheus/alerts.yml
- alert: RedisSessionEviction
  expr: increase(redis_evicted_keys_total{instance="redis-sessions:9121"}[5m]) > 100
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Redis session evictions detected — user sessions at risk"
```

This would have caught the problem 20 minutes before I did, during a time when we could have done something without impacting live exams.

## What I'd Do Differently

Run a load test before exam season. Not a load test for performance — a load test for memory behavior. Simulate 800 concurrent active sessions and watch `redis-cli info memory` for 30 minutes. If you see `mem_fragmentation_ratio` climbing above 1.5 or `evicted_keys` ticking up at all, you have a configuration problem that will surface in production.

I had load tested for page response time. I had not tested for memory management under sustained session load. Those are different things.

For the monitoring setup to catch these Redis indicators before they become an outage, see our [Prometheus and Grafana LMS Monitoring guide](/blog/prometheus-grafana-lms-monitoring/).
