---
title: "Speeding Up Moodle Globally with Cloudflare CDN Caching"
date: 2026-06-06T18:20:59+08:00
image: "images/blog/blog-post-4.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud"]
tags: ["Moodle"]
description: "Speed up Moodle globally with Cloudflare CDN caching. I share my battle-tested `moodle cloudflare` setup, page rules, and Workers, plus critical fixes for robust `moodle cdn setup`."
---

I remember a particularly painful deployment for a university in Sydney. They had a substantial student body in Southeast Asia, and their Moodle instance, hosted on a respectable 64GB RAM AWS EC2 instance in us-east-1, was crawling. Login times were acceptable, but loading course pages, fetching static assets like images and JavaScript, and even just navigating between activities often exceeded 5-7 seconds for users in Manila or Jakarta. We were seeing TTFB (Time To First Byte) values of 800ms to 1.2s consistently, even for cached static content. It was a classic case of geographical latency choking an otherwise well-provisioned Moodle server. My mission was clear: drastically reduce this latency and improve overall perceived performance, and I immediately knew a robust `moodle cdn setup` using Cloudflare was the answer.

### The Core Challenge: Moodle's Global Latency Problem and the Power of CDN

Moodle, at its heart, is a dynamic PHP application. While it has its own internal caching mechanisms (which are excellent for reducing database load and server processing), it doesn't inherently solve the problem of network latency for geographically dispersed users. Every request for a theme file, an image from `/pluginfile.php`, or a JavaScript library still has to travel from the user's browser all the way to your origin server and back. For our Sydney client, this round trip to Manila added ~150-200ms *per request*. Imagine a Moodle page with 50 static assets; that's 7.5 to 10 seconds of pure network overhead just waiting for packets.

This is precisely where a Content Delivery Network (CDN) like Cloudflare becomes indispensable for a `moodle cloudflare` integration. Cloudflare positions copies of your static content on edge servers globally. When a student in Jakarta requests a Moodle image, Cloudflare serves it from its nearest data center – perhaps Singapore or Kuala Lumpur – rather than forcing the request to traverse the entire Pacific. This dramatically reduces latency and bandwidth usage on your origin server, translating to faster load times and a smoother user experience. I've personally seen page load times drop from 7 seconds to under 1.5 seconds for remote users after a proper Cloudflare integration.

### Architecting Moodle for Cloudflare Caching: Core Settings and Best Practices

Before you even touch Cloudflare, ensure your Moodle instance is configured to play nice with a CDN. This isn't just about speed; it's about correctness. I spent 8 hours once debugging broken file paths because I overlooked a critical setting.

1.  **Enable Slash Arguments:** Go to `Site administration > Server > HTTP`. Ensure `Use slash arguments` is checked. This ensures Moodle generates clean URLs for file serving (e.g., `/pluginfile.php/1/mod_resource/content/0/document.pdf` instead of `pluginfile.php?file=/1/mod_resource/content/0/document.pdf`). Cloudflare caches these cleaner URLs more effectively.
2.  **Optimize Moodle's Internal Caching:** While Cloudflare handles external caching, ensure Moodle's internal caching is robust. I always recommend Redis or Memcached for the Moodle cache store for any production environment with over 1,000 active users. Set `$CFG->cachejs = true;` in `config.php` to combine and minify JavaScript files, further reducing the number of requests.
3.  **DNS Configuration:** The simplest and most robust approach is to proxy your Moodle domain (e.g., `lms.university.edu`) through Cloudflare. In your Cloudflare DNS settings, create an `A` record pointing to your origin server's IP address (or a `CNAME` if using another service like AWS ELB) and ensure the orange cloud is enabled. This directs all traffic through Cloudflare's network.

You also need to tell Moodle that it's behind a reverse proxy. Add these lines to your `config.php` *before* the `require_once(...)` line:

```php
// Cloudflare CDN / Reverse Proxy settings
$CFG->reverseproxy = true;
$CFG->reverseproxyremoteuser = false; // Set to true only if Cloudflare passes a remote user header
$CFG->sslproxy = true; // Use this if Cloudflare handles SSL for your domain
$CFG->cdnurl = 'https://lms.university.edu'; // Important: Use your actual Moodle domain
$CFG->wwwroot = 'https://lms.university.edu'; // Ensure this matches your CDN URL if behind Cloudflare
```

The `$CFG->cdnurl` and `$CFG->wwwroot` are critical. While `$CFG->cdnurl` might seem redundant if your entire site is proxied, it’s good practice. For a very specific setup where you might only CDN static content via a subdomain (e.g., `cdn.lms.university.edu`), `$CFG->cdnurl` would point there, while `$CFG->wwwroot` would be your main domain. For a full proxy via Cloudflare, they often align.

### Implementing Cloudflare Page Rules and Worker Scripts for Granular Moodle Caching

This is where the real magic happens for `moodle cloudflare` optimization. Moodle is highly dynamic, so you can't just `Cache Everything` indiscriminately. Aggressive caching can break logins, assignment submissions, and other interactive elements. My approach involves using Page Rules for broad strokes and Cloudflare Workers for fine-grained control.

**Cloudflare Page Rules (Priority-based, top-down):**

I typically set up 3-5 page rules for Moodle:

1.  **Bypass Cache for Admin/Login/Dynamic Pages (Highest Priority):**
    *   URL: `*lms.university.edu*/(login|admin|my|message|user|report|grade|calendar|mod/quiz/attempt.php)*`
    *   Settings: `Cache Level: Bypass`
    *   *Why:* These are user-specific or administrative areas that must *never* be cached. Caching them leads to authentication issues and stale data.

2.  **Cache Everything for Static Assets (Medium-High Priority):**
    *   URL: `*lms.university.edu*/(pluginfile.php|theme|pix|local|mod|course|moodle/plugin|repository|lib/yui|question|blocks|filter|lang|index).php*`
    *   Settings:
        *   `Cache Level: Cache Everything`
        *   `Edge Cache TTL: 7 days` (or 30 days for very static content)
        *   `Browser Cache TTL: 1 day`
    *   *Why:* This targets the bulk of Moodle's static content. `/pluginfile.php` is particularly important as it serves user-uploaded files and course resources. I've set Edge Cache TTL to 7 days – it’s a good balance; too long and you risk serving stale content if an asset changes rapidly, too short and you lose the CDN benefit.

3.  **Default Caching for Public-Facing Content (Lower Priority):**
    *   URL: `*lms.university.edu/*`
    *   Settings:
        *   `Cache Level: Standard` (or `No Query String` if you want to be more specific)
        *   `Edge Cache TTL: 2 hours`
        *   `Browser Cache TTL: 30 minutes`
    *   *Why:* This catches everything else. `Standard` will respect your origin's `Cache-Control` headers. If your Moodle installation serves content with `Cache-Control: public, max-age=3600`, Cloudflare will respect that. For any pages without explicit headers, it defaults to the `Edge Cache TTL`.

**Cloudflare Workers for Advanced Scenarios:**

Sometimes, Page Rules aren't enough. For instance, you might want to cache certain content for non-logged-in users but bypass the cache entirely for authenticated users. This is where Workers shine.

I often use a Worker script to inspect cookies. Moodle sets a `MoodleSession` cookie (or `MOODLEID_` followed by a hash) when a user logs in. We can use this to bypass caching dynamically.

```javascript
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url)

  // Define paths that are ALWAYS bypassed (e.g., login, admin, messaging)
  const bypassPaths = [
    '/login/',
    '/admin/',
    '/my/',
    '/message/',
    '/user/',
    '/report/',
    '/grade/',
    '/calendar/',
    '/mod/quiz/attempt.php'
  ];

  // Check if the request path matches any of the bypass paths
  if (bypassPaths.some(path => url.pathname.startsWith(path))) {
    return fetch(request); // Bypass cache and fetch directly from origin
  }

  // Identify Moodle session cookies (adjust MOODLEID_ to your Moodle's specific cookie prefix if different)
  const cookies = request.headers.get('Cookie') || '';
  const isMoodleLoggedIn = /(MoodleSession|MOODLEID_)/.test(cookies);

  // If a Moodle session cookie is present, bypass cache for most pages
  // EXCEPT specific static asset types that are safe to cache even for logged-in users.
  const staticAssetExtensions = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.eot', '.pdf', '.zip', '.mp4', '.webm'];
  const isStaticAsset = staticAssetExtensions.some(ext => url.pathname.endsWith(ext)) || url.pathname.startsWith('/pluginfile.php');

  if (isMoodleLoggedIn && !isStaticAsset) {
    // For logged-in users, bypass cache for dynamic pages, but still cache static assets.
    // We can also add a cache-control header to prevent browser caching for dynamic content.
    const response = await fetch(request);
    let newHeaders = new Headers(response.headers);
    newHeaders.set('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
    newHeaders.set('Pragma', 'no-cache');
    newHeaders.set('Expires', '0');
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers: newHeaders });
  }

  // Otherwise, attempt to serve from cache or fetch from origin
  // Cloudflare's default caching behavior (based on Page Rules and origin headers) will apply
  return fetch(request);
}
```
This Worker provides an extra layer of intelligent caching that Page Rules alone can't quite replicate. It essentially allows authenticated users to still hit Cloudflare's cache for truly static assets (like `/pluginfile.php` PDFs or theme images), while ensuring dynamic, personalized content is always fresh from the origin.

### Debugging and Monitoring Your Moodle Cloudflare CDN Setup

Implementing a CDN isn't a "set it and forget it" task. You need to verify its effectiveness and diagnose issues. This is where my team often leverages tools like Grafana, combined with Cloudflare's analytics, to build comprehensive dashboards. [Building a Student Performance Dashboard with Grafana and Moodle Data](/blog/building-a-student-performance-dashboard-with-grafana-data/) taught us the power of centralized monitoring.

1.  **Verify Caching:**
    *   **Browser Developer Tools:** Open your browser's developer console (F12). Go to the Network tab. Load Moodle pages. Look at the response headers for static assets. You should see `cf-cache-status: HIT` or `DYNAMIC` (if not cached), and `cf-ray` which is useful for Cloudflare support. `Cache-Control` headers from your origin should also be visible.
    *   **`curl -I`:** From your terminal, use `curl -I https://lms.university.edu/theme/yourtheme/pix/some_image.png`. Check for `cf-cache-status` and `Age` headers. An `Age` header indicates how long the asset has been in Cloudflare's cache.
2.  **Cloudflare Analytics:** Cloudflare provides excellent dashboards for bandwidth, cached requests, uncached requests, and attack surface. Regularly review these to ensure your cache hit ratio is high (aim for 70%+ for static assets).
3.  **Origin Server Logs:** Keep an eye on your Moodle server's access logs and CPU/memory usage. You should see a significant *reduction* in direct requests for static files hitting your origin, leading to lower load.
4.  **Performance Testing:** Use tools like GTmetrix, WebPageTest.org, or Lighthouse to measure page load times from various global locations *before and after* implementing Cloudflare. Look specifically at TTFB and asset loading times.

### Gotchas: Real-World Moodle Cloudflare Problems and Their Fixes

I've encountered my share of frustrating issues when integrating Moodle with Cloudflare. Here are a few common ones and their solutions:

1.  **Broken `pluginfile.php` Links for Specific Activities:**
    *   **Problem:** After enabling Cloudflare, some course files served via `/pluginfile.php` were showing as broken links or throwing 404s, even with the Page Rule set. I saw this particularly with custom SCORM packages or H5P content where the `pluginfile.php` URL often included complex query parameters.
    *   **Diagnosis:** The issue was often that `Cache Level: Cache Everything` wasn't actually caching URLs with complex query strings, or Moodle was generating slightly different URLs for the same asset. More critically, sometimes Moodle's `slasharguments` setting wasn't correctly applied *everywhere*, leading to `?file=` syntax that was harder for Cloudflare to normalize.
    *   **Fix:**
        1.  Ensure `Use slash arguments` is absolutely checked in Moodle's HTTP settings and `lib/setup.php` allows it.
        2.  For the `pluginfile.php` Page Rule, set `Cache Level: Cache Everything` and crucially, enable `Query String: Standard` or even `Ignore Query String` *if you are certain* query parameters don't alter the file content (use with extreme caution!). For Moodle, usually `Standard` is safer.
        3.  The main fix often involved adding an explicit `Bypass Cache on Cookie: MoodleSession` to the Page Rule that covers `pluginfile.php`. This ensures that if a user has an active session, Cloudflare checks with the origin, preventing potential access issues for restricted files. It's a trade-off but ensures correctness.

2.  **Redirect Loops or Infinite Refresh on Login:**
    *   **Problem:** Users would try to log in, but instead of reaching their dashboard, they'd get stuck in a redirect loop or the login page would refresh endlessly.
    *   **Diagnosis:** This almost always indicates that Cloudflare is serving a cached version of a page that requires authentication or session state, or the `sslproxy` setting in `config.php` is incorrect. Cloudflare might also be incorrectly trying to redirect HTTP to HTTPS, while your Moodle thinks it's already on HTTPS. I once spent 4 hours going through Nginx logs, Moodle logs, and Cloudflare access logs before realizing the `sslproxy` setting was missing.
    *   **Fix:**
        1.  Verify `sslproxy` is set to `true` in `config.php` if Cloudflare handles SSL.
        2.  Ensure your `wwwroot` in `config.php` starts with `https://`.
        3.  Critically, *double-check* that your `Bypass Cache` Page Rule for login paths (e.g., `*lms.university.edu*/login*`) is active and correctly configured as the *highest priority*.
        4.  Ensure you don't have conflicting Cloudflare rules like "Always Use HTTPS" alongside a Moodle server that's not ready to handle HTTPS internally.

3.  **Broken JavaScript or CSS After Clearing Moodle Cache:**
    *   **Problem:** After I cleared Moodle's internal cache (e.g., `php admin/cli/purge_caches.php`), users would report broken layouts or JavaScript errors.
    *   **Diagnosis:** Moodle generates new versions of combined JavaScript/CSS files after a cache purge, often with unique filenames or timestamps. Cloudflare's edge servers, however, were still holding onto the *old* cached versions with their extended `Edge Cache TTL`.
    *   **Fix:** After purging Moodle's internal caches, you *must* also manually purge Cloudflare's cache for the relevant assets. You can do this granularly via the Cloudflare dashboard (e.g., purge `*lms.university.edu*/theme/*`) or, even better, purge *everything*. I usually trigger a full cache purge on Cloudflare immediately after any significant Moodle cache clearing or update. This is one thing I wish someone had told me early on: Moodle's cache purge doesn't magically tell Cloudflare to purge!

### Weighing the Benefits and Caveats: When to Cache Moodle with Cloudflare

Adopting a `moodle cloudflare` setup is a powerful move, but it's not without its considerations.

**Benefits:**

*   **Dramatic Performance Improvement:** As I mentioned, for global users, I've seen TTFB drop from 1.2s to 50ms and full page load times from 7s to 1.5s.
*   **Reduced Origin Load:** Your Moodle server offloads a significant portion of static asset requests to Cloudflare, freeing up CPU and network resources for dynamic content and database operations. This allows your Moodle server to handle more concurrent users without scaling vertically as aggressively.
*   **Enhanced Security:** Cloudflare provides WAF (Web Application Firewall) capabilities, DDoS protection, and SSL termination, bolstering your Moodle's security posture. I always recommend enabling the WAF for any public-facing LMS.
*   **Cost Savings:** By offloading bandwidth, you might reduce your hosting costs, especially if you're on a pay-per-GB plan.

**Caveats & Recommendations:**

*   **Complexity:** The initial setup, especially with Page Rules and potentially Workers, adds a layer of configuration complexity. It requires a good understanding of Moodle's asset serving and Cloudflare's caching logic.
*   **Stale Content Risk:** The biggest risk is serving stale content. My strong stance here is to *prioritize correctness over aggressive caching*. Always err on the side of caution for dynamic, user-specific, or administrative content. For static assets like images, CSS, and JS, a 7-day edge cache TTL is generally safe.
*   **SSL Configuration:** Ensure your Moodle server handles SSL certificates correctly, or Cloudflare manages it End-to-End. I recommend `Full (strict)` SSL mode in Cloudflare for maximum security.
*   **Authentication:** This is the trickiest part. Any page with a Moodle session cookie or requiring authentication *must* bypass caching. This is why the Page Rules and Worker script focusing on `MoodleSession` cookies are non-negotiable for a robust `moodle cdn setup`.
*   **Monitoring is Key:** Without proper monitoring of cache hit ratios, origin load, and user-perceived performance, you're flying blind.

My clear recommendation: If you have a Moodle instance serving users across multiple geographic regions, or if your server is struggling under the load of static asset requests, implementing Cloudflare CDN caching is a mandatory step. The performance gains and reduced load on your origin server are invaluable. Just ensure you allocate sufficient time for proper configuration and thorough testing.

Optimizing Moodle performance is just one facet of managing a robust EdTech ecosystem. The principles of automation and data-driven insights apply across various LMS platforms and supporting services. For those managing other systems, consider how you might apply similar strategies, perhaps looking into solutions like [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/) to streamline operational tasks. Furthermore, securing these environments is paramount, often achieved through centralized identity management; exploring options like [Building a Campus-Wide Single Sign-On (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/) can significantly enhance user experience and administrative control.