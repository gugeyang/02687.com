---
title: "Building a Campus-Wide Single Sign-On (SSO) with Keycloak"
date: "2024-05-13T10:00:00+08:00"
image: "images/blog/blog-post-4.jpg"
author: "Alex Chen"
type: "post"
categories: ["Security", "Infrastructure and Cloud"]
tags: ["Keycloak", "SSO", "IAM", "Nginx", "Active Directory"]
description: "Step-by-step guide to deploying Keycloak as a campus-wide SSO provider. Covers Active Directory federation, Nginx reverse proxy configuration, and debugging SAML attribute mapping in production."
---

Five years ago, a typical student at Global Tech University had to memorize separate passwords for the Learning Management System, the library portal, the email client, and the campus Wi-Fi. This fragmented identity landscape was a security nightmare. Students reused weak passwords, the helpdesk spent 40% of their time handling password reset tickets, and when a student graduated, offboarding their access across 15 disjointed systems took days.

We needed a unified Identity and Access Management (IAM) solution. While commercial offerings are robust, their pricing models鈥攐ften per-user鈥攁re ruinous for large educational institutions with hundreds of thousands of active and alumni accounts. We turned to Keycloak, an open-source IAM tool sponsored by Red Hat, to build our campus-wide Single Sign-On (SSO) infrastructure.


## The Architectural Vision

Our goal was simple in theory but complex in execution: create a single pane of glass for identity. We wanted an architecture where our legacy Active Directory (AD) remained the ultimate source of truth for passwords, but no application would ever speak directly to AD again.

Instead, applications (LMS, portals, APIs) would redirect to Keycloak. Keycloak would authenticate the user, validate their multi-factor authentication (MFA) token, and then issue a secure JWT (JSON Web Token) to the requesting application using standard protocols like OIDC (OpenID Connect) or SAML 2.0.

## Federation vs. Synchronization

The first major architectural hurdle was how to integrate Keycloak with our existing, massive Active Directory forest.

We had two options: Sync all users into Keycloak's internal database, or use User Federation. Syncing is generally discouraged for large deployments because it duplicates data and risks latency issues. 

We chose User Federation. Keycloak acts as a proxy. When a user enters their credentials, Keycloak securely binds to the AD server, verifies the password, and instantly retrieves the user's groups and attributes on the fly. This guarantees that if a user is disabled in AD, their access across all connected applications is revoked instantaneously.

## Customizing the Authentication Flow

Higher education requires complex authentication logic. For example, faculty members need mandatory MFA to access the grading system from off-campus, but students only need simple username/password authentication when logging into the library portal from the campus IP range.

Keycloak handles this brilliantly through its Authentication Flows. Instead of hardcoding logic, you configure a pipeline of execution steps.

We built a custom flow that evaluates the context of the login request. It checks the origin IP address and the requested application. If the request originates from a known internal subnet, it bypasses the MFA step. If it originates externally, it forces the user to provide a Time-based One-Time Password (TOTP) or a WebAuthn security key.

Here is a look at a crucial piece of configuration for Keycloak when deploying it behind an Nginx reverse proxy. Misconfiguring headers here is the #1 reason SSO deployments fail, leading to infinite redirect loops.

```nginx
# Nginx Reverse Proxy Configuration for Keycloak
server {
    listen 443 ssl http2;
    server_name sso.globaltech.edu;

    ssl_certificate /etc/letsencrypt/live/sso.globaltech.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sso.globaltech.edu/privkey.pem;

    location / {
        proxy_pass http://keycloak-backend:8080;
        
        # Crucial headers for Keycloak to understand it's behind a proxy
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port 443;
        
        # Increase buffer sizes for large JWT headers
        proxy_buffer_size   128k;
        proxy_buffers   4 256k;
        proxy_busy_buffers_size   256k;
    }
}
```

*Note: For this to work, you must also set the `PROXY_ADDRESS_FORWARDING=true` environment variable when starting the Keycloak Docker container, otherwise it will try to issue tokens with HTTP instead of HTTPS URLs.*

## Mapping Claims and Roles

One of the most tedious parts of integrating legacy applications is ensuring they get the user data in the exact format they expect. The LMS might expect the student's department to be under an attribute named `department_code`, while the library system expects `deptId`.

We used Keycloak's Protocol Mappers to solve this cleanly. We pull the raw `department` attribute from LDAP/AD, and then map it dynamically into the SAML assertion or OIDC token based on which client application is requesting it. The applications don't need to change their code; Keycloak translates the identity data into the specific dialect each app requires.

## The High Availability Nightmare

SSO is the definition of a single point of failure. If Keycloak goes down, the entire university goes dark. Nobody can teach, learn, or work.

Deploying Keycloak in a clustered, high-availability (HA) environment is notoriously tricky due to its reliance on Infinispan (a distributed cache). If the network partitions, you can end up in a split-brain scenario where different nodes issue conflicting session states.

We deployed Keycloak on a 3-node Kubernetes cluster. We had to carefully tune the Infinispan `JGroups` configuration, utilizing JDBC_PING (using our highly available PostgreSQL database for node discovery) rather than relying on multicast, which is often blocked in modern cloud environments. 

## The Reality of Migration

Rolling out SSO isn't just an IT project; it's an organizational change management challenge. We couldn't flip a switch overnight. We spent a year running in a hybrid state, slowly migrating applications one by one, managing extensive communications, and training the helpdesk to handle MFA lockouts.

However, the payoff is immense. Our security posture has drastically improved, onboarding new cloud services takes hours instead of weeks, and the student experience is finally cohesive. Open-source tools like Keycloak prove that you don't need a massive enterprise budget to build enterprise-grade identity infrastructure.

