---
title: "Configuring Moodle SMTP Email with SPF and DKIM to Avoid Spam"
date: 2026-06-02T23:05:21+08:00
image: "images/blog/blog-post-2.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud"]
tags: ["Moodle"]
description: "Master Moodle SMTP setup with SPF and DKIM to fix Moodle email not sending issues. Learn my proven methods for high email deliverability and authentication."
---

I remember a critical Monday morning at a university in Jakarta. Their Moodle instance, supporting over 20,000 active students, suddenly went silent. No password reset emails, no forum notifications, no assignment submission confirmations. The support queue exploded. My initial check showed Moodle's "outgoing mail configuration" was correct in the UI, but nothing was actually leaving the server. Digging deeper into the PHP error logs (which, incidentally, I've spent more hours staring at than I care to admit across Moodle, Canvas, and Open edX deployments), I found cryptic "SMTP connect() failed" or "could not authenticate" messages. It turned out to be a classic triple threat: an upstream SMTP service had changed its TLS cipher suite requirements, a firewall rule on the Moodle server was silently blocking outbound connections to port 587, and critically, the domain's SPF and DKIM records were either missing or incorrectly configured, leading to legitimate Moodle emails being summarily rejected by recipient mail servers. This isn't just an inconvenience; it's a breakdown of critical educational infrastructure.

### The Silent Killer: Why Moodle Email Deliverability Demands Your Attention

Moodle, at its core, is a communication platform. From user registrations and password resets to forum discussions and grading notifications, email is the lifeblood connecting the LMS to its users. When these emails fail to deliver, the user experience craters, and administrative overhead skyrockets. I've personally seen a 40% increase in help desk tickets related to password resets alone when email deliverability issues strike. The problem isn't always Moodle's internal settings; often, it's about how the *internet* perceives your emails. Spam filters are aggressive, and if your emails lack proper sender authentication, they're dead on arrival in the spam folder, if not outright rejected. This is where Moodle's SMTP configuration, coupled with robust SPF and DKIM DNS records, becomes absolutely non-negotiable.

### Demystifying Moodle's SMTP Settings: A Deep Dive into `config.php`

While Moodle offers UI settings for email, for any production-grade deployment, especially with an external SMTP service, I strongly advocate for configuring SMTP directly in `config.php`. This gives you granular control, ensures consistency across updates, and makes troubleshooting clearer. I’ve managed Moodle instances with 50,000+ users that rely on this setup.

Here’s a production-ready snippet for `config.php` I routinely use. This assumes you’re using an external SMTP relay like AWS SES, SendGrid, or Mailgun, which I recommend for any university-scale deployment. Self-hosting your own mail server on the Moodle box is a battle you rarely win without dedicated full-time staff, and even then, deliverability is a nightmare.

```php
<?php  // config.php - add these lines at the end of the file

// --- SMTP Configuration ---
// If you are using an external SMTP service (recommended for production)

// Enable SMTP sending
$CFG->smtphosts = 'smtp.yourdomain.com:587'; // Replace with your SMTP host and port
$CFG->smtpsecure = 'tls';                  // 'ssl' for port 465, 'tls' for port 587, '' for no encryption
$CFG->smtpuser = 'your_smtp_username';    // Replace with your SMTP username
$CFG->smtppass = 'your_smtp_password';    // Replace with your SMTP password
$CFG->smtpmaxbulk = 100;                   // Maximum number of emails to send in one bulk session (adjust as needed)
$CFG->smtptimeout = 30;                    // SMTP connection timeout in seconds

// Set a default 'From' address for Moodle emails.
// This is critical for SPF alignment. MUST be a valid email from your domain.
$CFG->noreplyaddress = 'moodle@yourdomain.com';

// If you want all system-generated emails to appear to come from this address, regardless of who initiated them.
// $CFG->emailfromnoreply = true; 

// A list of addresses (comma-separated) to add as reply-to for all outgoing Moodle emails.
// Optional, but useful for managing replies.
// $CFG->emailreplyto = 'support@yourdomain.com'; 
?>
```

**Key takeaways from this configuration:**

*   `$CFG->smtphosts`: Always include the port. I recommend `587` with `tls` for opportunistic encryption or `465` with `ssl` for explicit encryption. Avoid port `25` unless absolutely necessary and you understand the security implications.
*   `$CFG->smtpuser` and `$CFG->smtppass`: Use a dedicated SMTP user. Never reuse credentials.
*   `$CFG->noreplyaddress`: This is one of the biggest "gotchas" I’ve seen. This address *must* belong to the domain for which you are configuring SPF and DKIM. If Moodle tries to send an email "from" `moodle@somedomain.com` but your SPF/DKIM only covers `yourdomain.com`, you're asking for trouble.

### Implementing SPF Records for Sender Authentication

Sender Policy Framework (SPF) is a DNS TXT record that tells recipient mail servers which IP addresses are authorized to send email on behalf of your domain. Without it, mail servers have no way of knowing if an email "from" your domain is legitimate or forged. I've spent 3 hours debugging why a new Moodle deployment's emails kept landing in junk folders, only to find the SPF record was completely missing.

Here's how to structure a robust SPF record. You’ll add this as a TXT record in your domain’s DNS manager (e.g., Cloudflare, AWS Route 53, your registrar).

```
NAME: @ or yourdomain.com
TYPE: TXT
VALUE: "v=spf1 include:spf.protection.outlook.com include:_spf.google.com include:sendgrid.net include:amazonses.com ~all"
TTL: 3600 (or your preferred setting)
```

**Breaking down the SPF value:**

*   `v=spf1`: Declares this is an SPF record, version 1.
*   `include:spf.protection.outlook.com`, `include:_spf.google.com`, etc.: These `include` mechanisms are critical. They delegate authority to third-party services like Microsoft 365, Google Workspace, SendGrid, or AWS SES. You *must* include the specific SPF records for your chosen SMTP provider. My example includes common ones; yours will likely be a subset.
*   `~all`: This is a "softfail." It tells recipient servers that emails from unauthorized IPs *should* be treated with suspicion, but not outright rejected. For initial deployments, I start with `~all`. Once I’m confident all legitimate sending sources are covered, I often move to `-all` (hardfail) for stricter enforcement, though `~all` is generally safer for complex environments.
*   **Important**: You should only have *one* SPF TXT record per domain. Merging multiple `include` statements into a single record is crucial.

### Generating and Configuring DKIM for Email Integrity

DomainKeys Identified Mail (DKIM) adds a digital signature to your outgoing emails, allowing recipient servers to verify that the email hasn't been tampered with in transit and that it genuinely originates from your domain. While SPF authenticates the *sender's server*, DKIM authenticates the *email's content and origin*.

Configuring DKIM typically involves two steps:

1.  **Generating the DKIM key pair:** Your SMTP provider (e.g., AWS SES, SendGrid, Mailgun) will provide you with a public DKIM key and a selector. You usually don't generate this yourself; the service generates it.
2.  **Adding a CNAME or TXT record to your DNS:** This record, provided by your SMTP service, points to their DKIM validation servers or contains the public key itself.

For example, if you're using AWS SES, you might get three CNAME records:

```
NAME: 20210201._domainkey.yourdomain.com
TYPE: CNAME
VALUE: 20210201.dkim.us-east-1.amazonses.com
TTL: 3600

NAME: 20210204._domainkey.yourdomain.com
TYPE: CNAME
VALUE: 20210204.dkim.us-east-1.amazonses.com
TTL: 3600

NAME: 20210207._domainkey.yourdomain.com
TYPE: CNAME
VALUE: 20210207.dkim.us-east-1.amazonses.com
TTL: 3600
```

The selector (`20210201` in this example) is unique and allows your domain to have multiple DKIM keys simultaneously (e.g., if you use different services for different email types). I can't stress this enough: *follow your SMTP provider's exact instructions for DKIM setup*. They vary slightly.

### Real-World Debugging: My Moodle Email Troubleshooting Playbook

I've spent countless hours debugging "Moodle email not sending" issues. Here are the common culprits and my exact fixes:

1.  **Firewall Blocks (the most frequent offender):**
    *   **Problem:** The Moodle server simply cannot connect to the external SMTP host. Outbound ports 587, 465, or 25 are blocked by a local firewall (`ufw`, `firewalld`, `iptables`) or a cloud security group (AWS Security Groups, Azure Network Security Groups, Google Cloud Firewall Rules). I've seen this block a university's entire Moodle email stream for 48 hours.
    *   **Diagnosis:** From the Moodle server's command line, `telnet smtp.yourdomain.com 587` (replace with your host and port). If it hangs or times out, it's a firewall.
    *   **Fix:**
        *   Local: `sudo ufw allow out 587` (for UFW) or `sudo firewall-cmd --permanent --add-port=587/tcp --zone=public && sudo firewall-cmd --reload` (for Firewalld).
        *   Cloud: Update the outbound rules for the Moodle server's security group/firewall to allow traffic to your SMTP host on the required port.
2.  **PHP Extensions Missing or Disabled:**
    *   **Problem:** Moodle's underlying PHPMailer library relies on specific PHP extensions for secure communication (e.g., `php-openssl`, `php-sockets`). If these are missing or disabled, you'll see generic SMTP connection errors. I spent 5 hours on one deployment where `php-openssl` was mysteriously missing after an OS upgrade.
    *   **Diagnosis:** Check `php -m` or `phpinfo()` output for `openssl` and `sockets`. Look at your Moodle server's Apache/Nginx error logs and PHP-FPM logs (e.g., `/var/log/php-fpm/error.log`).
    *   **Fix:** Install them: `sudo apt install php8.2-fpm php8.2-cli php8.2-common php8.2-curl php8.2-gd php8.2-intl php8.2-mbstring php8.2-mysql php8.2-soap php8.2-xml php8.2-xmlrpc php8.2-zip php8.2-imagick php8.2-gmp php8.2-bcmath php8.2-redis php8.2-memcached php8.2-ldap php8.2-opcache php8.2-snmp php8.2-sqlite3 php8.2-pgsql -y` (example for Ubuntu 22.04 and PHP 8.2), then `sudo phpenmod openssl sockets` and `sudo systemctl restart php8.2-fpm`.
3.  **SPF/DKIM Misalignment or Caching Issues:**
    *   **Problem:** Emails are sent successfully by Moodle (confirmed by SMTP service logs), but never reach the inbox. Recipient mail servers are silently dropping them or routing to spam due to failed authentication. DNS changes can take time to propagate, especially TTLs are high.
    *   **Diagnosis:** Use online tools like `mxtoolbox.com` or `mail-tester.com` to send a test email from Moodle. They will report on SPF, DKIM, and DMARC status. You can also manually query DNS records using `dig TXT yourdomain.com` for SPF and `dig CNAME selector._domainkey.yourdomain.com` for DKIM (adjust selector).
    *   **Fix:**
        *   Double-check SPF and DKIM records against your SMTP provider's documentation. Ensure `noreplyaddress` in Moodle aligns with the SPF domain.
        *   Reduce DNS TTLs (`300` seconds for testing, then `3600` for production) during changes to speed up propagation.
        *   Verify the *sender domain* configured in your SMTP service matches the domain you’re authenticating.

### Architectural Choices: Hosted SMTP vs. On-Premise for Moodle

When it comes to email, I take a very clear stance: **use a dedicated, hosted SMTP service for Moodle deployments handling more than a few hundred users.** For universities, this is non-negotiable. I've personally scaled Moodle instances to support 50,000 students, sending tens of thousands of emails daily, and trying to manage that email volume with an on-premise Postfix or Exim instance on the Moodle server itself is a recipe for disaster.

**Why I recommend hosted SMTP (e.g., AWS SES, SendGrid, Mailgun):**

*   **Deliverability:** These services specialize in email delivery, managing IP reputation, spam complaints, and adhering to complex email standards. This is a full-time job for experts, not something you want to offload to your Moodle sysadmin.
*   **Scalability:** They can effortlessly handle bursts of tens of thousands of emails during critical periods like registration or assignment deadlines.
*   **Reduced Operational Overhead:** You don't manage mail queues, blacklists, or outbound firewall rules specific to SMTP on your Moodle server. This frees up engineering time, which is invaluable. For instance, the time I save not debugging email deliverability can be spent on more impactful projects, like building a [student performance dashboard with Grafana and Moodle data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/) or streamlining user management.
*   **Security:** Dedicated services often have robust security measures, reducing the risk of your Moodle server being compromised and used for spam.

The only "trade-off" is the recurring cost, which for high-volume environments, is a tiny fraction of the cost of engineering time, reputational damage, and lost educational opportunity from poor email deliverability. For small, internal-only Moodle instances with minimal email traffic, an on-premise SMTP relay might be justifiable, but I’d still err on the side of a hosted solution.

Ensuring your Moodle instance can reliably communicate with its users is paramount. By correctly configuring SMTP in `config.php` and meticulously setting up SPF and DKIM DNS records, you'll drastically improve email deliverability and avoid the frustrating "Moodle email not sending" issues I've battled countless times. This isn't just about technical configuration; it's about maintaining trust and ensuring the continuity of learning. Speaking of seamless operations, don't forget that effective user and course management also hinges on robust integration points; for example, understanding how to automate tasks like [automating Canvas LMS enrollments using Python and REST APIs](/blog/automating-canvas-lms-enrollments/) can save untold administrative hours, just as a well-planned [campus-wide Single Sign-On (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/) can significantly improve user experience and security across all your EdTech platforms.