---
title: "Building a Serverless Plagiarism Detection Pipeline"
date: "2024-05-08T10:00:00+08:00"
image: "images/blog/blog-post-6.jpg"
author: "Alex Chen"
type: "post"
categories: ["Dev Log", "Data & AI"]
tags: ["Serverless", "AWS Lambda", "Python", "Plagiarism Detection", "MOSS"]
description: "Build a cost-effective, serverless plagiarism detection system using AWS Lambda, S3, and the MOSS engine. Designed to handle peak-semester submission bursts without dedicated server infrastructure, with Lambda cold-start mitigation strategies."
---

Academic integrity is a cornerstone of any educational institution. For years, Global Tech University relied on proprietary, expensive plagiarism detection suites tightly coupled with our LMS. However, as our computer science and engineering programs expanded, we realized traditional text-matching engines were failing at detecting code plagiarism and architectural diagram similarities. Furthermore, the licensing costs for scanning tens of thousands of submissions per semester were astronomical.

We decided to build our own serverless ingestion and analysis pipeline. By leveraging AWS Lambda, S3, and customized Python analysis engines, we created an event-driven architecture that scales down to zero cost during the summer and easily handles the bursty traffic of final exam week. This post outlines the architecture of our bespoke detection pipeline.


## The Event-Driven Architecture

The core philosophy of our system is asynchronous processing. When a student submits an assignment via Canvas or Moodle, we don't want the LMS to block while an analysis engine grinds through Megabytes of data.

Our pipeline looks like this:
1. **LMS Webhook**: The LMS triggers a webhook on a submission event.
2. **API Gateway**: An AWS API Gateway receives the webhook and drops the metadata into an SQS Queue.
3. **Ingestion Lambda**: A Lambda function reads the SQS message, downloads the file from the LMS via API, normalizes the format (e.g., extracting text from PDF, flattening code directories), and saves the raw asset to an S3 "Intake" bucket.
4. **Analysis Fan-out**: S3 triggers an SNS topic. Multiple Analysis Lambdas subscribe to this topic (one for text cosine similarity, one for MOSS code analysis, etc.).
5. **Aggregation**: The analysis engines write their similarity scores to a DynamoDB table.

### The Ingestion Function

Normalizing student submissions is notoriously difficult. Students upload `.docx`, `.pdf`, `.zip`, and occasionally bizarre formats. Here is a simplified version of our Python ingestion Lambda that handles PDF text extraction using `pdfplumber` before passing the sanitized text to S3.

```python
import boto3
import json
import requests
import pdfplumber
import io
import os

s3_client = boto3.client('s3')
BUCKET_NAME = os.environ['INTAKE_BUCKET']

def lambda_handler(event, context):
    for record in event['Records']:
        payload = json.loads(record['body'])
        submission_url = payload['file_url']
        student_id = payload['student_id']
        assignment_id = payload['assignment_id']
        
        # Download the file
        response = requests.get(submission_url, stream=True)
        response.raise_for_status()
        
        extracted_text = ""
        
        # Handle PDF extraction
        if 'application/pdf' in response.headers.get('Content-Type', ''):
            with pdfplumber.open(io.BytesIO(response.content)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        extracted_text += text + "\n"
        else:
            # Fallback for plain text
            extracted_text = response.text
            
        # Store normalized text in S3 to trigger analysis
        object_key = f"{assignment_id}/{student_id}.txt"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=object_key,
            Body=extracted_text.encode('utf-8')
        )
        
    return {"statusCode": 200, "body": "Ingestion successful"}
```

## The Code Plagiarism Engine (MOSS Integration)

While NLP-based text similarity is relatively straightforward (using TF-IDF or BERT embeddings), code similarity requires Abstract Syntax Tree (AST) analysis. We utilize Stanford's MOSS (Measure of Software Similarity) engine via a custom Lambda wrapper.

When a `.zip` file containing source code lands in our S3 intake bucket, it triggers our MOSS Lambda. This function unzips the payload, packages it alongside previous historical submissions from the same assignment, and submits the batch to the MOSS server.

```python
import mosspy
import boto3
import os

def submit_to_moss(assignment_dir, language="python"):
    userid = os.environ.get("MOSS_USER_ID")
    m = mosspy.Moss(userid, language)
    
    # Add historical base files (boilerplate code provided by instructor)
    m.addBaseFile(f"{assignment_dir}/template.py")
    
    # Add all student submissions
    m.addFilesByWildcard(f"{assignment_dir}/submissions/*.py")
    
    url = m.send()
    
    # Store the result URL in DynamoDB for instructor review
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('PlagiarismResults')
    table.put_item(
        Item={
            'AssignmentID': os.path.basename(assignment_dir),
            'MossReportUrl': url,
            'Timestamp': int(time.time())
        }
    )
    return url
```

## Scaling and Cost Management Trade-offs

The beauty of a serverless architecture in EdTech is the pricing model. University traffic is highly seasonal. During July, this pipeline costs us literally $0. During the week of final exams in December, when thousands of essays and code projects are submitted simultaneously, AWS provisions hundreds of concurrent Lambda executions to handle the queue.

However, there are architectural trade-offs:
1. **Cold Starts**: If a Lambda function hasn't been invoked recently, the first execution might take several seconds as AWS provisions the container. Because our process is entirely asynchronous via SQS and S3 events, this latency is invisible to the student and the LMS.
2. **Execution Time Limits**: AWS Lambda has a hard maximum execution time of 15 minutes. For massively complex NLP tasks on huge documents, we occasionally hit this limit. To mitigate this, we implemented chunking鈥攂reaking 100-page theses into 10-page chunks and running the analysis MapReduce style.

Building your own plagiarism detection pipeline isn't trivial. It requires maintaining complex ingestion logic and tuning similarity algorithms to avoid false positives. However, the capability to analyze custom programmatic formats, maintain strict data privacy internally, and eliminate per-user vendor licensing has proven to be a massive operational win for our engineering team.

## Integrating with Your LMS Submission Workflow

This pipeline is deliberately LMS-agnostic at the ingestion layer. Whether you are running a self-hosted Moodle instance or Canvas LMS, the webhook contract is identical 鈥?a JSON payload with a `file_url`, `student_id`, and `assignment_id`. For instructions on how to configure Moodle webhooks and integrate external event-driven pipelines, refer to our foundational guide on [Self-Hosting Educational Tools with Docker and HomeLab](/blog/self-hosting-educational-tools-docker-homelab/).

If your institution is also looking to capture *what* students learned (not just *whether* they submitted), consider pairing this pipeline with an xAPI event stream. Our article on [Moving from an LMS to a Learning Record Store (LRS) with xAPI](/blog/lms-to-lrs-with-xapi/) demonstrates how to route submission events alongside engagement signals into a unified data lake for longitudinal academic integrity analysis.



