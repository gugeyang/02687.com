---
title: "Troubleshooting Moodle Cron Jobs and Scheduled Tasks"
date: 2026-06-11T11:38:47+08:00
image: "images/blog/blog-post-6.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud"]
tags: ["Moodle"]
description: "Experiencing 'moodle cron not running' or stalled scheduled tasks? I'll share how I diagnose and fix common Moodle cron job failures, optimize performance, and set up robust monitoring, drawing from 9 years of real-world deployments."
---

I've seen it too many times: a university's Moodle instance, serving 50,000 students, appears to be running smoothly, yet behind the scenes, critical operations are grinding to a halt. Forum digests aren't sending, course completion records are stuck, and user enrollments from the SIS haven't updated in 24 hours. The culprit? A silently failing Moodle cron job. I still remember a deployment for a large university in Malaysia where I spent a grueling 30 hours tracking down a subtle `php-cli` permission issue that caused cron to fail without any explicit errors in the standard `syslog`. It's a silent killer for any production LMS, eroding data integrity and user experience byte by byte.

## The Silent Killer: Diagnosing a Stalled Moodle Cron

When Moodle's scheduled tasks stop processing, the first instinct is often to check the Moodle UI under `Site administration > Server > Scheduled tasks`. But by the time tasks appear stuck there, you're already in a reactive state. The real problem usually lies deeper, at the OS level where the `cron` daemon runs. I've found that the most common cause for "moodle cron not running" isn't a Moodle misconfiguration itself, but an underlying system issue preventing the `php-cli` command from executing successfully or completely. My first step is always to verify the system cron.

## Verifying Your Moodle Cron Daemon and PHP CLI Setup

Before diving into Moodle's internal tasks, we need to ensure the very foundation is solid. Is your system's `cron` daemon actually running? And is your PHP CLI environment configured correctly?

On a Linux system, I always start by confirming the cron service status:

```bash
sudo systemctl status cron
# or for older systems
sudo service cron status
```

You should see it active and running. If not, start it: `sudo systemctl start cron`.

Next, let's look at the `crontab` entry for Moodle. It's almost always under the web server user (e.g., `www-data`, `apache`, `nginx`). If you're using `sudo -u www-data crontab -e` to edit, ensure that the user has the necessary permissions. A typical, production-ready `crontab` entry for Moodle looks something like this, designed for robust logging and error capture:

```bash
# Moodle Cron Job - Executes every minute
# Ensure this is owned by the web server user (e.g., www-data)
# Path to PHP CLI binary
PHP_CLI="/usr/bin/php" 

# Path to Moodle's admin/cli/cron.php script
MOODLE_CRON_SCRIPT="/var/www/html/moodle/admin/cli/cron.php"

# Path for cron logs
CRON_LOG_DIR="/var/log/moodle_cron"
CRON_LOG_FILE="${CRON_LOG_DIR}/cron_output.log"
CRON_ERROR_FILE="${CRON_LOG_DIR}/cron_error.log"

# Create log directory if it doesn't exist
# This is usually handled by provisioning tools, but useful to keep in mind
mkdir -p "${CRON_LOG_DIR}"

# Run Moodle cron every minute, append output/errors to separate log files, timestamp entries
* * * * * ${PHP_CLI} ${MOODLE_CRON_SCRIPT} >> ${CRON_LOG_FILE} 2>> ${CRON_ERROR_FILE}
```

*Note*: If you are deploying Moodle with Ansible playbooks, this entire setup, including log directory creation and permissions, can be fully automated, which is what I recommend for consistency across environments. You can learn more about this approach by reading my previous article on [Automating Moodle Deployment with Ansible Playbooks](/blog/automating-moodle-deployment-with-ansible-playbooks/).

Crucially, verify the PHP CLI environment. Run `php -v` to ensure you're using the expected PHP version. Then, compare `php -i | grep memory_limit` with `phpinfo()` output from your web server. I've often seen `memory_limit` for CLI default to a paltry 128M or 256M, while the web server PHP has 512M or 1024M. Many Moodle tasks, especially course backups or large user data processing, demand significant memory. I always set CLI `memory_limit` to at least 512M, and often 1024M, in the dedicated `php.ini` used by `php-cli` (usually `/etc/php/X.X/cli/php.ini`).

## Unmasking Common Moodle Cron Failure Modes

Beyond basic setup, several common scenarios lead to "moodle scheduled tasks" failing.

1.  **Out of Memory (OOM) Kills:** This is the specific failure I spent 30 hours debugging on that Malaysian campus Moodle. The server was an AWS EC2 t3.medium running Moodle 3.9, serving around 1,000 active students daily. The `crontab` entry was correct and showed exit code 0, but tasks weren't completing. The logs `cron_output.log` and `cron_error.log` were empty. After deep diving, I checked `dmesg` output and `/var/log/syslog`, revealing `Out of memory: Kill process [PID] (php)` messages. The system was silently killing the `php-cli` process before it could even write an error. The fix involved increasing the CLI `memory_limit` to 1024M and, ultimately, upgrading the EC2 instance to a c5.xlarge with 8GB RAM to handle the 100GB Moodle data directory and peak loads.
2.  **Permissions Issues:** The `www-data` user (or equivalent) *must* have read/write access to `moodle/config.php` and the `moodle/moodledata` directory, including its subdirectories. If cron can't write to its temporary files or logs, it will fail. I've seen situations where `moodledata` was mounted from an NFS share with incorrect `no_root_squash` settings, leading to write failures under `www-data`.
3.  **Concurrent Cron Runs:** If Moodle's cron takes longer than 60 seconds to complete, successive cron jobs will overlap. This often leads to database contention, file locking issues, or task corruption. Moodle has a built-in mechanism to prevent this (the `LOCK_ADODB_CRON_FILE` lock file in `moodledata/temp`), but I've seen it fail when the lock file itself becomes unwriteable or the previous process crashes without releasing the lock. The solution isn't to lengthen the cron interval (which would delay critical tasks), but to optimize individual scheduled tasks or consider a distributed task queue (more on that later).
4.  **Database Connection Limits:** On busy systems, the `php-cli` process trying to connect to MySQL/PostgreSQL might hit the `max_connections` limit, especially if the web server is already consuming most connections. You'll see "Too many connections" errors in your cron logs. Increase `max_connections` in your database configuration and ensure Moodle's `dbconnections` setting in `config.php` isn't set excessively high.

## Optimizing Moodle Scheduled Tasks for High-Concurrency Environments

For large deployments, simply running `cron.php` every minute might not be enough or efficient. I often recommend looking into specific task optimization:

*   **Dedicated Task Queues:** For extremely large Moodle instances (e.g., 100,000+ users), `cron.php` can become a bottleneck. Consider offloading long-running, non-time-critical tasks (like analytics processing or report generation) to a dedicated queue system like Redis or RabbitMQ using a custom Moodle plugin, or even leveraging AWS SQS for serverless task processing. This allows Moodle's core cron to remain lean and handle critical real-time tasks.
*   **Task Prioritization:** Moodle 4.x has improved scheduled task management, allowing administrators to enable/disable tasks and set custom schedules. Review `Site administration > Server > Scheduled tasks` and disable any tasks not actively used. Some tasks, like "Process course completion," can be very resource-intensive on a large Moodle instance; consider scheduling them during off-peak hours if they don't require real-time processing.
*   **Segmenting Cron:** Instead of running one `cron.php` that does everything, I've implemented setups where separate `crontab` entries run specific Moodle CLI scripts. For example, a dedicated script for user syncs that runs every 5 minutes (`admin/cli/users.php`), and another for course backups that runs nightly (`admin/cli/backup.php`), thereby reducing the load on the main `cron.php` execution. This also aligns well if you are thinking about [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/), as similar principles apply to segmenting tasks for external system integrations.

## Beyond the Basics: Robust Monitoring and Alerting for Cron Health

Checking logs manually is reactive. For any production system, proactive monitoring is non-negotiable.

*   **Log Aggregation:** Centralize your `moodle_cron` logs (and `syslog`, `dmesg`) to a system like ELK (Elasticsearch, Logstash, Kibana) or Splunk. This allows for quick searches and trend analysis.
*   **Health Checks and Pings:** I implement a simple PHP script that Moodle's cron *should* run every minute, which updates a timestamp in a database table or a simple file. An external monitoring tool (like Prometheus/Grafana or Zabbix) then checks this timestamp. If it's older than, say, 2 minutes, an alert fires. This is far more reliable than just monitoring the cron process itself.
    *   For example, you could have a `cron_status.php` that simply writes `echo time();` to `moodledata/cron_last_run.txt`. Your monitoring system then checks the age of this file.
    *   When I talk about [Building a Student Performance Dashboard with Grafana and Moodle Data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/), I often emphasize that reliable cron execution is the bedrock for getting fresh data into your dashboard. If cron is broken, your analytics are stale.
*   **Process Monitoring:** Monitor the `php` processes spawned by cron. Look for processes that run for excessively long periods (e.g., >10 minutes) or consume disproportionate CPU/memory. Tools like `htop`, `atop`, or even a simple `ps aux | grep cron.php` can give immediate insights.

## "Gotchas" and Hard-Learned Lessons from the Field

1.  **PHP Version Mismatch:** You might have multiple PHP versions installed. Your `crontab` might call `/usr/bin/php`, but your web server uses `/usr/local/bin/php7.4`. Ensure the PHP CLI binary specified in `crontab` (e.g., `/usr/bin/php`) is the *exact* one Moodle expects and that it has the necessary extensions. I've spent hours debugging Moodle tasks failing only to discover `intl` or `mbstring` wasn't enabled for `php-cli`.
    *   *Fix:* Specify the full path to the correct PHP CLI binary in your `crontab` entry (e.g., `/usr/bin/php7.4` instead of just `php`). Then run `php7.4 -m` to check loaded modules and compare it with your web server's `phpinfo()`.
2.  **`PATH` Environment Variable:** When cron runs, it operates with a very minimal `PATH` environment variable. If your `cron.php` script or any custom Moodle task relies on external binaries or commands (e.g., `rsync`, `ffmpeg`) that aren't in standard system paths, cron won't find them.
    *   *Fix:* Either specify the full, absolute path to the binary in your Moodle script (e.g., `/usr/bin/rsync`) or, better yet, define a more comprehensive `PATH` at the top of your `crontab` file: `PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`.
3.  **`wget` or `curl` vs. `php-cli`:** Some older guides suggest running Moodle cron via `wget` or `curl` to `http://yourmoodle.com/admin/cli/cron.php`. **Never do this in production.** This executes cron through your web server's PHP-FPM/Apache/Nginx context, which might have different `memory_limit`, `max_execution_time`, and often an unnecessary network overhead. It also bypasses the CLI's optimized execution path and can expose your cron endpoint to external access if not properly secured.
    *   *Fix:* Always use the `php-cli` binary directly as demonstrated in the `crontab` example.

## The Trade-offs: Centralized Cron vs. Distributed Task Management

When it comes to "moodle scheduled tasks" on a large scale, I often get asked whether to stick with the traditional single-server cron or move to a distributed task management system. My stance is clear: **for most university Moodle deployments (up to 50,000-75,000 users), a well-configured, centralized `cron` daemon on a sufficiently provisioned server is perfectly adequate and significantly simpler to manage.**

Moving to distributed systems like Celery/Redis, Gearman, or similar technologies introduces significant operational overhead: more moving parts, complex debugging, and higher infrastructure costs. While these are invaluable for massive, multi-tenant SaaS platforms or highly-concurrent applications, they are often overkill for a typical university LMS. The complexity rarely justifies the benefit unless you're processing hundreds of thousands of concurrent tasks or integrating with dozens of external systems in real-time.

My recommendation? Invest in a robust monitoring stack for your existing cron, optimize your PHP CLI settings, and ensure your server has ample resources (CPU, RAM, fast storage). For the vast majority of institutions I've worked with across Asia-Pacific, a single, powerful Moodle server with a meticulously configured cron has proven reliable and cost-effective.

Troubleshooting Moodle cron jobs can feel like chasing ghosts in the machine, especially when tasks silently fail. But by systematically verifying your `crontab` setup, understanding PHP CLI nuances, diligently checking system logs, and proactively monitoring execution, you can maintain a healthy, responsive Moodle environment. The stability of your scheduled tasks is directly linked to the data integrity and overall user experience for your students and educators. Keep these lessons in mind, and you'll save yourself countless hours of late-night debugging. For deeper dives into managing your LMS infrastructure, check out our posts on [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/) or how we approach [Automating Moodle Deployment with Ansible Playbooks](/blog/automating-moodle-deployment-with-ansible-playbooks/).