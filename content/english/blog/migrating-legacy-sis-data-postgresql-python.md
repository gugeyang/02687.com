---
title: "Migrating Legacy SIS Data to PostgreSQL using Python"
date: "2024-05-12T10:00:00+08:00"
image: "images/blog/blog-post-3.jpg"
author: "Alex Chen"
type: "post"
categories: ["Data and AI", "Dev Log"]
tags: ["PostgreSQL", "Python", "ETL", "Legacy SIS", "Data Migration"]
description: "Hard-won lessons from migrating a 25-year-old Student Information System to PostgreSQL using Python streaming ETL. Covers dirty data remediation, encoding normalization, and resumable batch processing for multi-million row datasets."
---

If you work in higher education IT long enough, you eventually have to slay the dragon: The Legacy Student Information System (SIS). At Global Tech University, our core SIS was a 25-year-old monolith running on an archaic proprietary database. It held the academic records, enrollment histories, and financial data for hundreds of thousands of alumni. It was slow, impossible to integrate with modern cloud applications, and the vendor support contract was bleeding our budget dry.

We made the strategic decision to migrate the core data warehouse to PostgreSQL. This wasn't just a database swap; it was an archaeological expedition. We discovered undocumented tables, bizarre encoding schemes, and business logic hardcoded into triggers written in the late 90s. This post outlines how we built a robust, repeatable ETL (Extract, Transform, Load) pipeline using Python to safely migrate millions of critical academic records.


## The Data Extraction Challenge

The legacy system didn't have a modern API. Our only extraction method was dumping raw, flat CSV files overnight via a scheduled job. These files were massive, often poorly formatted, and frequently contained delimiters (like commas and pipes) hidden within the data fields themselves (e.g., a student address like "Apartment A, Building 4").

Attempting to process a 15GB CSV file entirely in memory using standard Python tools would instantly crash our worker nodes. We needed a streaming approach.

We utilized Python's built-in `csv` module coupled with generator functions to read the data chunk by chunk. This allowed us to keep our memory footprint under 200MB, regardless of the file size.

## Data Cleansing and Transformation

Legacy data is universally dirty data. We found "NULL" represented as empty strings, literal string "NULL", "-99", and occasionally "N/A". Dates were formatted in a half-dozen different ways depending on which administrative clerk entered them 15 years ago.

We built a transformation layer using Python. For heavy data manipulation, `pandas` is popular, but given our streaming requirement, we opted for pure Python dictionaries and custom validation functions. It was slightly more verbose but vastly more memory efficient and easier to debug row-by-row failures.

Here is an example of our core processing loop, highlighting the validation and chunking strategy.

```python
import csv
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

def parse_legacy_date(date_str):
    if not date_str or date_str.strip() in ['NULL', 'N/A']:
        return None
    try:
        # The legacy system inexplicably used MM-DD-YYYY for some records
        # and YYYY/MM/DD for others.
        if '-' in date_str:
            return datetime.strptime(date_str, '%m-%d-%Y').date()
        else:
            return datetime.strptime(date_str, '%Y/%m/%d').date()
    except ValueError:
        return None # Log this anomaly for manual review

def process_and_load(file_path, db_connection):
    insert_query = """
        INSERT INTO core_students (student_id, first_name, last_name, enrollment_date, status)
        VALUES %s
        ON CONFLICT (student_id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            status = EXCLUDED.status;
    """
    
    batch = []
    batch_size = 5000 # Tune based on network/DB latency

    with open(file_path, mode='r', encoding='ISO-8859-1') as file:
        reader = csv.DictReader(file, delimiter='|') # Legacy export used pipes
        
        with db_connection.cursor() as cursor:
            for row in reader:
                # 1. Extraction & Cleaning
                student_id = row['STU_ID'].strip()
                fname = row['F_NAME'].strip().title()
                lname = row['L_NAME'].strip().title()
                raw_date = row['ENR_DT']
                status_code = row['STAT'].strip().upper()
                
                parsed_date = parse_legacy_date(raw_date)
                
                # 2. Build the tuple for insertion
                batch.append((student_id, fname, lname, parsed_date, status_code))
                
                # 3. Batch Loading
                if len(batch) >= batch_size:
                    execute_values(cursor, insert_query, batch)
                    db_connection.commit() # Commit the batch
                    batch.clear()
            
            # Insert any remaining records
            if batch:
                execute_values(cursor, insert_query, batch)
                db_connection.commit()
```

### The Encoding Nightmare

You might notice `encoding='ISO-8859-1'` in the code above. That took us a week to figure out. The old system pre-dated modern UTF-8 standards. When we initially imported the data, student names with accents or non-standard characters were completely garbled in PostgreSQL. Identifying the correct legacy code page and enforcing a strict conversion to UTF-8 at the Python layer was a critical turning point in the project.

## High-Performance Loading with PostgreSQL

Loading millions of rows row-by-row (using standard `INSERT` statements) is painfully slow. PostgreSQL shines when you use bulk operations.

In the code snippet, we use `psycopg2.extras.execute_values`. This function is dramatically faster than looping over `cursor.execute` because it bundles the data into a single, massive SQL statement. 

Furthermore, during the initial historical load, we temporarily disabled indexes and foreign key constraints on the target PostgreSQL tables. Updating indexes on every insert adds immense overhead. By dropping the indexes, performing the bulk load, and then recreating the indexes at the end, we cut our total migration time from 18 hours down to just 2.5 hours.

## Idempotency and The UPSERT

A migration script will inevitably fail midway through—a network blip, a corrupted disk, or an unhandled data edge case will crash the process. If your script isn't idempotent, you have to wipe the database and start over.

We heavily leveraged PostgreSQL's `ON CONFLICT DO UPDATE` clause (the "upsert"). This meant we could run the migration script repeatedly against the same data without fear of creating duplicate records or causing primary key violations. It gracefully updates existing records and inserts new ones.

## The Payoff

Moving away from the legacy proprietary database was painful, but the resulting PostgreSQL data warehouse changed how our entire university operates. We finally had standard SQL access to our core data. Within a month, we had connected Metabase and Grafana directly to the new warehouse, providing administration with real-time analytics they previously waited weeks for. The Python ETL pipeline now runs nightly, ensuring the new cloud systems stay perfectly synchronized with the (stubbornly surviving) on-premise legacy apps.

