---
title: "Containerizing Auto-Grading Pipelines with Docker"
date: "2024-05-10T10:00:00+08:00"
image: "images/blog/blog-post-1.jpg"
author: "EdTech Architect"
type: "post"
categories: ["Dev Log", "Infrastructure & Cloud"]
tags: ["Docker", "Auto-Grading", "Python", "Celery", "Kubernetes"]
description: "How to containerize untrusted student code submissions for automated grading using Docker and Celery. Includes resource-limit configurations, seccomp profiles, and a Kubernetes CronJob deployment pattern."
---

A few years ago, our computer science faculty at Global Tech University hit a wall. Managing student submissions for programming assignments had devolved into a chaotic mess of zip files, broken local environments, and missing dependencies. Instructors were spending more time trying to compile code on their Macs than actually reviewing the algorithms. The traditional "it works on my machine" excuse was rampant. We needed a reproducible, isolated, and highly scalable way to run untrusted student code without compromising our internal network.

The obvious solution was Docker. But integrating Docker into an automated grading pipeline for thousands of students isn't as simple as writing a quick `Dockerfile`. You run into severe security implications, resource exhaustion problems, and orchestration headaches. This post details how we built a robust, containerized auto-grading pipeline from scratch, the architecture decisions we made, and the pitfalls we encountered along the way.

<!-- ADSENSE_INSERT_HERE -->

## The Core Architectural Problem

When a student submits code via our Learning Management System (LMS), we essentially receive an untrusted payload. Executing this payload directly on a server is a recipe for disaster. We've seen it all—infinite loops that eat up CPU, fork bombs designed to crash the host, and subtle attempts to access the local file system.

The pipeline needed to accomplish three things:
1. **Isolation**: Every submission must run in an airtight environment.
2. **Resource Constraints**: CPU time and memory must be strictly capped.
3. **Determinism**: The environment must be identical for every student, every single time.

We decided to build a worker queue architecture. The LMS fires a webhook to a central API, which then pushes a grading job to a Redis queue. Celery workers pick up these jobs, spin up ephemeral Docker containers with the student's code, run the unit tests, collect the results, and tear down the container.

## Building the Ephemeral Container Environment

The most critical part of this system is the Docker execution layer. You can't just use `docker run` indiscriminately. We rely heavily on the Docker Python SDK to manage the container lifecycle programmatically.

Here is an example of the Python worker code that handles the execution. Notice how we enforce strict resource limits and network isolation.

```python
import docker
import tarfile
import io
import time

def run_untrusted_code(submission_path, language, timeout_seconds=10):
    client = docker.from_env()
    
    # We maintain strict base images for different languages (e.g., python:3.9-slim)
    image_tag = f"grader-base-{language}:latest"
    
    try:
        # Spin up a container with no network access, limited memory, and restricted CPU.
        container = client.containers.run(
            image_tag,
            command="sleep 3600", # Keep it alive temporarily
            detach=True,
            network_mode='none', # Crucial: No internet or local network access
            mem_limit='256m',
            memswap_limit='256m',
            cpu_period=100000,
            cpu_quota=50000,     # Limit to 50% of a single CPU core
            read_only=True,      # Root filesystem is read-only
            tmpfs={'/tmp': ''},  # Allow writes only to /tmp
            security_opt=['no-new-privileges']
        )
        
        # ... logic to copy the submission into the container ...
        
        # Execute the test script
        exit_code, output = container.exec_run(
            cmd="pytest /tmp/student_code.py --json-report",
            workdir="/tmp",
            user="nobody" # Never run untrusted code as root
        )
        
        return {
            'status': 'success' if exit_code == 0 else 'failed',
            'output': output.decode('utf-8')
        }
        
    except docker.errors.ContainerError as e:
        return {'status': 'error', 'message': str(e)}
    finally:
        # Always tear down, even if things crash
        if 'container' in locals():
            container.remove(force=True)
```

### The Pitfall of File System Permissions

One of the earliest bugs we encountered was related to file permissions. When you copy a file into a Docker container, it often retains the UID/GID of the host environment. Because we run the execution as the `nobody` user for security, the test runner would frequently fail to read the student's submission.

We had to implement an intermediate step during the Docker image build process to establish an explicit `runner` user with a known UID, and ensure that the payload injection script chowns the directory before dropping privileges.

## Handling the Concurrency Nightmare

During midterms, the volume of submissions spikes dramatically. A simple queue architecture can easily buckle if not tuned correctly. Initially, our Celery workers were spinning up too many containers concurrently on a single node, leading to massive context-switching overhead and disk I/O bottlenecks.

To solve this, we moved to a dedicated Kubernetes cluster specifically for the grading nodes. However, instead of using Kubernetes Jobs (which have too much overhead for 5-second grading scripts), we kept the Celery workers running as DaemonSets. Each worker limits its own concurrency using Python's `multiprocessing.Semaphore`.

We also discovered that repeatedly pulling Docker images during spikes was killing our network bandwidth. We configured the DaemonSets to aggressively cache the base grading images locally on the node level.

```yaml
# A snippet of our DaemonSet configuration for grading workers
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: grading-worker-node
spec:
  selector:
    matchLabels:
      app: grader
  template:
    metadata:
      labels:
        app: grader
    spec:
      containers:
      - name: celery-worker
        image: internal-registry.globaltech.edu/grader-worker:v2.1
        env:
        - name: MAX_CONCURRENT_CONTAINERS
          value: "4" # Tuned to host CPU count
        volumeMounts:
        - name: docker-sock
          mountPath: /var/run/docker.sock
      volumes:
      - name: docker-sock
        hostPath:
          path: /var/run/docker.sock
```

*Note: Mounting the docker socket inside a pod is highly dangerous if the pod itself is exposed. Our grading workers run on an isolated subnet with strict network policies to mitigate this risk.*

## Securing the Output

Students are remarkably creative when it comes to trying to hack grading systems. We had students writing code to read the grading unit test files and outputting the expected results without actually solving the problem. 

To mitigate this, the unit tests and the student code are never in the same directory. The tests are baked into the base image in a read-only directory accessible only by root. The `nobody` user executes a test runner script (also owned by root, but executable) that dynamically imports the student's module from the `/tmp` directory.

Furthermore, we heavily sanitize the output. If a student's code infinite-loops and prints gibberish, it can bloat the Celery backend (Redis) and crash the LMS when it tries to render a 50MB string. We enforce a strict 10KB cap on captured `stdout`/`stderr`.

## Final Thoughts

Building a custom, containerized auto-grading system was significantly more work than buying an off-the-shelf solution. However, the flexibility we gained was unmatched. We can now support any programming language just by writing a new `Dockerfile`, and we have total control over the data privacy of our students' work.

If you are going down this path, prioritize security and resource limits from day one. Do not trust the payload, do not run as root, and always assume a student will find a way to write a fork bomb in a language you didn't even know supported them.