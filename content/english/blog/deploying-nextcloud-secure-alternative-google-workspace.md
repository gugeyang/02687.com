---
title: "Deploying Nextcloud as a Secure Alternative to Google Workspace for Education"
date: "2024-05-14T10:00:00+08:00"
image: "images/blog/blog-post-5.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure & Cloud"]
tags: ["Nextcloud", "Ceph", "S3", "Kubernetes", "Data Sovereignty"]
description: "Architect a self-hosted Nextcloud cluster to replace Google Workspace for Education. Deep-dive into S3-compatible Ceph backend, background job tuning, and LDAP user provisioning for large university deployments."
---

For a decade, higher education enjoyed unlimited, free cloud storage from tech giants. It was an incredible era. Faculty stored massive research datasets, students hosted gigabytes of video projects, and IT departments offloaded their storage budgets entirely. Then, the policy changed. The "unlimited" era ended, and universities were suddenly faced with staggering cloud storage bills and aggressive quotas. 

At Global Tech University, we realized that relying entirely on third-party SaaS for our core institutional data was a strategic vulnerability. We needed a self-hosted, scalable, and secure file collaboration platform that kept our data on our own hardware, under our own jurisdiction. We chose Nextcloud. This post details our architectural approach to deploying Nextcloud for thousands of users, ensuring performance, data sovereignty, and compliance.


## The Architecture of Sovereignty

Deploying Nextcloud on a Raspberry Pi for your family is easy. Deploying it for a university requires serious infrastructure planning. 

Nextcloud is fundamentally a PHP application backed by a database and a massive file storage layer. To handle our load, we could not rely on a monolithic server. We adopted a distributed architecture:

1.  **The Application Tier**: A cluster of stateless Nginx/PHP-FPM nodes running in Kubernetes. They handle the web interface, API requests, and WebDAV sync operations.
2.  **The Database Tier**: A robust PostgreSQL cluster. (MySQL/MariaDB is popular in the Nextcloud ecosystem, but PostgreSQL handles heavy concurrency and complex locking much better in our experience).
3.  **The Storage Tier**: This is the heart of the system. We utilized our on-premise Ceph cluster. Rather than mounting network drives, we configured Nextcloud to use Ceph's S3-compatible API as its primary storage backend.

## Object Storage (S3) as the Primary Backend

By default, Nextcloud writes files directly to a local filesystem. In a clustered environment, you'd typically use NFS to share that filesystem across the web nodes. However, NFS becomes a severe bottleneck under heavy concurrent I/O (like 5,000 students syncing files at 9 AM).

Using an S3-compatible backend (like Ceph or MinIO) bypasses this. The web nodes don't need a shared POSIX filesystem. Nextcloud handles the file metadata in the database and streams the actual file blocks directly via HTTP to the object storage.

Here is the critical snippet from our `config.php` that enables S3 as the primary storage. This must be configured *before* the initial Nextcloud installation wizard is run.

```php
<?php
$CONFIG = array (
  // ... other configuration settings ...
  'objectstore' => array(
    'class' => '\\OC\\Files\\ObjectStore\\S3',
    'arguments' => array(
      'bucket' => 'nextcloud-data-bucket',
      'autocreate' => true,
      'key'    => 'YOUR_CEPH_ACCESS_KEY',
      'secret' => 'YOUR_CEPH_SECRET_KEY',
      'hostname' => 's3.internal.globaltech.edu',
      'port' => 443,
      'use_ssl' => true,
      'region' => 'us-east-1', # Required even for local S3 compatible storage
      // Path style is often required for local Ceph/MinIO deployments
      'use_path_style'=>true 
    ),
  ),
);
```

### The Performance Cost of Federation

We actively utilize Nextcloud's Federation feature, allowing researchers to share folders seamlessly with colleagues at other universities running their own Nextcloud instances. 

However, we discovered early on that Federation heavily impacts database performance. The system constantly polls remote instances to check for file updates. We had to aggressively tune our Redis cache (which Nextcloud uses for file locking and session management) and increase the PHP memory limits to prevent the background cron jobs from stalling.

## Securing the Perimeter

When you host your own data, you are fully responsible for the perimeter. We integrated Nextcloud directly with our campus Keycloak SSO (using SAML). This meant no passwords were ever stored in the Nextcloud database, and we could enforce our campus-wide Multi-Factor Authentication (MFA) policies.

Furthermore, because university research often involves sensitive intellectual property, we enabled Nextcloud's server-side encryption module. 

A critical architectural note regarding encryption: Nextcloud's default server-side encryption encrypts files using keys stored on the server itself. This protects data at rest if the physical hard drives are stolen, but it does *not* protect the data if the server is compromised (since the server has both the file and the key). 

For highly sensitive research, we require faculty to use Nextcloud's End-to-End Encryption (E2EE) plugin, where the encryption happens locally on the user's client device, and the server only ever sees ciphertext.

## Handling Background Jobs (Cron)

Nextcloud relies heavily on background tasks to generate thumbnails, index files for search, and clean up deleted files. 

If you leave the default setting ("AJAX"), Nextcloud attempts to run these jobs every time a user loads a page. In a university environment, this leads to horrific, unpredictable page load times.

You must switch to a system cron job. We created a dedicated Kubernetes cronjob that executes the PHP cron script every 5 minutes against a dedicated background worker pod, keeping the web-facing pods completely free to serve user requests.

```yaml
# Kubernetes CronJob for Nextcloud background tasks
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nextcloud-cron
spec:
  schedule: "*/5 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: nextcloud-cron-worker
            image: internal-registry.globaltech.edu/nextcloud-app:v27
            command: ["/usr/local/bin/php"]
            args: ["-f", "/var/www/html/cron.php"]
          restartPolicy: OnFailure
```

## The Migration Reality

Moving away from Big Tech's ecosystem is politically and technically challenging. Users love the seamless collaborative editing of Google Docs. To match this, we deployed Collabora Online alongside Nextcloud, allowing multi-user, real-time editing of Office documents directly in the browser.

Taking ownership of our data infrastructure required significant upfront engineering, but the long-term cost predictability and the absolute control over our digital sovereignty have proven to be the right strategic choice for our university.

