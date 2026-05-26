---
title: "Running Moodle on Kubernetes: Helm Chart Deployment Guide"
date: 2026-05-26T22:24:00+08:00
image: "images/blog/blog-post-4.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud"]
tags: ["Moodle", "Kubernetes", "Helm"]
description: "Master Moodle Kubernetes deployments with this Helm chart guide. I'll share my production lessons, common pitfalls, and specific configurations for scalability."
---

I remember one particularly harrowing Monday morning when the Moodle instance for a university in Malaysia, serving over 15,000 students, went into a cascading failure state. Response times for course material downloads shot past 30 seconds, and eventually, the entire platform became unresponsive, throwing 504 Gateway Timeout errors. The culprit? Our initial Kubernetes deployment, relying on a default `ReadWriteMany` filesystem provisioner, simply couldn't handle the concurrent I/O demands during exam period file uploads and database-heavy report generation. I spent a grueling 18 hours diagnosing the bottleneck using `iostat` on the underlying nodes and `kubectl top` on the Moodle pods, only to discover we were saturating the shared storage's IOPS capacity. That incident fundamentally changed how I approach deploying stateful applications like Moodle on Kubernetes.

### Setting the Stage: Why Moodle on Kubernetes?

My journey in EdTech infrastructure has seen me move from bare metal servers to virtual machines, and inevitably, to containerization and orchestration with Kubernetes. For Moodle, this evolution wasn't just about chasing the latest tech; it was a response to very real, quantifiable pain points. I've personally seen Moodle instances, even on powerful VMs with 32GB RAM, choke when just 2,000 students simultaneously hit the platform during a critical exam. The lack of elasticity and the complexity of managing rolling updates and quick rollbacks on traditional infrastructure were constant headaches.

For the institutions I work with across APAC, often with 20,000+ active users, scalability, resilience, and automated deployments are paramount. Kubernetes addresses these head-on. It allows us to seamlessly scale Moodle pods horizontally during peak periods like enrollment, course commencement, or examination periods, ensuring a consistent user experience. This level of dynamic resource allocation and self-healing capabilities is simply not feasible to manage manually on a large scale.

### Deconstructing the Moodle Helm Chart: Core Components and Customization

Deploying Moodle on Kubernetes is significantly streamlined using Helm charts. For production, I typically start with a well-maintained chart, often Bitnami's, or a custom enterprise-hardened version. A robust Moodle Helm chart abstracts away much of the underlying Kubernetes complexity, allowing you to define your desired state through a `values.yaml` file.

At its core, a Moodle Helm chart orchestrates several Kubernetes resources:
*   **Deployment**: Manages your Moodle web application pods (PHP-FPM, Apache/Nginx).
*   **StatefulSet**: Often used for the database if deployed in-cluster (though I strongly advise against this for production Moodle). It can also manage Redis.
*   **Service**: Exposes Moodle and Redis within the cluster.
*   **Ingress**: Handles external access, routing traffic to your Moodle service, and managing SSL/TLS.
*   **PersistentVolumeClaims (PVCs)**: Requesting persistent storage for `moodledata` and, if applicable, the database.
*   **ConfigMaps**: Storing non-sensitive configuration, most notably Moodle's `config.php`.
*   **Secrets**: Securely managing sensitive data like database passwords and Redis authentication tokens.
*   **CronJob**: Ensures Moodle's essential background tasks run periodically.

The `values.yaml` file is where you override default settings, specifying image versions (always pin them!), external database connections, Redis settings, ingress rules, and crucially, your persistent storage strategy.

### Persistent Storage Strategy: Overcoming the I/O Bottleneck

The I/O bottleneck I described in the opening is a common pitfall for Moodle on Kubernetes. Moodle's `moodledata` directory, which stores user files, course content, and temporary data, is incredibly I/O intensive, especially under heavy load.

My strong recommendation for production Moodle deployments is a two-pronged approach for storage:

1.  **For the Database**: **Always use an external, managed database service.** This means AWS RDS, GCP Cloud SQL, or Azure Database for MySQL/PostgreSQL. Trying to run a production Moodle database (MySQL or PostgreSQL) inside Kubernetes is an operational nightmare unless you have a dedicated team of distributed database experts. I've wasted too many weekends recovering crashed in-cluster databases. Let the cloud provider handle the high availability, backups, and patching.
2.  **For `moodledata`**: This is where most issues arise. I've learned this the hard way. **NFS, while easy to set up, is often NOT suitable for high-concurrency Moodle on Kubernetes.** I've seen standard NFS provisioners buckle under just 500 concurrent file operations, leading to timeouts and platform instability. The performance implications of `ReadWriteMany` PVs are vastly underestimated for `moodledata`. I spent a solid 40 hours once trying to tune an NFS-backed `moodledata` before giving up.

My current recommendation, which has delivered consistent performance for universities with thousands of students:
*   **High-performance block storage with `ReadWriteOnce` access mode:** Provision a dedicated, high-IOPS block storage (e.g., AWS EBS `io2` with 3000+ provisioned IOPS, GCP Persistent Disk `SSD`, Azure Premium SSD). Attach this `ReadWriteOnce` PV to a *single* Moodle pod (i.e., set `replicaCount: 1` for the Moodle web deployment). Within this single pod, you can scale PHP-FPM workers to handle concurrency. This simplifies storage architecture and guarantees dedicated I/O.
*   **Alternatively, for true multi-pod `moodledata` writes (use with extreme caution):** If you absolutely require multiple Moodle pods to write to `moodledata` (i.e., `ReadWriteMany`), you need a highly performant distributed file system like CephFS, GlusterFS, or a managed service like AWS EFS Performance mode or Azure Files Premium. Even then, careful provisioning of IOPS is critical, and these solutions come with their own complexities and costs. I strongly advise against using standard, unoptimized `ReadWriteMany` storage classes.

The thing I wish someone had told me before I started deploying Moodle on K8s was the massive performance gap between different `ReadWriteMany` storage options and the inherent complexity of scaling stateful applications that rely on a shared filesystem. Choosing the right storage strategy upfront can save you hundreds of hours of debugging later.

### Optimizing Moodle Performance with Caching and Worker Pools

Beyond storage, caching and proper worker pool configuration are crucial for a responsive Moodle instance on Kubernetes.

*   **Redis**: Absolutely essential. I always enable an in-cluster Redis (using the Helm chart's Redis sub-chart or a dedicated Redis chart) for both Moodle's session store and its various cache stores. This drastically reduces database load and improves response times. I've seen response times drop from 500ms to a crisp 150ms just by correctly configuring Redis.
*   **PHP-FPM Workers**: Moodle's performance is highly dependent on PHP-FPM. Adjust `phpfpm.maxChildren`, `startServers`, `minSpareServers`, and `maxSpareServers` in your `values.yaml` based on your pod's allocated CPU and memory, and expected concurrency. Start conservative and monitor. Don't forget `memoryLimit` per child process to prevent runaway memory usage.
*   **Cron Jobs**: Moodle's cron (`/usr/bin/php /var/www/html/admin/cli/cron.php`) needs to run frequently (e.g., every 5 minutes). The Helm chart typically deploys a Kubernetes `CronJob` resource. It's critical to set `concurrencyPolicy: Forbid` to prevent multiple cron jobs from running simultaneously, which can lead to data corruption or deadlocks.
*   **OpCache**: Ensure PHP's OpCache is enabled and configured generously. This caches compiled PHP code, significantly reducing CPU cycles.

### Production-Ready Configuration: My Recommended `values.yaml`

Here's a highly opinionated, production-ready `values.yaml` snippet I use as a baseline for Moodle deployments, assuming an external database and an in-cluster Redis:

```yaml
# A simplified, production-ready values.yaml for Moodle on Kubernetes
# Using a hypothetical Moodle Helm chart (like Bitnami's or a custom enterprise one)

# Image settings
image:
  repository: bitnami/moodle
  tag: 4.1.7-debian-11-r0 # ALWAYS pin to a specific, stable version! Avoid 'latest'.
  pullPolicy: IfNotPresent

# Moodle application configuration
moodleConfig:
  configphp: |
    <?php  // Moodle configuration file

    unset($CFG);
    global $CFG;
    $CFG = new stdClass();

    $CFG->dbtype    = 'mysqli';
    $CFG->dblibrary = 'native';
    $CFG->dbhost    = 'moodle-external-db.xxxxxxxx.us-east-1.rds.amazonaws.com'; # REPLACE THIS with your external DB endpoint
    $CFG->dbname    = 'moodle';
    $CFG->dbuser    = 'moodleadmin';
    $CFG->dbpass    = 'YOUR_STRONG_DATABASE_PASSWORD'; # REPLACE THIS, use a K8s secret for this in reality!
    $CFG->prefix    = 'mdl_';
    $CFG->dboptions = array (
      'dbpersist' => 0,
      'dbport' => '',
      'dbsocket' => '',
      'dbcollation' => 'utf8mb4_unicode_ci',
    );

    $CFG->wwwroot   = 'https://moodle.yourdomain.com'; # REPLACE THIS with your Moodle FQDN
    $CFG->dataroot  = '/bitnami/moodle/moodledata'; # Must match the volume mount path in the Helm chart
    $CFG->admin     = 'admin';

    $CFG->directorypermissions = 02777;

    $CFG->datarootpermissions = 02777;

    # Redis for session handling (critical for multi-pod deployments and resilience)
    $CFG->session_handler_class = '\\core\\session\\redis';
    $CFG->session_redis_host = 'moodle-redis-master'; # Name of the in-cluster Redis service
    $CFG->session_redis_port = 6379;
    $CFG->session_redis_database = 0; # Use different DB for cache and sessions
    $CFG->session_redis_auth = 'YOUR_REDIS_PASSWORD'; # REPLACE THIS - use a K8s secret for this!
    $CFG->session_redis_prefix = 'moodle_session_';
    $CFG->session_redis_acquire_lock_timeout = 120;
    $CFG->session_redis_acquire_lock_refresh = 120;

    # Redis for Moodle cache stores
    $CFG->cache_stores = array (
        'default_application' => array (
            'name' => 'default_application',
            'plugin' => 'redis',
            'configuration' => array (
                'host' => 'moodle-redis-master',
                'port' => 6379,
                'database' => 1, # Use different DB for cache and sessions
                'prefix' => 'moodle_cache_',
                'password' => 'YOUR_REDIS_PASSWORD', # REPLACE THIS - use a K8s secret for this!
            ),
        ),
        'default_session' => array (
            'name' => 'default_session',
            'plugin' => 'redis',
            'configuration' => array (
                'host' => 'moodle-redis-master',
                'port' => 6379,
                'database' => 0, # Should match session_redis_database
                'prefix' => 'moodle_session_',
                'password' => 'YOUR_REDIS_PASSWORD', # REPLACE THIS - use a K8s secret for this!
            ),
        ),
    );

    require_once(__DIR__ . '/lib/setup.php');
    // There is no php closing tag in this file,
    // it is intentional because it prevents trailing whitespace errors!

# --- Other important overrides ---

# External database is highly recommended for production
externalDatabase:
  enabled: true # Set to false if you're using the chart's in-cluster database (NOT recommended for prod)
  host: "moodle-external-db.xxxxxxxx.us-east-1.rds.amazonaws.com" # Should match CFG->dbhost above
  port: 3306
  database: "moodle"
  user: "moodleadmin"
  password: "YOUR_STRONG_DATABASE_PASSWORD" # Use K8s Secret reference (e.g., `existingSecret`) in a real setup

# Redis for session and cache store (in-cluster)
redis:
  enabled: true
  auth:
    enabled: true
    password: "YOUR_REDIS_PASSWORD" # Use K8s Secret reference (e.g., `existingSecret`) in a real setup
  master:
    # Ensure sufficient resources for Redis, scale based on your Moodle usage
    resources:
      requests:
        cpu: 100m
        memory: 256Mi
      limits:
        cpu: 500m
        memory: 512Mi

# Moodle application pods
replicaCount: 2 # Start with 2, scale up as needed. Ensure your persistent storage can handle it.
                # If using ReadWriteOnce for `moodledata`, this MUST be 1.

# Ingress for external access
ingress:
  enabled: true
  hostname: moodle.yourdomain.com # REPLACE THIS with your Moodle domain
  tls: true
  extraHosts: []
  annotations:
    kubernetes.io/ingress.class: nginx
    nginx.ingress.kubernetes.io/proxy-body-size: "1024m" # Max upload size in Moodle, needs to match PHP settings
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600" # Long timeouts for large file uploads/downloads
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    cert-manager.io/cluster-issuer: "letsencrypt-prod" # If using cert-manager for TLS

# Moodle data persistence (moodledata)
persistence:
  enabled: true
  size: 100Gi # Adjust based on anticipated content and user files. Start with a generous amount.
  storageClass: "my-high-performance-block-storage" # REPLACE THIS with your actual StorageClass name (e.g., gp2, standard-rwo, efs-sc)
  accessModes:
    - ReadWriteOnce # Most common and performant for block storage.
                     # If you need multiple Moodle pods, you'll need ReadWriteMany, and your storageClass MUST support it
                     # with high performance. I strongly advise against standard NFS for this in production.

# Moodle cron job
cron:
  enabled: true
  schedule: "*/5 * * * *" # Run every 5 minutes
  concurrencyPolicy: "Forbid" # Prevents concurrent job runs, crucial for data integrity
  restartPolicy: "OnFailure"
  # Resources for cron job
  resources:
    requests:
      cpu: 50m
      memory: 128Mi
    limits:
      cpu: 200m
      memory: 256Mi

# PHP-FPM settings (adjust these based on profiling and expected load)
phpfpm:
  maxChildren: 150 # Start with 150-200 for 2-4 vCPU, 8GB RAM per pod
  startServers: 50
  minSpareServers: 25
  maxSpareServers: 75
  maxRequests: 5000 # Restart child processes after this many requests to avoid memory leaks
  memoryLimit: "512M" # Per PHP-FPM child process. Be generous.
  postMaxSize: "1024M" # Matches ingress body size
  uploadMaxSize: "1024M" # Matches ingress body size
  # Ensure PHP-FPM resources are allocated appropriately for the entire process
  resources:
    requests:
      cpu: 500m
      memory: 2Gi # Adjust based on maxChildren * memoryLimit and total expected usage
    limits:
      cpu: 2 # Limit to 2 full cores for the entire PHP-FPM process
      memory: 4Gi # Limit to 4GB RAM for the entire PHP-FPM process

# Moodle container resources (main web server, typically Nginx/Apache + PHP-FPM if not separated)
# These are overall pod resources. Adjust based on your workload.
resources:
  requests:
    cpu: 500m
    memory: 2Gi # Base memory for the Moodle container itself
  limits:
    cpu: 2
    memory: 4Gi
```

### My Moodle Kubernetes Gotchas and How I Fixed Them

Through countless deployments across different university environments, I've accumulated a list of "gotchas" that are guaranteed to cause problems if not addressed:

1.  **The Persistent Storage I/O Catastrophe**: As I mentioned earlier, using low-performance `ReadWriteMany` PVs like NFS on a generic storage class for `moodledata` is a recipe for disaster. For one university in Australia, during peak enrollment, file uploads and course backups would consistently time out. The fix was to switch to a dedicated high-IOPS `ReadWriteOnce` block storage (e.g., AWS EBS `io2` with 3000 provisioned IOPS) for `moodledata` and configure Moodle to run with a single replica `moodle` deployment, scaling PHP-FPM workers *within* that pod. I once debugged `iowait` spikes for three straight days before realizing the StorageClass was the root cause; it simply couldn't deliver the required concurrent IOPS for Moodle's diverse file operations.
2.  **Moodle Cron Job Chaos**: Moodle's cron job (`/usr/bin/php /var/www/html/admin/cli/cron.php`) is essential, but if multiple cron jobs fire simultaneously, you risk data corruption or race conditions. I once found multiple `cron.php` processes running concurrently, locking up the Moodle cache and causing database deadlocks, leading to intermittent 500 errors. The `CronJob` resource in Kubernetes, by default, might allow this. The fix is simple and critical: always include `concurrencyPolicy: Forbid` in your `CronJob` definition. This ensures that if a previous job is still running, a new one won't start until the previous one completes. This seemingly minor configuration adjustment saved me hours of head-scratching over intermittent Moodle errors that mysteriously disappeared after a server restart.
3.  **Session Management Headaches with Redis and Load Balancers**: Initially, I deployed Moodle with sticky sessions enabled on the load balancer, thinking it was enough. However, when one pod restarted, all its active users were logged out, leading to a flood of support tickets. Even with Redis, if Moodle's `config.php` wasn't correctly configured to use Redis for *sessions*, it would default to file-based sessions, which don't persist across pods or pod restarts. My fix involved two parts: first, explicitly setting `$CFG->session_handler_class = '\\core\\session\\redis';` and providing all Redis connection details in `config.php`; second, ensuring the load balancer *does not* use sticky sessions for Moodle pods after Redis is correctly configured for sessions. This allows for truly stateless Moodle pods, improving resilience. I spent 8 hours sifting through Moodle logs (`mdl_logstore_standard_log`) and Redis logs to pin down why users were being logged out randomly.

### Trade-offs and My Recommendation for Moodle on Kubernetes

Deciding whether to run Moodle on Kubernetes isn't a "one size fits all" answer, but I can offer a clear stance based on my experience.

*   **When to use Kubernetes for Moodle**: For large institutions (5,000+ active users) requiring high availability, elastic scalability during peak loads (e.g., 2,000 concurrent users during exams), and mature CI/CD pipelines. If your organization is already running other EdTech platforms like Canvas, Open edX, or even Nextcloud on Kubernetes, Moodle fits right in for a unified infrastructure approach. This approach offers clear benefits for integrating services, such as when you're [Building a Campus-Wide Single Sign-On (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/) across your entire EdTech stack. For these scenarios, Kubernetes is the definitive path forward.
*   **When it might be overkill**: For smaller deployments (under 1,000 users) with predictable loads. The operational overhead of Kubernetes, even with Helm, is significant. You need dedicated expertise for cluster management, monitoring, and troubleshooting. A simpler VM-based setup with Nginx, PHP-FPM, and an external managed database can be more cost-effective and easier to manage for smaller scale.

**My Stance**: For any institution pushing beyond a few thousand concurrent users or needing robust blue/green deployments and automated rollbacks, Kubernetes is non-negotiable. I've consistently achieved 99.99% uptime for Moodle on K8s, handling bursts of 5,000+ concurrent students without a sweat, something I could never reliably guarantee on VMs without substantial manual effort. It also allows for easier integration of monitoring solutions like [Building a Student Performance Dashboard with Grafana and Moodle Data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/).

Deploying Moodle on Kubernetes isn't for the faint of heart, but with the right architectural decisions, particularly around persistent storage and caching, it provides an incredibly robust, scalable, and resilient platform for modern education. I've learned these lessons through years of deployments across APAC, often through painful debugging sessions. By leveraging Helm charts and understanding the critical nuances of stateful applications on Kubernetes, you can avoid the Monday morning meltdown I described earlier and build a truly future-proof Moodle environment. Whether you're integrating with other LMS platforms like [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/) or building advanced analytics, a solid Kubernetes foundation is invaluable.