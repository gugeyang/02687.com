---
title: "Load Balancing Moodle with HAProxy for High Availability"
date: 2026-06-03T11:33:29+08:00
image: "images/blog/blog-post-3.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud"]
tags: ["Moodle"]
description: "Achieve Moodle high availability with HAProxy: I share 9 years of deployment insights, a production-ready HAProxy config, and critical real-world Moodle HAProxy fixes to scale your LMS."
---

I still vividly recall the incident during the final exam period at a large Southeast Asian university. Our Moodle instance, normally a robust workhorse, suddenly ground to a halt. Apache logs were flooded, PHP-FPM processes were maxed out, and the single Moodle application server, which had been handling around 800 concurrent users adequately, simply buckled under a surge of 2,100 students all trying to access their exams simultaneously. Response times plummeted from a healthy 200ms to over 10 seconds, and eventually, the server became unresponsive. It was a complete outage, triggering panic across campus and forcing a scramble to extend exam windows. That day, it became unequivocally clear: a single point of failure in our critical EdTech infrastructure, especially Moodle, was no longer an option. This incident cemented my commitment to designing high availability into every LMS deployment I oversee.

## Architecting for Moodle High Availability: Why HAProxy is Non-Negotiable

When you're running a mission-critical platform like Moodle, especially for thousands of students across multiple time zones, you simply cannot afford downtime. Over my nine years deploying various LMS platforms like Moodle, Canvas, and Open edX in production, I've seen firsthand how a well-architected high availability (HA) setup can mean the difference between seamless learning and widespread disruption. For Moodle, which is predominantly a PHP application backed by a database, achieving HA means distributing traffic across multiple application servers and ensuring session persistence and data consistency.

I've experimented with Nginx's `upstream` module and even commercial load balancers, but time and again, I return to HAProxy. Why? Its exceptional performance, small memory footprint (typically under 256MB on a 4GB RAM VM, even with high traffic), and powerful feature set for TCP and HTTP load balancing make it the gold standard for applications like Moodle. HAProxy's ability to precisely manage sessions, perform sophisticated health checks, and dynamically reconfigure without downtime is unparalleled in the open-source world. It’s not just about distributing requests; it’s about intelligently routing them to maintain user context and ensure a consistent experience. This is especially crucial for interactive learning platforms where students might be mid-quiz or submitting assignments.

## Core HAProxy Configuration for Moodle Load Balancing

Setting up HAProxy for Moodle requires careful consideration of several factors: SSL termination, session persistence, and effective health checks. My typical setup involves two HAProxy instances in an active-passive or active-active configuration (using Keepalived for VIP failover) in front of multiple Moodle application servers. Below is a production-ready HAProxy configuration that I've refined over several deployments, designed to handle thousands of concurrent users while ensuring Moodle high availability.

```ini
# /etc/haproxy/haproxy.cfg - Production HAProxy configuration for Moodle
global
    log /dev/log    local0 notice
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin expose-fd listeners
    stats timeout 30s
    user haproxy
    group haproxy
    daemon
    # Set maximum number of concurrent connections (adjust based on your server capacity)
    maxconn 20000 
    # Enable a debug mode for HAProxy internal errors
    # debug
    # quiet

defaults
    log global
    mode http
    option httplog
    option dontlognull
    # Redirect HTTP to HTTPS immediately
    redirect scheme https if !{ ssl_fc }
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms
    # Retries upon server connection failure
    retries 3

frontend http_frontend
    bind *:80
    default_backend moodle_backend

frontend https_frontend
    bind *:443 ssl crt /etc/haproxy/certs/moodle.pem
    http-request set-header X-Forwarded-Proto https
    http-request set-header X-Forwarded-SSL on
    default_backend moodle_backend

backend moodle_backend
    balance roundrobin
    # Enable cookie-based session persistence for Moodle.
    # 'MoodleSession' is the default PHP session cookie name.
    # 'insert indirect nocache' ensures HAProxy manages the cookie without modifying app behavior directly,
    # and prevents caching issues.
    cookie MoodleSession insert indirect nocache
    
    # Define your Moodle application servers
    # 'check' enables health checks.
    # 'inter 2000ms' checks every 2 seconds.
    # 'rise 2' means 2 successful checks to mark as up.
    # 'fall 3' means 3 failed checks to mark as down.
    # 'backup' servers are only used when all primary servers are down.
    server moodle_app_1 192.168.1.101:80 check inter 2s rise 2 fall 3 cookie s1
    server moodle_app_2 192.168.1.102:80 check inter 2s rise 2 fall 3 cookie s2
    server moodle_app_3 192.168.1.103:80 check inter 2s rise 2 fall 3 cookie s3
    
    # Example backup server (optional, but highly recommended for disaster recovery)
    # server moodle_app_backup 192.168.1.104:80 check inter 2s rise 2 fall 3 backup cookie s_b

    # Moodle specific health check: ensure it returns 200 OK for the login page
    # This is more robust than just checking '/' which might return 200 even if DB is down.
    http-check expect string "Moodle"
    http-check send meth GET uri /login/index.php

    # Custom error page for when all servers are down
    errorfile 503 /etc/haproxy/errors/503.http
```
This configuration handles SSL termination at the HAProxy layer, which offloads computational overhead from your Moodle application servers. I've found this setup can reduce Moodle server CPU utilization by 10-15% during peak loads. The `cookie MoodleSession insert indirect nocache` directive is critical for Moodle, ensuring that a user's session is always routed back to the same Moodle application server, preventing login loops or lost session data. I typically use `roundrobin` for general traffic distribution as it's simple and effective, but you might consider `leastconn` for highly dynamic workloads.

## Moodle Data Consistency and Shared Storage Solutions

For a highly available Moodle setup, application servers must be stateless or, more accurately, share state. This means your `moodledata` directory and your Moodle codebase itself must be accessible by all Moodle application nodes. I've deployed several solutions for this:

1.  **NFS (Network File System):** This is my go-to for on-premises deployments. A dedicated NFS server or a highly available NFS cluster (e.g., using GlusterFS or DRBD) exports the `moodledata` directory, which is then mounted by all Moodle application servers. This ensures absolute consistency. Just make sure your NFS server is robust and has low latency to your Moodle nodes.
2.  **AWS EFS / Azure Files / Google Cloud Filestore:** For cloud deployments, managed file storage services are fantastic. They offer high availability, scalability, and ease of management. I recently migrated a university's Moodle instance from a single EC2 machine to an auto-scaling group behind HAProxy using EFS for `moodledata`, and the performance gains were remarkable, especially during peak course enrollments.
3.  **Shared Web Root (less common for Moodle, but possible):** While you can also share the Moodle codebase itself (e.g., `/var/www/html/moodle`), I generally prefer to deploy the Moodle code locally on each application server. This simplifies patching and ensures that each node isn't reliant on network storage for its core binaries. I use a deployment pipeline (Ansible or similar) to ensure all nodes have identical code.

The database, of course, also needs high availability. I always recommend a highly available database cluster like Percona XtraDB Cluster, Galera Cluster for MySQL, or a cloud-managed database service with read replicas and automated failover. The `config.php` on each Moodle application server then points to this highly available database endpoint.

## Real-World Moodle HAProxy Deployment Gotchas and My Fixes

Over the years, I've spent countless hours debugging Moodle HAProxy setups. Here are some of the most frustrating "gotchas" and how I've solved them:

1.  **The Persistent Login Loop:** This is probably the most common HAProxy-Moodle issue. Users would try to log in, seemingly succeed, then immediately be redirected back to the login page. I spent 18 hours debugging this at one point, tearing my hair out. The root cause? Incorrect session persistence configuration. If HAProxy wasn't consistently routing a user back to the *same* Moodle application server, the new server wouldn't recognize the existing session cookie, forcing a re-login.
    *   **The Fix:** Ensure your `backend` section has `cookie MoodleSession insert indirect nocache`. And crucially, make sure Moodle itself isn't generating multiple session cookies or cookies with inconsistent paths. Also, check that `cfg.php` has `$CFG->wwwroot` correctly set to the HAProxy's public URL, not an internal IP.

2.  **Stale Moodle Cache Data Across Nodes:** Users would report seeing old data, or changes made by an admin on one node wouldn't immediately reflect on another. This often happens with Moodle's internal caches.
    *   **The Fix:** While HAProxy handles traffic, Moodle's internal caching system needs to be aware of the clustered environment. First, ensure `moodledata` is on shared storage. Second, Moodle cron jobs (`php /path/to/moodle/admin/cli/cron.php`) should only run on *one* dedicated server, or be carefully orchestrated across nodes to avoid race conditions. For caching, I strongly recommend configuring Moodle to use an external, centralized cache like Redis or Memcached (e.g., `redis.conf` for sessions and `cachestore_redis` for application data) instead of file-based or local caches. This ensures all nodes see the same cache state.

3.  **HAProxy Falsely Marking Moodle Servers as Down:** HAProxy would suddenly report one or more Moodle backend servers as `DOWN`, even though I could access them directly. This often happened under heavy load.
    *   **The Fix:** This was usually a combination of overly aggressive health checks and Moodle being slow to respond. I'd typically tune the `http-check expect string "Moodle"` to target a very lightweight Moodle page, like `/login/index.php`. More importantly, I'd increase `timeout server` and `timeout client` in the `defaults` section, and adjust `inter`, `rise`, and `fall` parameters in the `server` definitions within the `backend`. For example, `inter 5s rise 3 fall 5` might be more appropriate if your Moodle takes longer to respond under load, giving it more leeway before marking it as unhealthy. Monitoring your Moodle nodes with tools like Grafana, pulling data from Moodle itself through a plugin or custom script (as discussed in [Building a Student Performance Dashboard with Grafana and Moodle Data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/)), is essential for understanding your system's true health.

4.  **Mixed Content Warnings and SSL Errors:** After enabling SSL offloading on HAProxy, users would see warnings about insecure content or Moodle's CSS/JS wouldn't load correctly.
    *   **The Fix:** Moodle needs to be told that it's running behind an SSL-terminating proxy. In your `config.php`, ensure `$CFG->wwwroot = 'https://your-moodle-domain.com';` is explicitly set to the HTTPS URL. Also, ensure HAProxy is adding the `X-Forwarded-Proto https` and `X-Forwarded-SSL on` headers, as Moodle often relies on these to determine the originating protocol.

## Choosing Your Moodle HAProxy Strategy: A Clear Recommendation

For almost all university and enterprise Moodle deployments, I unequivocally recommend a robust HAProxy setup with at least two HAProxy instances (for the load balancer itself to be highly available via Keepalived), 3-5 Moodle application servers, and a highly available database cluster. This architecture provides an excellent balance of performance, scalability, and cost-effectiveness.

While containerization with Docker and orchestration with Kubernetes are increasingly popular, I maintain that for most Moodle deployments, HAProxy on VMs or bare metal remains simpler to manage, more transparent to troubleshoot, and often more performant for I/O-heavy applications like Moodle without the added overhead and complexity of a full Kubernetes stack. Kubernetes might be overkill unless you have dozens of microservices or extremely elastic scaling requirements beyond what an auto-scaling group and HAProxy can offer. For simpler automation tasks, like programmatically updating Moodle users or courses, dedicated scripts (similar to how I've used [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/)) are often more straightforward than full container orchestration.

## Final Thoughts on Scaling Moodle

Building a highly available Moodle system with HAProxy isn't just about preventing downtime; it's about providing a consistent, performant experience that supports uninterrupted learning. By addressing session persistence, data consistency, and intelligent health checks, you create a resilient platform. Remember, the ultimate goal is to remove single points of failure, from your network edge all the way to your database. And while you're securing your LMS, consider how a unified authentication system like [Building a Campus-Wide Single Sign-On (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/) can further enhance both security and user experience across your entire digital campus ecosystem.