---
title: "Automating Moodle Deployment with Ansible Playbooks"
date: 2026-06-08T12:22:07+08:00
image: "images/blog/blog-post-5.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud", "Dev Log"]
tags: ["Moodle"]
description: "Automate Moodle deployment with production-ready Ansible playbooks. I'll share my hard-won lessons, specific failures, and best practices from deploying Moodle at scale."
---

I remember a particularly brutal Moodle upgrade for a university in Manila. We had a 12-hour maintenance window for a Moodle 3.9 to 4.1 migration, impacting over 15,000 active students. Midway through, a manually executed SQL script for a custom plugin failed, rolling back half the database and corrupting several activity modules. The rollback took 4 hours, and we ended up extending downtime by another 6, drawing ire from the academic registrar. That incident, which personally cost me 18 hours of continuous debugging fueled by instant coffee, cemented my resolve: manual deployments and upgrades are a ticking time bomb. This is exactly why I've dedicated significant effort to mastering `moodle ansible` automation for every subsequent deployment.

For nearly a decade, I've architected EdTech infrastructure across Asia-Pacific, deploying everything from Moodle and Canvas to Open edX. My experience consistently shows that automation, specifically with Ansible, isn't just a convenience; it's a critical reliability and security component for any educational institution running Moodle in production.

### Architecting the Moodle Ansible Playbook: A Foundational Overview

When I design an Ansible playbook for Moodle, I approach it as a modular blueprint. A robust `automate moodle deployment` strategy requires more than just copying files; it's about orchestrating servers, databases, and application-level configurations harmoniously. My standard Moodle playbook structure breaks down into several key roles, ensuring idempotent operations and clear separation of concerns:

1.  **`webserver`**: Configures Nginx (my web server of choice for performance with PHP-FPM) or Apache, including SSL/TLS setup via Let's Encrypt or institutional certificates.
2.  **`php`**: Installs PHP-FPM with necessary extensions (e.g., `php-cli`, `php-curl`, `php-gd`, `php-intl`, `php-mbstring`, `php-xml`, `php-zip`, `php-soap`, `php-pgsql` or `php-mysql`). Crucially, this role also tunes `php.ini` and `www.conf` settings.
3.  **`database`**: Provisions PostgreSQL (my strong preference over MySQL for Moodle's long-term scalability and data integrity) or MySQL, creates the Moodle database and user, and sets up appropriate permissions.
4.  **`moodle_app`**: Handles Moodle core file deployment (cloning from Git or extracting archives), `config.php` generation, data directory setup, and initial installation via `admin/cli/install.php` or `admin/cli/upgrade.php`.
5.  **`moodle_plugins`**: Manages the deployment of custom and third-party Moodle plugins, themes, and language packs.
6.  **`caching`**: Configures Redis or Memcached for Moodle's session and MUC (Moodle Universal Cache) stores, significantly improving responsiveness for high user loads.
7.  **`cron`**: Sets up the Moodle cron job, vital for background tasks like sending notifications, processing activity logs, and synchronizing user data.

This structured approach allows me to iterate on specific components without fear of breaking others. I routinely deploy a base Moodle instance capable of handling 5,000 concurrent users with this methodology, targeting 4GB RAM, 2vCPU servers for the application layer.

### Database Provisioning: PostgreSQL as Moodle's Robust Backbone

For any serious Moodle deployment, I wholeheartedly recommend PostgreSQL. Its advanced features, superior concurrency handling, and robust data integrity checks make it a far better choice than MySQL, especially for large datasets and heavy read/write operations common in an LMS. My `database` role, when deploying PostgreSQL, takes care of the following:

```yaml
# roles/database/tasks/main.yml
- name: Install PostgreSQL server
  ansible.builtin.apt:
    name: "postgresql-{{ postgresql_version }}"
    state: present
    update_cache: yes
  become: yes

- name: Ensure PostgreSQL service is running and enabled
  ansible.builtin.service:
    name: postgresql
    state: started
    enabled: yes
  become: yes

- name: Create Moodle database user
  community.postgresql.postgresql_user:
    db: postgres
    name: "{{ moodle_db_user }}"
    password: "{{ moodle_db_password }}"
    role_attr_flags: CREATEDB,LOGIN
    state: present
  become: yes
  become_user: postgres

- name: Create Moodle database
  community.postgresql.postgresql_db:
    name: "{{ moodle_db_name }}"
    owner: "{{ moodle_db_user }}"
    encoding: UTF8
    lc_collate: en_US.UTF-8
    lc_ctype: en_US.UTF-8
    template: template0
    state: present
  become: yes
  become_user: postgres

- name: Configure pg_hba.conf for secure access
  ansible.builtin.copy:
    src: pg_hba.conf.j2
    dest: /etc/postgresql/{{ postgresql_version }}/main/pg_hba.conf
    owner: postgres
    group: postgres
    mode: '0640'
  become: yes
  notify: Restart postgresql

- name: Configure postgresql.conf for performance
  ansible.builtin.copy:
    src: postgresql.conf.j2
    dest: /etc/postgresql/{{ postgresql_version }}/main/postgresql.conf
    owner: postgres
    group: postgres
    mode: '0644'
  become: yes
  notify: Restart postgresql
```

The `pg_hba.conf.j2` template usually restricts access to `host all all 127.0.0.1/32 trust` (for local access) or specifies the IP range of the Moodle application servers with `md5` authentication for production environments. For `postgresql.conf`, I tune `shared_buffers`, `work_mem`, `maintenance_work_mem`, and `max_connections` based on server resources and expected user load, often setting `shared_buffers` to 25% of system RAM and `max_connections` to 200-300 for a server handling 10,000 student enrollments.

### Web Server & PHP-FPM Configuration: Tuning for Scale and Security

Nginx is my go-to web server for Moodle. Its asynchronous event-driven architecture makes it incredibly efficient at handling static assets and proxying requests to PHP-FPM. Within my `webserver` and `php` roles, I ensure PHP-FPM is configured with adequate child processes and memory.

One thing I wish someone had told me before I started my journey: always prioritize PHP memory. Moodle, especially with numerous plugins, can be quite memory hungry. I've spent frustrating hours debugging "blank page" errors only to trace them back to an `out of memory` error hidden deep in PHP-FPM logs, often caused by the default `memory_limit = 128M`. For any production Moodle instance, I immediately set `memory_limit = 512M` (or even `1G` for very large or complex installations) in `/etc/php/{{ php_version }}/fpm/php.ini` and `/etc/php/{{ php_version }}/cli/php.ini`.

Another crucial setting is `max_execution_time`. While CLI scripts handle their own limits, web requests often hit a default 30-second timeout, which isn't enough for some Moodle processes, especially during upgrades or extensive course backups. I typically set `max_execution_time = 300` seconds.

### Automating Moodle Core Installation & Plugin Management

The `moodle_app` role is where the magic of deployment truly happens. I usually pull Moodle directly from its Git repository, allowing for easy version control and patch application.

```yaml
# roles/moodle_app/tasks/main.yml
- name: Clone Moodle from Git repository
  ansible.builtin.git:
    repo: "{{ moodle_git_repo }}"
    dest: "{{ moodle_install_dir }}"
    version: "{{ moodle_version_tag }}"
    force: yes
  become: yes
  become_user: "{{ moodle_app_user }}"

- name: Create Moodle data directory
  ansible.builtin.file:
    path: "{{ moodle_data_dir }}"
    state: directory
    owner: "{{ moodle_app_user }}"
    group: "{{ moodle_app_group }}"
    mode: '0770'
  become: yes

- name: Copy Moodle config.php
  ansible.builtin.template:
    src: config.php.j2
    dest: "{{ moodle_install_dir }}/config.php"
    owner: "{{ moodle_app_user }}"
    group: "{{ moodle_app_group }}"
    mode: '0644'
  become: yes

- name: Install Moodle via CLI if not installed (or upgrade)
  ansible.builtin.command:
    cmd: "php {{ moodle_install_dir }}/admin/cli/install.php --non-interactive --wwwroot={{ moodle_wwwroot }} --dataroot={{ moodle_data_dir }} --dbtype={{ moodle_db_type }} --dbhost={{ moodle_db_host }} --dbname={{ moodle_db_name }} --dbuser={{ moodle_db_user }} --dbpass={{ moodle_db_password }} --fullname={{ moodle_site_name }} --shortname={{ moodle_site_shortname }} --adminuser={{ moodle_admin_user }} --adminpass={{ moodle_admin_password }} --adminemail={{ moodle_admin_email }}"
    creates: "{{ moodle_install_dir }}/version.php" # Prevents re-running if Moodle is already installed
  become: yes
  become_user: "{{ moodle_app_user }}"
  when: not moodle_is_installed.stdout

- name: Run Moodle upgrade via CLI (for subsequent runs)
  ansible.builtin.command:
    cmd: "php {{ moodle_install_dir }}/admin/cli/upgrade.php --non-interactive"
  become: yes
  become_user: "{{ moodle_app_user }}"
  when: moodle_is_installed.stdout # Run only if Moodle was already installed (e.g., during an upgrade)
  # ... tasks for installing plugins, themes etc.
```

The `install.php` command is incredibly powerful, allowing a completely headless Moodle setup. For plugins, I typically use `git clone` or `unarchive` into the appropriate plugin directory (`mod`, `block`, `theme`, `auth`, etc.) followed by another `admin/cli/upgrade.php` to register them with Moodle. This ensures a consistent plugin set across all environments.

### The Crucial Post-Deployment Setup: Cron, Permissions, and Caching

After the core Moodle files are in place, several post-deployment steps are critical for a functional and performant LMS:

*   **Moodle Cron Job:** This is non-negotiable. Moodle depends on its cron job to perform background tasks, from processing pending emails to updating course activity. I always set this up via a dedicated `cron` role using Ansible's `ansible.builtin.cron` module, running every minute under the `www-data` user (or whichever user PHP-FPM runs as).
    ```yaml
    - name: Ensure Moodle cron job is configured
      ansible.builtin.cron:
        name: "Moodle cron job"
        user: "{{ moodle_app_user }}" # e.g., www-data
        minute: "*"
        job: "/usr/bin/php {{ moodle_install_dir }}/admin/cli/cron.php > /dev/null 2>&1"
        state: present
      become: yes
    ```
*   **File Permissions:** Moodle's `moodledata` directory needs to be writable by the web server user but *not* directly accessible via the web. Permissions are frequently a source of deployment headaches. I enforce `0770` on `moodledata` owned by `www-data:www-data`.
*   **Caching (Redis/Memcached):** For Moodle, caching is essential for performance, particularly with 10,000+ users. I typically deploy Redis as a dedicated caching server or on the application server itself for smaller deployments, configuring Moodle to use it for sessions and MUC. This reduces database load significantly.

### Gotchas: Navigating Real-World Moodle Ansible Roadblocks

After years of deploying Moodle with Ansible, I've hit more than my share of obscure issues. Here are a few common `automate moodle deployment` pitfalls and their fixes:

1.  **PHP Memory Limit Exceeded (The Silent Killer):**
    *   **Problem:** Moodle installations or upgrades hang, or pages load blank without clear errors in Nginx logs. Digging into PHP-FPM logs reveals `PHP Fatal error: Allowed memory size of 134217728 bytes exhausted (tried to allocate 20971520 bytes)`. This usually happens during `install.php` or `upgrade.php`, especially when dealing with many plugins or a large `data` directory migration.
    *   **Diagnosis:** Check `/var/log/php-fpm/www-error.log` (or equivalent) for `memory_limit` errors.
    *   **Fix:** Increase `memory_limit` in `/etc/php/{{ php_version }}/fpm/php.ini` and `/etc/php/{{ php_version }}/cli/php.ini` to `512M` or `1G`. Don't forget to restart PHP-FPM (`systemctl restart php{{ php_version }}-fpm`).
2.  **Moodle Data Directory Permissions:**
    *   **Problem:** Moodle throws "The moodledata directory is not writable" or "You need to change the permissions of the moodledata directory". This occurs if the web server user (e.g., `www-data`) doesn't have write access to `/var/www/moodledata`.
    *   **Diagnosis:** Moodle's pre-installation checks or error messages are usually quite clear.
    *   **Fix:** Ensure correct ownership and permissions: `ansible.builtin.file: path: /var/www/moodledata state: directory owner: www-data group: www-data mode: '0770'`. Crucially, if you create the directory manually, ensure the Ansible task *re-applies* these, and sometimes a `chown -R www-data:www-data /var/www/moodledata` is needed if previous manual steps messed it up.
3.  **PostgreSQL `pg_hba.conf` Connection Denied:**
    *   **Problem:** Moodle reports "Could not connect to database" during installation, even though the database user and password are correct. PostgreSQL logs (e.g., `/var/log/postgresql/postgresql-{{ postgresql_version }}-main.log`) show `FATAL: no pg_hba.conf entry for host "192.168.1.10" user "moodleuser" database "moodledb"`.
    *   **Diagnosis:** This means the PostgreSQL server is denying the connection based on the IP address, user, or database specified in `pg_hba.conf`.
    *   **Fix:** Edit `/etc/postgresql/{{ postgresql_version }}/main/pg_hba.conf` to add an entry that matches your Moodle application server's IP address, user, and database. For example: `host moodledb moodleuser 192.168.1.10/32 md5`. Then, restart PostgreSQL (`systemctl restart postgresql`).

### Clear Stances: Why Ansible Isn't Optional for EdTech Infrastructure

I have a strong, unequivocal stance: for any university deploying or managing an LMS, whether it's Moodle, Canvas, or Open edX, automation with tools like Ansible is not optional. It is a fundamental requirement for operational excellence, security, and scalability.

My recommendation is always to move beyond the manual clicks or ad-hoc shell scripts. Implementing `moodle ansible` playbooks drastically reduces human error, provides consistent deployments across development, staging, and production environments, and enables rapid disaster recovery. If you're building a campus-wide Single Sign-On (SSO) with Keycloak, as described in my article [Building a Campus-Wide Single Sign-On (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/), you'll find Ansible indispensable for configuring Moodle's authentication plugins consistently. Furthermore, managing the underlying infrastructure for a student performance dashboard powered by Moodle data and Grafana, as detailed in [Building a Student Performance Dashboard with Grafana and Moodle Data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/), becomes trivial with automation.

When evaluating database options, my recommendation remains PostgreSQL for Moodle, coupled with Redis for caching. While MySQL works, PostgreSQL scales better, handles heavy transaction loads with greater resilience, and offers more advanced features beneficial for data analysis or reporting integrations.

### Wrapping Up

Automating Moodle deployment with Ansible playbooks transforms a typically complex, error-prone process into a repeatable, auditable, and reliable workflow. I've personally seen it slash deployment times from half a day to under 15 minutes, freeing up critical infrastructure architects like myself to focus on more strategic initiatives. From provisioning the database and tuning PHP-FPM to deploying core Moodle and its plugins, Ansible provides the framework for robust EdTech infrastructure.

By investing in `moodle ansible` automation, you're not just deploying software; you're building a foundation for a resilient, performant, and secure learning environment that can evolve with your institution's needs. Remember, the goal isn't just to make things work, it's to make them work reliably, repeatedly, and with minimal fuss. For further insights into automating other aspects of EdTech, consider my experiences in [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/). Happy automating!