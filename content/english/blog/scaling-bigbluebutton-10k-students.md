---
title: "Scaling BigBlueButton Video Conferencing for 10,000 Concurrent Students"
date: "2024-05-06T10:00:00+08:00"
image: "images/blog/blog-post-4.jpg"
author: "EdTech Architect"
type: "post"
categories: ["Infrastructure & Cloud"]
tags: ["BigBlueButton", "WebRTC", "Scalelite", "Load Balancing", "UDP"]
description: "Architecture guide for horizontally scaling BigBlueButton to 10,000 concurrent students using Scalelite as a load balancer. Covers TURN server configuration, UDP port tuning, and network topology decisions that prevent WebRTC session drops."
---

When the shift to remote learning happened, Global Tech University was caught off guard, like many institutions. We had a modest BigBlueButton (BBB) deployment running on a single bare-metal server, perfectly adequate for a few ad-hoc distance learning courses. Suddenly, we were asked to support 10,000 concurrent students across hundreds of virtual classrooms.

The immediate reaction from management was to throw money at a commercial vendor. But as an engineering team, we looked at the data sovereignty requirements, the integration depth needed for our custom LMS, and the prohibitive per-user licensing costs, and decided to scale our self-hosted BBB infrastructure instead. This post details the architecture, the load balancing strategy, and the harsh lessons learned scaling open-source WebRTC infrastructure.

<!-- ADSENSE_INSERT_HERE -->

## The Anatomy of a BigBlueButton Server

Before you can scale BBB, you need to understand what it actually is. It's not a single application; it's a complex orchestration of several specialized components:
* **FreeSWITCH**: Handles the audio bridging (SIP/WebRTC).
* **Kurento/mediasoup**: Handles the video SFU (Selective Forwarding Unit) routing.
* **Redis**: For pub/sub messaging between components.
* **Node.js (meteor)**: Drives the HTML5 client interface.
* **Nginx**: Reverse proxy and SSL termination.

A single robust server (e.g., 16 Cores, 32GB RAM) can typically handle about 150-200 concurrent users with moderate webcam usage before FreeSWITCH or the Node.js processes start dropping packets or locking up CPU cores. To support 10,000 users, we needed horizontal scaling. 

## The Scalelite Architecture

You cannot simply put a generic round-robin TCP load balancer (like HAProxy) in front of multiple BBB servers. Video conferencing requires sticky sessions and meeting-aware routing. If Professor Alice starts "Math 101" on Server A, all students joining "Math 101" must be routed to Server A. 

Enter **Scalelite**, the open-source load balancer specifically designed for BigBlueButton.

Scalelite acts as a proxy. When your LMS (like Moodle or Canvas) sends an API request to `create` a meeting, Scalelite intercepts it, checks the load across your pool of BBB workers, and assigns the meeting to the least loaded server. Subsequent `join` requests for that meeting are automatically routed to the correct worker.

### The Infrastructure Stack

Our final architecture looked like this:
1. **Frontend Proxy**: AWS Application Load Balancer (ALB) terminating TLS.
2. **Scalelite Cluster**: 2x VMs running Scalelite API and Nginx proxy in an active-active setup, backed by a managed PostgreSQL database and Redis cluster.
3. **Storage backend**: NFS share (AWS EFS) for storing shared meeting recordings, accessible by all workers.
4. **BBB Worker Pool**: 60x Compute-optimized instances (c5.4xlarge).

## Configuring the Worker Pool

Automating the deployment of the BBB workers was critical. You do not want to SSH into 60 servers to run installation scripts. We utilized Ansible to bootstrap bare Ubuntu images. 

Here is a snippet of our Ansible playbook for registering a new BBB worker with the Scalelite load balancer using the `scalelite-run` script:

```yaml
---
- name: Register BBB Worker to Scalelite
  hosts: bbb_workers
  become: yes
  vars:
    scalelite_url: "https://scalelite.globaltech.edu"
    scalelite_secret: "super_secret_scalelite_key"
  tasks:
    - name: Fetch BBB Server API Secret
      command: bbb-conf --secret | grep "Secret:" | awk '{print $2}'
      register: bbb_secret
      changed_when: false

    - name: Add server to Scalelite
      delegate_to: scalelite_master
      command: >
        docker exec scalelite-api bin/rake server:add
        url=https://{{ inventory_hostname }}/bigbluebutton/api
        secret={{ bbb_secret.stdout }}
      register: add_result

    - name: Enable server in Scalelite
      delegate_to: scalelite_master
      command: docker exec scalelite-api bin/rake server:enable url=https://{{ inventory_hostname }}/bigbluebutton/api
      when: "'Added' in add_result.stdout"
```

## The WebRTC UDP Problem

This is where most network engineers stumble. WebRTC video and audio (via FreeSWITCH and Kurento/mediasoup) do not traverse HTTP over TCP. They use UDP streams on ephemeral ports (typically 16384 - 32768). 

If you put your BBB servers behind a strict NAT or a standard corporate firewall without opening these UDP port ranges, the WebRTC ICE negotiation will fail. Users will connect to the HTML5 interface but will see an "ICE Error 1007" when trying to share their microphone or camera.

Furthermore, we deployed a **TURN/STUN server cluster** (using Coturn) to act as a relay for students trapped behind restrictive symmetric NATs (like typical hospital or corporate network firewalls). 

### Coturn Configuration Snippet

Your Coturn setup needs to be robust. Here is the core of our `turnserver.conf`:

```ini
listening-port=3478
tls-listening-port=5349

# Use a valid SSL certificate for WebRTC over TLS
cert=/etc/letsencrypt/live/turn.globaltech.edu/fullchain.pem
pkey=/etc/letsencrypt/live/turn.globaltech.edu/privkey.pem

# Authentication
use-auth-secret
static-auth-secret=generate_a_very_long_random_string_here
realm=turn.globaltech.edu

# Resource limits to prevent abuse
total-quota=100
bps-capacity=0
stale-nonce
no-loopback-peers
no-multicast-peers
```

You then configure the BBB workers via `bbb-conf --setturn` to point to this Coturn cluster using the `static-auth-secret`.

## Monitoring and the 'Thundering Herd'

When you have 10,000 students logging in at exactly 9:00 AM on a Monday, you experience the "Thundering Herd" problem. CPU spikes drastically not from video routing, but from the Node.js HTML5 client parsing simultaneous websocket connections and Redis pub/sub events.

We utilized Prometheus and Grafana, hooking into the `bbb-exporter` module, to monitor CPU steal time, active meetings, and video streams per server. 

**Pro-tip**: We modified the BBB HTML5 client configuration (`/etc/bigbluebutton/bbb-html5.yml`) to disable the default "join with microphone" prompt for classes over 50 users, defaulting them to "Listen Only". This massively reduced the immediate load on FreeSWITCH during class startup.

Scaling WebRTC is hard. It forces you to understand networking at the packet level. But by utilizing Scalelite and rigorous automation, achieving a massive, self-hosted concurrent conferencing system is entirely feasible.
