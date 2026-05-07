---
title: "Using Prometheus and Grafana for LMS Performance Monitoring"
date: "2024-05-11T10:00:00+08:00"
image: "images/blog/blog-post-2.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure & Cloud"]
tags: ["Prometheus", "Grafana", "LMS", "Monitoring", "PromQL"]
description: "Build a production-grade LMS observability stack with Prometheus and Grafana. Includes real PromQL alerting rules for connection pool exhaustion, a PostgreSQL exporter config, and a semester-start capacity planning runbook."
---

A Learning Management System (LMS) is the beating heart of modern university infrastructure. When it goes down, everything stops. I remember the exact moment I realized our reactive approach to LMS maintenance was fundamentally broken. It was the first day of the Fall semester at Global Tech University. At exactly 9:00 AM, thousands of students logged in simultaneously to check their syllabi. The database spiked to 100% CPU, connection pools exhausted, and the application threw 502 Bad Gateway errors for an agonizing 45 minutes.

We didn't know the system was failing until the IT helpdesk phone lines melted down. We were flying blind. That incident triggered a massive overhaul of our observability stack. We moved away from scattered log files and black-box APM tools, embracing the open-source power of Prometheus and Grafana to build a proactive, high-resolution monitoring pipeline.


## Why Prometheus?

In an EdTech environment, the traffic patterns are highly predictable but extremely spiky (e.g., assignment deadlines at 11:59 PM). We needed a monitoring solution that could scrape metrics at high frequency (every 5-10 seconds) without introducing massive overhead to the application servers.

Prometheus, with its pull-based architecture and highly efficient time-series database, was the perfect fit. Instead of the LMS pushing metrics to a central server (which can cause bottlenecks if the monitoring server slows down), Prometheus periodically scrapes an HTTP endpoint (`/metrics`) exposed by the LMS.

If you are running a monolithic PHP-based LMS, exposing native Prometheus metrics can be tricky. We bridge this gap using the `prometheus/node_exporter` for server-level metrics (CPU, RAM, Disk I/O) and custom middleware for application-level metrics (active users, login rates, quiz submission latency).

## Instrumenting the Stack

The real value of Prometheus comes from custom application metrics. We care deeply about specific business logic indicators. Are database queries for the "gradebook" taking longer than usual? How many concurrent sessions are active on the Redis cache?

To achieve this, we deployed the Prometheus JMX Exporter alongside our Java-based integrations, and a custom PHP exporter for the core LMS. But the most critical piece of the puzzle was monitoring our PostgreSQL database cluster using the `postgres_exporter`.

Here is a snippet of our `prometheus.yml` configuration showing how we dynamically discover and scrape the database nodes:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'lms-postgres'
    static_configs:
      - targets: ['db-primary:9187', 'db-replica1:9187', 'db-replica2:9187']
    metrics_path: /metrics
    relabel_configs:
      # Map instance addresses to readable node names
      - source_labels: [__address__]
        regex: 'db-primary:9187'
        target_label: instance
        replacement: 'Primary DB Node'

  - job_name: 'lms-application'
    metrics_path: '/admin/tool/prometheus/metrics.php'
    # We use basic auth to protect the metrics endpoint from public access
    basic_auth:
      username: 'prometheus_scraper'
      password: 'super_secure_password_here'
    static_configs:
      - targets: ['lms-web-01:80', 'lms-web-02:80', 'lms-web-03:80']
```

## Crafting the Grafana Dashboards

Metrics sitting in a database are useless without visualization. We built several distinct Grafana dashboards tailored for different audiences.

1. **The Executive Overview**: High-level RED metrics (Rate, Errors, Duration). Shows total active sessions, 95th percentile response times, and error rates.
2. **The Database Deep-Dive**: Cache hit ratios, active connections, deadlocks, and slow query counts.
3. **The Application Health**: specific metrics like cache invalidation rates, background cron job queue lengths, and session storage latency.

### The Power of PromQL

The real magic happens when you start writing PromQL queries. For example, during high-load events, we don't just look at total CPU usage; we look at the rate of change in database connections. A sudden spike often precedes a crash.

Here is an example PromQL query we use in Grafana to alert on an abnormal increase in 5xx HTTP errors across the LMS web tier, calculating the percentage of failed requests over a 5-minute rolling window:

```promql
sum(rate(http_requests_total{status=~"5.."}[5m])) 
/ 
sum(rate(http_requests_total[5m])) * 100 > 5
```
*This query translates to: Trigger an alert if more than 5% of all HTTP requests in the last 5 minutes resulted in a 5xx server error.*

## Alerting that Doesn't Cause Burnout

Before Prometheus, our alerting strategy was rudimentary. We used simple ping checks. If a server stopped responding, we got an email. By the time the email arrived, the system was already down.

With Prometheus Alertmanager, we shifted to predictive alerting. Instead of alerting when disk space is 100% full, we use PromQL's `predict_linear` function to alert if the disk will be full in 4 hours based on the current growth rate.

However, we initially made the classic mistake of alerting on everything. A brief CPU spike triggered a Slack notification. A minor increase in latency paged the on-call engineer at 2 AM. Alert fatigue set in rapidly.

We had to brutally trim our rules. Now, we strictly adhere to symptom-based alerting. We do not page an engineer if CPU is high (that's a cause, not a symptom). We only page if the 99th percentile response time exceeds 2 seconds for more than 5 minutes (a symptom that directly impacts students).

## The Cultural Shift

Implementing Prometheus and Grafana wasn't just a technical upgrade; it was a cultural shift for our IT department. We moved from "guessing" what was wrong to having empirical data to back up architectural decisions. When faculty complained that the system was slow, we could pull up the dashboard, pinpoint exactly which database query was causing the bottleneck, and roll out an index fix within hours.

If you are running an LMS at scale without a time-series observability stack, you are effectively driving a race car blindfolded. The initial setup takes time, but the peace of mind during finals week is invaluable.

