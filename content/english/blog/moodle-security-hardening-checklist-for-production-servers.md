---
title: "Moodle Security Hardening Checklist for Production Servers"
date: 2026-06-02T16:02:53+08:00
image: "images/blog/blog-post-1.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud", "Security"]
tags: ["Moodle"]
description: "Learn Alex Chen's battle-tested Moodle security hardening checklist for production servers. Discover critical configurations, common pitfalls, and exact fixes to secure your Moodle LMS."
---

I remember it like it was yesterday: a Friday evening, 7 PM, right as I was about to head out. Our campus Moodle instance, serving nearly 25,000 active students, suddenly started returning 500 errors. Initial checks showed high CPU and disk I/O, but nothing obvious in the logs. After a frantic 3-hour deep dive, I traced it back to a rogue PHP script uploaded via a misconfigured file upload component in a third-party Moodle plugin, which was then attempting to scan internal network ports. This wasn't an external attack; it was a payload dropped *inside* our production environment due to a simple oversight in our initial hardening strategy. It taught me a painful lesson: Moodle security hardening isn't a one-time setup; it's a continuous, multi-layered process, and ignoring even a seemingly minor detail can lead to a catastrophic compromise of your secure Moodle server.

Having personally deployed Moodle instances across numerous universities in the Asia-Pacific region, handling everything from a few thousand users to over 100,000 concurrent sessions, I've spent countless hours debugging, securing, and optimizing these environments. This isn't just theory; this is a checklist forged in the fires of production incidents.

## Layering OS and Network Defenses for a Secure Moodle Server

The foundation of any secure Moodle server deployment starts beneath the Moodle application itself. I always begin by treating the underlying operating system and network as the first line of defense.

First, **minimize the attack surface** on the OS. I deploy Moodle exclusively on a minimal Linux distribution (Ubuntu Server LTS or RHEL/CentOS Stream are my go-to's). Strip out all unnecessary packages. If it's not absolutely essential for Moodle, PHP, or your web server (Nginx or Apache), it doesn't get installed. This means no desktop environments, no developer tools, and certainly no Samba or FTP servers. I've seen deployments where developers left SSH daemons running on non-standard ports with weak passwords, just for convenience, and that's an invitation for trouble.

Next, **configure your firewall** strictly. On Linux, I use `ufw` or `firewalld` to allow only essential incoming traffic: SSH (port 22, often changed to a non-standard port like 2222 for production servers), HTTP (port 80) and HTTPS (port 443) for web traffic, and potentially your database port if the database server is on a separate machine (e.g., PostgreSQL on 5432, MySQL on 3306). All other ports are explicitly denied. For instance, a basic `ufw` setup might look like this:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 2222/tcp  # SSH on non-standard port
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

Beyond the server's host firewall, I strongly recommend a **Web Application Firewall (WAF)** at the network edge. Whether it's a dedicated hardware appliance, a cloud service like Cloudflare, or an open-source solution like ModSecurity integrated with Nginx/Apache, a WAF is invaluable. It provides real-time protection against common web vulnerabilities like SQL injection, cross-site scripting (XSS), and brute-force attacks that Moodle's built-in defenses might miss or delay. I once spent 15 hours trying to mitigate a credential stuffing attack on a Moodle instance, only to realize a WAF could have blocked 98% of the malicious requests at the edge without impacting server performance.

## Hardening the Web Server and PHP Environment

This is where a significant chunk of Moodle's attack surface lies. For the web server, I predominantly use Nginx for its performance and resource efficiency, especially with a PHP-FPM backend.

**Nginx Configuration:**
*   **SSL/TLS First:** Enforce HTTPS for all traffic using strong ciphers and protocols (TLSv1.2+). Disable insecure protocols like TLSv1.0 and TLSv1.1. I use `certbot` with Let's Encrypt for automated certificate management.
*   **Hide Server Tokens:** Prevent Nginx from revealing its version number in HTTP headers. Add `server_tokens off;` to your `nginx.conf`.
*   **Limit Request Body Size:** Prevent large file upload attacks by setting `client_max_body_size` appropriately in your Nginx configuration. For Moodle, I typically set it to `1024M` (1GB) to accommodate large course files, but adjust based on your university's policy.
*   **Protect `moodledata`:** This is crucial. Moodle's data directory (`moodledata`) *must* be located outside the web root and inaccessible directly via the web. Even if you place it outside, I add an Nginx rule to explicitly deny access to it, just in case:

```nginx
# Nginx configuration snippet for moodledata protection
location ~ ^/moodledata/ {
    deny all;
    return 404;
}
```

**PHP-FPM and PHP Configuration:**
*   **Run PHP-FPM as a dedicated user:** Create a separate, unprivileged user (e.g., `moodle-php`) for PHP-FPM processes, distinct from the web server user. This limits potential damage if a PHP process is compromised.
*   **Disable Dangerous Functions:** In `php.ini`, disable functions that can be abused for command execution or file system manipulation. My standard list includes `exec`, `shell_exec`, `passthru`, `system`, `proc_open`, `popen`, `dl`, `show_source`, `posix_kill`, `posix_setpgid`, `posix_setsid`, `posix_setuid`, `posix_setgid`, `symlink`, `link`, `apache_child_terminate`, `pcntl_exec`. Add them to `disable_functions = ...`
*   **Limit Resource Usage:** Prevent denial-of-service (DoS) attacks or runaway scripts. Set `memory_limit` (e.g., `256M` or `512M` for Moodle's needs), `max_execution_time` (e.g., `300`), and `max_input_time` (e.g., `60`) in `php.ini`.
*   **`open_basedir` Restriction:** Confine PHP script execution to specific directories. This prevents scripts from accessing files outside the Moodle web root and `moodledata`. Set `open_basedir = /var/www/moodle:/var/moodledata:/tmp` (adjust paths as needed).
*   **Error Logging:** Disable `display_errors` in production and ensure `log_errors = On` and `error_log` points to a secure, non-web-accessible location.
*   **Opcode Cache (OPcache):** Crucial for performance, but also security. Ensure it's configured correctly. `opcache.validate_timestamps=1` is generally safe, but for maximum performance after a Moodle upgrade, I often use `opcache_reset()` via a maintenance script.

## Securing the Moodle Data Directory and Database

This is often where I find the most critical vulnerabilities in initial deployments.

**Moodle Data Directory (`moodledata`):**
*   **Location:** As mentioned, *always* outside the web root. For example, if Moodle is in `/var/www/html/moodle`, `moodledata` should be in `/var/moodledata`.
*   **Permissions:** This is a recurring "gotcha." The `moodledata` directory and its contents must be owned by the web server user (e.g., `www-data` for Apache/Nginx on Ubuntu) and *not* be writable by others. I typically set permissions like `chmod -R 0770 /var/moodledata` and `chown -R www-data:www-data /var/moodledata`. This ensures only the web server can write to it, and prevents other users on the system from tampering.

**Moodle Database:**
*   **Dedicated Database Server:** For any production Moodle instance with more than 1,000 active users, I strongly recommend a dedicated database server, separate from the web server. This provides isolation and better resource management.
*   **Strong Credentials:** Create a specific database user for Moodle with a complex, randomly generated password (minimum 32 characters, including special characters).
*   **Least Privilege:** Grant the Moodle database user only the necessary permissions (SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP on the Moodle database) and nothing more. No `SUPER` or `GRANT` privileges.
*   **Encrypt Database Connections:** If your database is on a separate server, encrypt the connection using SSL/TLS. This prevents eavesdropping on sensitive student data.
*   **Regular Backups:** Implement a robust backup strategy, encrypting backups, and storing them off-site. I usually schedule daily full backups with hourly transaction log backups for mission-critical deployments.

## Advanced Moodle Configuration and Management

Moodle itself offers numerous security controls that need to be correctly configured.

*   **Authentication:** For university environments, I advocate strongly for Single Sign-On (SSO). SAML2 is robust, and integrating with an existing identity provider like Keycloak drastically reduces password management headaches and improves overall security. I've personally streamlined campus-wide SSO initiatives, and [Building a Campus-Wide Single Sign-On (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/) covers many of the principles I apply. If you must use Moodle's internal authentication, enforce strong password policies, enable account lockout, and use CAPTCHA.
*   **Security Scans:** Regularly run Moodle's built-in `admin/tool/health` checks and security reports. These are fantastic for identifying common misconfigurations.
*   **Plugin Management:** Plugins are common attack vectors. Only install plugins from trusted sources (Moodle plugins directory) and ensure they are actively maintained. Before deployment, review plugin code for potential vulnerabilities. I've seen Moodle instances compromised by outdated or poorly coded third-party plugins. Always update them promptly.
*   **Audit Logging:** Configure Moodle's activity logging (Settings > Site administration > Reports > Logs) to be verbose. This is critical for forensic analysis in case of a breach. Forward these logs to a centralized log management system (e.g., ELK stack, Splunk) for analysis and alerting. This also helps when [Building a Student Performance Dashboard with Grafana and Moodle Data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/), as you'll have rich datasets.
*   **Session Management:** Set appropriate session timeouts (`admin/settings.php?section=securitysessions`). For high-security environments, enable `forceloginforprofiles` to prevent profile enumeration.
*   **Updates:** Stay current with Moodle releases. Every major and minor release includes security fixes. Don't fall behind. I schedule a maintenance window for Moodle core updates every 2-3 months.

## Gotchas in Moodle Security Hardening

In my 9 years, I've stumbled upon specific pitfalls more times than I care to admit. Here are a few:

1.  **`moodledata` in web root (or accessible via Nginx/Apache alias):** This is the most common and dangerous mistake. A direct web request to `moodledata/filedir/` could expose user-uploaded files or even configuration backups if not properly secured.
    *   **Fix:** Absolutely ensure `moodledata` is outside your web server's document root. Verify with `curl -I https://yourmoodle.com/moodledata/README.txt` – it should return a 403 or 404, not 200. Double-check your Nginx/Apache configurations for any aliases that inadvertently expose it.
2.  **`config.php` with incorrect permissions or containing sensitive data:** Sometimes `config.php` ends up with world-readable permissions or, worse, contains database credentials directly hardcoded when environment variables should be used.
    *   **Fix:** Set `chmod 0440 config.php` and `chown www-data:www-data config.php`. Better yet, consider externalizing sensitive variables, though Moodle's `config.php` is its primary configuration mechanism. Make sure database passwords are robust and rotated periodically.
3.  **Outdated PHP or Moodle versions running with known CVEs:** I've spent an entire weekend patching 15 critical Moodle sites because a CVE in an older PHP version (`7.2.x` at the time) allowed for remote code execution, and no one had updated.
    *   **Fix:** Implement a strict patch management policy. Subscribe to Moodle's security announcements and your OS distribution's security feeds. Use tools like `php-fpm` to run multiple PHP versions if you have legacy applications, but keep your Moodle instance on the latest stable and supported PHP branch (currently PHP 7.4+ or 8.x).

## Trade-offs: Security, Performance, and Usability

There's always a balance. Implementing every single security control I've mentioned can add a tiny bit of overhead. For example, aggressive WAF rules can occasionally block legitimate user traffic, requiring fine-tuning. Heavily restricted `open_basedir` settings might interfere with some third-party plugins that attempt to write to non-standard directories. High session timeouts for security can frustrate users who get logged out frequently.

My clear stance: **security must take precedence, especially in an educational context dealing with student data.** The performance impact of a well-configured WAF or a dedicated database server is negligible compared to the cost of a data breach. The slight inconvenience of a stricter password policy or a shorter session timeout is a small price to pay for protecting thousands of student accounts. I always aim for a layered approach, prioritizing critical controls like `moodledata` protection, database security, and prompt updates. For new deployments, I'd rather over-secure and then selectively loosen non-critical restrictions based on performance monitoring and user feedback, rather than starting insecure and playing catch-up.

## Maintaining a Secure Moodle Environment

Securing Moodle is not a set-it-and-forget-it task. It demands continuous vigilance, regular audits, and a proactive approach to updates. The threat landscape evolves, and your defenses must evolve with it. By implementing this checklist, you'll build a robust foundation for your Moodle production server, significantly reducing its attack surface and protecting your users.

For more insights into managing complex EdTech systems, you might find our article on [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/) interesting, as many of the underlying API security principles apply across different LMS platforms. Keep those servers patched, keep those logs monitored, and keep learning.