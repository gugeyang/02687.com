---
title: "Building a Student Performance Dashboard with Grafana and Moodle Data"
date: 2026-05-23T21:26:47+08:00
image: "images/blog/blog-post-2.jpg"
author: "Alex Chen"
type: "post"
categories: ["Data and AI"]
tags: ["Moodle", "Grafana", "LMS", "Performance"]
description: "Learn to build a robust Moodle Grafana dashboard for student performance analytics. I share exact SQL, setup pitfalls, and real-world solutions for LMS data visualization."
---

I remember it vividly: a Tuesday morning, 9 AM, peak login hours for our university’s Moodle instance. The server load spiked from a healthy 0.8 to 15.0 in under three minutes, causing a cascade of HTTP 500 errors and completely freezing the interface for over 2,000 active students. My immediate thought was a DDoS, but a quick `htop` showed a single MySQL process chewing up 100% of a 16-core CPU, running a grotesquely complex query for a "student progress report." It was a prime example of why directly querying an OLTP (Online Transaction Processing) system like Moodle for intensive OLAP (Online Analytical Processing) `lms analytics` is a recipe for disaster. This incident became the catalyst for us to build a dedicated `moodle grafana dashboard` for student performance, offloading analytics from our production LMS.

## The Quest for Real-time Student Performance Insights: Why Moodle Alone Isn't Enough

Moodle is an incredible LMS, powering education for millions globally. I’ve personally deployed it for universities ranging from 5,000 to 50,000 students. Its built-in reporting, however, is often rudimentary or resource-intensive. For administrators, faculty, and even students, getting a comprehensive, at-a-glance view of performance, engagement trends, and risk factors is critical. We needed a `moodle grafana dashboard` that could answer questions like:

*   Which courses have the lowest average quiz scores this week?
*   How many students haven't accessed a specific course module in the last 7 days?
*   What's the grade distribution for a particular assignment across all cohorts?
*   Are there specific activities where a large percentage of students are failing to complete?

The Moodle database schema is complex, designed for transactional integrity, not analytical speed. Running multi-table JOINs on `mdl_user`, `mdl_course`, `mdl_grade_grades`, `mdl_quiz_attempts`, and `mdl_logstore_standard_log` directly on the Moodle production database inevitably leads to performance bottlenecks and, as I experienced, potential outages. This is where Grafana, coupled with an optimized data source, truly shines for `lms analytics`.

## Architecting the Data Pipeline: From Moodle MySQL to a Purpose-Built Analytics Store

The first crucial decision was where to store the data for Grafana. My recommendation: **never query your Moodle production database directly for complex Grafana dashboards** that could impact system performance during peak hours. Instead, establish an ETL (Extract, Transform, Load) pipeline.

Our architecture for the `moodle grafana dashboard` looked like this:

1.  **Moodle Production Database (MySQL):** The source of truth.
2.  **ETL Script (Python/Bash):** A daily (or even hourly for critical data) job extracts relevant data.
3.  **Analytics Database (PostgreSQL/ClickHouse):** A separate, optimized database for analytical queries. We opted for PostgreSQL 14 for its robust JSONB support and excellent performance with indexed analytical queries. For truly massive datasets, I’d lean towards ClickHouse.
4.  **Grafana Server:** Connects to the Analytics Database.

The ETL script is paramount. I've spent countless hours tuning these. Initially, I tried a simple `mysqldump` followed by an import, which was too slow for incremental updates. My recommended approach is to use a Python script with `pymysql` and `psycopg2` libraries to fetch data incrementally, using `timestamp` fields or logical primary key ranges to identify changes.

Here’s a simplified Python snippet for an incremental extract of user data:

```python
import pymysql
import psycopg2
from datetime import datetime, timedelta

def etl_users(moodle_db_config, analytics_db_config):
    """
    Extracts new/updated user data from Moodle and loads into Analytics DB.
    """
    moodle_conn = pymysql.connect(**moodle_db_config)
    analytics_conn = psycopg2.connect(**analytics_db_config)
    
    try:
        with analytics_conn.cursor() as analytics_cursor:
            # Get the latest 'timemodified' from the analytics DB
            analytics_cursor.execute("SELECT MAX(timemodified) FROM users_dim;")
            last_modified_in_analytics = analytics_cursor.fetchone()[0]
            if last_modified_in_analytics is None:
                last_modified_in_analytics = datetime(2000, 1, 1) # Start from scratch

        with moodle_conn.cursor(pymysql.cursors.DictCursor) as moodle_cursor:
            # Fetch users modified since last ETL run
            moodle_cursor.execute("""
                SELECT id, username, email, firstname, lastname, city, country, lastlogin, timemodified
                FROM mdl_user
                WHERE timemodified > %s;
            """, (last_modified_in_analytics.timestamp(),))
            
            users_to_upsert = moodle_cursor.fetchall()
            
            with analytics_conn.cursor() as analytics_cursor:
                for user in users_to_upsert:
                    # UPSERT logic for PostgreSQL
                    analytics_cursor.execute("""
                        INSERT INTO users_dim (id, username, email, firstname, lastname, city, country, lastlogin, timemodified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s))
                        ON CONFLICT (id) DO UPDATE SET
                            username = EXCLUDED.username,
                            email = EXCLUDED.email,
                            firstname = EXCLUDED.firstname,
                            lastname = EXCLUDED.lastname,
                            city = EXCLUDED.city,
                            country = EXCLUDED.country,
                            lastlogin = EXCLUDED.lastlogin,
                            timemodified = EXCLUDED.timemodified;
                    """, (
                        user['id'], user['username'], user['email'], user['firstname'], 
                        user['lastname'], user['city'], user['country'], 
                        user['lastlogin'], user['timemodified']
                    ))
        analytics_conn.commit()
        print(f"ETL completed for {len(users_to_upsert)} users.")
            
    except Exception as e:
        analytics_conn.rollback()
        print(f"ETL failed: {e}")
    finally:
        moodle_conn.close()
        analytics_conn.close()

# Example usage (replace with actual config)
# moodle_config = {'host': 'moodle-db', 'user': 'moodleuser', 'password': 'moodlepassword', 'database': 'moodle'}
# analytics_config = {'host': 'analytics-db', 'user': 'analyticsuser', 'password': 'analyticspassword', 'database': 'analytics'}
# etl_users(moodle_config, analytics_config)
```
This script handles the extraction and then an upsert into a simplified `users_dim` table in our analytics database. You'd build similar scripts for courses, enrolments, grades, and activity logs. I once spent 18 hours debugging a `timemodified` field discrepancy where Moodle's `mdl_user.timemodified` was not correctly indexing updates to enrolments or course completions, leading to stale data. The fix involved adding specific checks against `mdl_user_enrolments.timemodified` and `mdl_course_modules_completion.timecompleted` in subsequent ETL stages.

## Crafting Actionable Metrics: Essential SQL for Moodle Grafana Dashboard Panels

Once your data is in a performant analytics database, constructing the `moodle grafana dashboard` panels becomes a SQL exercise. Here's a powerful query for a Grafana panel that displays the average grade percentage for a specific course, broken down by enrollment cohort. This is incredibly useful for faculty to quickly spot discrepancies between groups.

```sql
SELECT
    COALESCE(c.shortname, 'N/A') AS course_name,
    COALESCE(g.itemname, 'Overall Course Grade') AS grade_item_name,
    EXTRACT(YEAR FROM TO_TIMESTAMP(ue.timestart)) AS enrollment_year,
    FLOOR(AVG(gg.finalgrade / g.grademax * 100)) AS average_grade_percentage
FROM
    mdl_grade_grades gg
JOIN
    mdl_grade_items g ON gg.itemid = g.id
JOIN
    mdl_user u ON gg.userid = u.id
JOIN
    mdl_course c ON g.courseid = c.id
JOIN
    mdl_user_enrolments ue ON u.id = ue.userid AND c.id = ue.courseid -- Ensure enrolment links to THIS course
WHERE
    g.itemtype = 'course' -- Focus on overall course grade for now
    AND gg.finalgrade IS NOT NULL
    AND g.grademax > 0
    AND c.id = ${course_id} -- Grafana variable for course selection
GROUP BY
    c.shortname,
    g.itemname,
    EXTRACT(YEAR FROM TO_TIMESTAMP(ue.timestart))
ORDER BY
    enrollment_year ASC;
```
This query uses several Moodle tables: `mdl_grade_grades` (actual grades), `mdl_grade_items` (grade item definitions), `mdl_user` (user details), `mdl_course` (course details), and crucially, `mdl_user_enrolments` (to determine cohort based on enrollment time). The `COALESCE` handles cases where a name might be missing, and `${course_id}` is a Grafana variable, allowing users to select a course dynamically. This provides precise `lms analytics` for faculty.

## Operationalizing Grafana: Datasources, Dashboards, and Alerting for LMS Analytics

Once your data pipeline is solid, setting up Grafana is straightforward.

1.  **Datasource Configuration:** Add your PostgreSQL analytics database as a new datasource in Grafana. Make sure network connectivity and credentials are correct. I always specify a read-only user for Grafana for security best practices.
2.  **Dashboard Creation:** Start with basic panels: total active students, course completion rates, average grades, and activity engagement over time. Build drill-down dashboards that allow faculty to go from a high-level course overview to individual student performance.
3.  **Variables:** Utilize Grafana's template variables extensively. For example, a "Course" variable (`SELECT id, fullname FROM courses_dim ORDER BY fullname`) allows users to select courses from a dropdown, dynamically updating all panels.
4.  **Alerting:** This is a game-changer. I configure alerts for scenarios like:
    *   "Course X average grade drops below 60% in the last 24 hours."
    *   "Less than 50% of students in Course Y have completed Module Z after its deadline."
    *   "Number of student logins drops by 20% compared to the previous week."
    These alerts directly empower faculty to intervene proactively, transforming raw `lms analytics` into actionable insights.

## Real-World Gotchas and Hard-Learned Lessons in Moodle Grafana Integrations

My journey building `moodle grafana dashboard` solutions across multiple institutions has been full of unexpected turns. Here are a few "gotchas" that cost me considerable time:

1.  **Moodle's Grade Schema Ambiguity:** The `mdl_grade_grades` table only tells you a student's grade for an item. It doesn't inherently tell you if they *completed* an activity, merely if a grade was recorded. For true activity completion, you *must* join with `mdl_course_modules_completion` and filter `completionstate` (0=NOT_STARTED, 1=STARTED, 2=COMPLETED). I once created a dashboard showing 100% completion for an assignment, only to realize it was counting students who had a grade of '0' but hadn't actually attempted it. The fix was to specifically filter `mdl_grade_grades.finalgrade IS NOT NULL` and ensure `mdl_course_modules_completion.completionstate = 2` for completion metrics.
2.  **Timezone Hell:** Moodle stores `timemodified`, `timecreated`, and `lastlogin` as UNIX timestamps (UTC). If your analytics database or Grafana server is configured with a local timezone and you don't explicitly convert, your daily/weekly charts will be off by several hours, splitting days incorrectly. Always convert timestamps to your desired local timezone using `FROM_UNIXTIME(timestamp_field, '%Y-%m-%d %H:%i:%s')` in MySQL or `TO_TIMESTAMP(timestamp_field) AT TIME ZONE 'Asia/Singapore'` in PostgreSQL queries to maintain consistency. I remember a faculty complaining that "students disappear from the dashboard at 4 PM every day," which was just the UTC day roll-over.
3.  **Moodle's `mdl_logstore_standard_log` Table Size:** This table records *every single interaction* in Moodle. For a university with 20,000 students, it can grow to hundreds of gigabytes within a year. Directly syncing this entire table for `lms analytics` in your ETL can be prohibitively slow and storage-intensive. My initial attempt to sync it hourly nearly crashed our ETL server. **What I wish someone told me earlier:** Only extract specific log types or aggregates you actually need. For example, filter by `eventname` like `/course/viewed`, `/mod/quiz/attempted`, `/mod/assign/submitted` to reduce data volume by 90% while retaining critical engagement metrics. For more sophisticated tracking and richer insights, sometimes you need to integrate Moodle with other data sources, building a more holistic view, much like we explore when [Building the Next-Gen Knowledge Graph for Modern Universities](/blog/building-next-gen-knowledge-graph/).

## Choosing Your Analytics Path: Direct Queries vs. Data Warehousing for Moodle Data

This is where I take a firm stance. While it's *possible* to point Grafana directly at your Moodle MySQL database, **I strongly recommend against it for any production-level, multi-user analytics dashboards.**

*   **Direct Query Pros:** Simpler initial setup, real-time data (if you don't care about a few seconds lag).
*   **Direct Query Cons:**
    *   **Performance Impact:** Complex queries can degrade Moodle's performance significantly, impacting student and faculty experience. I've personally seen a single mis-optimized query bring a Moodle server to its knees.
    *   **Schema Rigidity:** Moodle's schema is not optimized for reporting. You'll write incredibly complex, slow queries.
    *   **Data Latency vs. Freshness:** "Real-time" often isn't needed for performance analytics. Daily or hourly updates are sufficient for trends and interventions.
    *   **Security Risk:** Giving Grafana direct access to your primary Moodle DB increases the attack surface.

**My recommendation is unequivocal:** Invest in an intermediate analytics database (PostgreSQL, ClickHouse, or even a simpler data mart with daily refreshes) and a robust ETL pipeline. This architecture provides:

1.  **Performance Isolation:** Your analytics workload won't affect Moodle's usability.
2.  **Optimized Schema:** You can denormalize data into simpler, flatter tables, making queries orders of magnitude faster (e.g., a `student_grades` table that combines student, course, and grade item info).
3.  **Data Enrichment:** You can easily integrate data from other systems (e.g., student information systems, HR systems) into your analytics database, providing a richer, consolidated view. This approach complements initiatives like [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/), where data consistency and availability are key to automation.
4.  **Scalability:** Analytics databases are designed for read-heavy workloads and can scale independently of your Moodle instance.

The upfront effort of setting up an ETL and an analytics database pays dividends almost immediately in stability, performance, and the sheer power of the insights you can gain from your `moodle grafana dashboard`.

Building a robust student performance dashboard with Grafana and Moodle data is more than just connecting tools; it's about architecting a sustainable data pipeline that empowers educators without compromising the core LMS. From my experience managing LMS infrastructure across APAC, this approach has proven its worth time and again, transforming raw data into actionable intelligence. The journey to meaningful `lms analytics` might seem daunting, but with a clear strategy and an understanding of Moodle's data nuances, the rewards for student success and institutional effectiveness are immense.