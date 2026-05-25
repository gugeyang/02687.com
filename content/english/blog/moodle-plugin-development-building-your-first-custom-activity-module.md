---
title: "Moodle Plugin Development: Building Your First Custom Activity Module"
date: 2026-05-25T23:44:35+08:00
image: "images/blog/blog-post-3.jpg"
author: "Alex Chen"
type: "post"
categories: ["Dev Log"]
tags: ["Moodle"]
description: "Learn Moodle plugin development by building a custom activity module from scratch. I'll share my real-world failures and provide technical guidance for Moodle custom modules."
---

I remember a particularly frustrating week while deploying Moodle for a large university in Kuala Lumpur. They had a critical requirement for a peer-review activity module, far more nuanced than what core Moodle or existing community plugins offered. It needed specific rubric weighting, anonymous submission *and* grading, and a complex workflow for re-submission based on initial peer feedback. We initially tried to hack an existing assignment module, but after 40 hours of trying to force a square peg into a round hole, it became clear: we needed a custom activity. The existing solutions were either too generic, couldn't handle the anonymous workflow, or would buckle under the weight of 10,000+ student submissions, leading to page load times exceeding 30 seconds for graders. This technical pain point drove us directly into custom Moodle plugin development, and it's a journey I'm here to guide you through, sharing my hard-won lessons.

### Setting Up Your Moodle Development Environment for Plugin Sanity

Before you write a single line of Moodle-specific code, you need a robust, isolated development environment. I've seen too many developers try to build on a live server or an under-resourced local machine, leading to hours of debugging misconfigurations rather than actual code. My recommendation for local Moodle development is unequivocally Docker-Compose or Lando. These tools provide consistent environments that mirror production more closely than a raw LAMP stack.

Start by ensuring your `config.php` has the right debugging settings enabled. This is non-negotiable.
```php
@error_reporting(E_ALL | E_STRICT); // Show all errors
@ini_set('display_errors', '1');    // Display errors directly
$CFG->debug = (E_ALL | E_STRICT);   // More verbose Moodle debugging
$CFG->debugdisplay = 1;             // Display debug messages
$CFG->developerdebuging = true;     // Show developer-level messages
$CFG->dblogerror = true;            // Log database errors
$CFG->allowthemechangeonurl = true; // Useful for quick theme switching
```
This configuration, especially `debug` and `developerdebuging`, will save you weeks of your life. I once spent 8 hours debugging a cryptic "Fatal error: Allowed memory size of 268435456 bytes exhausted" message. The real issue, buried deep in a database transaction, was an incorrectly formed SQL query that Moodle's ORM was struggling to parse. With `developerdebuging` set to `true`, the error trace was explicit, pointing directly to the SQL syntax issue. Without it, the memory exhaustion error was a red herring. Always set up Xdebug too; stepping through Moodle's core code is often the only way to truly understand its intricate APIs, especially when dealing with complex data structures.

### Deconstructing Moodle's Activity Module Structure

A custom activity module lives within the `mod/` directory of your Moodle installation. Let's call our hypothetical module `mod_peerreview`. The directory structure will look something like this:

```
mod/
└── peerreview/
    ├── db/
    │   ├── access.php        // Defines capabilities
    │   ├── install.xml       // Initial database schema
    │   └── upgrade.php       // Schema upgrades and data migrations
    ├── lang/
    │   └── en/
    │       └── peerreview.php // Language strings
    ├── classes/              // PSR-4 autoloaded classes (modern Moodle)
    │   └── output/
    │       └── renderer.php
    ├── backup/               // Backup/restore handlers
    ├── lib.php               // Core module functions
    ├── version.php           // Module metadata (version, release)
    ├── view.php              // Main activity display page
    ├── edit.php              // Page for adding/updating the activity (form handling)
    ├── mod_form.php          // Defines the activity's settings form
    └── index.php             // List all activities of this type in a course
```

The `version.php` file is critical. It defines your module's version, which Moodle uses to manage upgrades. If you modify your database schema (e.g., `install.xml` or `upgrade.php`), you *must* increment the `$module->version` number. If you forget this, Moodle's `admin/cli/upgrade.php` or `admin/index.php` (via the UI) won't trigger your database upgrade scripts, leading to "Table not found" errors or silent data corruption. I once spent 3 hours debugging why my new database column wasn't appearing, only to realize I'd forgotten to bump the version number from `2023010100` to `2023010101`.

### Architecting the Database Schema and Data Access Layer

Your custom activity module will almost certainly need its own database tables. Moodle uses an XML-based Data Definition Language (DDL) for schema definition in `db/install.xml` and `db/upgrade.php`. This approach ensures Moodle handles database compatibility across different systems (MySQL, PostgreSQL, MSSQL).

Here’s a simplified `db/install.xml` for our `mod_peerreview` module, defining a table to store submissions:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<XMLDB PATH="mod/peerreview/db" VERSION="2023112800" COMMENT="Peer Review module schema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:noNamespaceSchemaLocation="../../../lib/xmldb/xmldb.xsd"
>
    <TABLES>
        <TABLE NAME="peerreview_submissions" COMMENT="Stores peer review submissions">
            <FIELDS>
                <FIELD NAME="id" TYPE="int" LENGTH="10" NOTNULL="true" UNSIGNED="true" SEQUENCE="true"/>
                <FIELD NAME="peerreviewid" TYPE="int" LENGTH="10" NOTNULL="true" UNSIGNED="true" DEFAULT="0" SEQUENCE="false" COMMENT="Foreign key to course_modules table"/>
                <FIELD NAME="userid" TYPE="int" LENGTH="10" NOTNULL="true" UNSIGNED="true" DEFAULT="0" SEQUENCE="false" COMMENT="User who made the submission"/>
                <FIELD NAME="timecreated" TYPE="int" LENGTH="10" NOTNULL="true" UNSIGNED="true" DEFAULT="0" SEQUENCE="false"/>
                <FIELD NAME="timemodified" TYPE="int" LENGTH="10" NOTNULL="true" UNSIGNED="true" DEFAULT="0" SEQUENCE="false"/>
                <FIELD NAME="status" TYPE="int" LENGTH="2" NOTNULL="true" UNSIGNED="true" DEFAULT="0" SEQUENCE="false" COMMENT="0=draft, 1=submitted, 2=graded"/>
                <FIELD NAME="content" TYPE="text" NOTNULL="true" SEQUENCE="false" COMMENT="Submission content"/>
            </FIELDS>
            <KEYS>
                <KEY NAME="primary" TYPE="primary" FIELDS="id"/>
                <KEY NAME="peerreviewid" TYPE="foreign" FIELDS="peerreviewid" TARGET="course_modules" TARGETFIELDS="id"/>
                <KEY NAME="userid" TYPE="foreign" FIELDS="userid" TARGET="user" TARGETFIELDS="id"/>
            </KEYS>
            <INDEXES>
                <INDEX NAME="peerreviewid_idx" UNIQUE="false" FIELDS="peerreviewid"/>
                <INDEX NAME="userid_idx" UNIQUE="false" FIELDS="userid"/>
            </INDEXES>
        </TABLE>
        <!-- Add more tables here as needed, e.g., peerreview_reviews, peerreview_rubric_criteria -->
    </TABLES>
</XMLDB>
```
Once you have `install.xml` in place, visit `admin/index.php` or run `admin/cli/upgrade.php` from the command line to create the table. If you modify your schema later, you'll create a new `db/upgrade.php` file and increment `version.php`.

For interacting with this data, Moodle provides a powerful database API (`$DB` global object). Avoid raw SQL queries unless absolutely necessary. Stick to Moodle's DML functions: `$DB->insert_record()`, `$DB->update_record()`, `$DB->get_record()`, `$DB->get_records()`, `$DB->count_records()`, etc. These functions handle sanitization and abstraction across different database types.

When your custom activity generates rich student interaction data, you'll inevitably want to visualize it. I've spent countless hours building dashboards for universities, and understanding Moodle's data structures is paramount, especially when you're looking to feed that data into external analytics platforms. It's exactly this kind of integration that allows you to start [Building a Student Performance Dashboard with Grafana and Moodle Data](/blog/building-a-student-performance-dashboard-with-grafana-and-moodle-data/) for deeper insights.

### Crafting the User Interface and Business Logic

The user interface of your activity module is built using Moodle's Form API (`mod_form.php`), Moodle's `output_factory` for templating, and standard PHP pages (`view.php`, `edit.php`).

*   **`mod_form.php`**: This file defines the form that administrators use to add or edit an instance of your activity in a course. It uses Moodle's `moodle_form` class. You define fields (text areas, checkboxes, dropdowns) here, including validation rules.
*   **`lib.php`**: This is the heart of your module, containing all core functions. This includes `peerreview_add_instance()`, `peerreview_update_instance()`, `peerreview_delete_instance()`, and crucially, `peerreview_supports()` which tells Moodle what features your module supports (e.g., grades, completion). You'll also define functions for retrieving submissions, calculating grades, or handling any custom business logic.
*   **`view.php`**: This is the main page that students and teachers will see when they click on your activity in a course. Here, you'll retrieve data from your custom tables, check user capabilities (`require_capability()`), and render the content using Moodle's `output_factory` and templates.
*   **`edit.php`**: Handles the form submission from `mod_form.php` and processes the data to either create a new activity instance or update an existing one.

Always use Moodle's capabilities system for access control. Define your capabilities in `db/access.php` (e.g., `mod/peerreview:addinstance`, `mod/peerreview:submit`, `mod/peerreview:grade`). Then, in your PHP code, check these capabilities: `require_capability('mod/peerreview:submit', $context);` before allowing a user to perform an action. Neglecting capabilities can open severe security vulnerabilities.

### Gotchas: The Pitfalls I Stepped In (So You Don't Have To)

1.  **Moodle Caching (MUC is a double-edged sword):** Moodle's Universal Cache (MUC) system is powerful for performance, but it *will* bite you during development. If you change a language string in `lang/en/peerreview.php`, a template file in `templates/`, or even certain PHP classes, Moodle often serves a cached version. I've spent 4 hours wondering why my `get_string('mysuperstring', 'peerreview')` wasn't updating on the UI, despite verifying the file was saved. The fix? Always purge caches (`admin/cli/purge_caches.php` or `Site administration -> Development -> Purge all caches`) after making changes to `lang` files, `templates`, or sometimes even `lib.php` for good measure.
2.  **Contexts and Capabilities:** Moodle's security and data access rely heavily on "contexts." Every item (site, category, course, module, block, user) has a context. When checking capabilities or retrieving localized strings, you *must* pass the correct context object. `get_context_instance(CONTEXT_MODULE, $cm->id)` is your friend for activity modules. Forgetting the context or using the wrong one (`CONTEXT_COURSE` instead of `CONTEXT_MODULE`) often leads to users inexplicably lacking permissions, or `get_string()` returning `[[string_not_found]]` errors. It’s an easy mistake to make, and often manifests as a silent permission denial that’s hard to trace.
3.  **`require_login()` vs. `require_course_login()` vs. `require_capability()`:** Understand the difference. `require_login()` just checks if *any* user is logged in. `require_course_login($course, true, $cm)` ensures the user is logged into the specific course containing your module *and* has access to the module itself. `require_capability()` (used with a context) is for fine-grained permission checks. Incorrect usage here can lead to either security holes (unauthorized access) or usability nightmares (legitimate users being blocked).
4.  **Database Upgrade Issues (`db/upgrade.php`):** When modifying your database schema after initial deployment, you'll write an `upgrade.php` script. Always wrap your DDL changes (e.g., `add_field()`, `drop_table()`) in `if ($oldversion < YYYYMMDDXX)` checks. Forgetting to do so means the upgrade script will try to run all previous schema changes every time, potentially causing "Field already exists" errors or data loss. This is why `version.php` incrementing is so vital.

### Trade-offs and Strategic Recommendations

When approaching Moodle plugin development, the biggest trade-off is often between extending core Moodle functionality versus building something entirely custom. My stance is clear: **always try to leverage Moodle's core APIs and existing plugin types first.** If a plugin exists that's 80% there, contribute to it or build a small local plugin that extends it, rather than rewriting from scratch. The cost of maintaining a fully custom activity module, including keeping it compatible with future Moodle versions, can be significant.

However, when you have a truly unique pedagogical requirement that Moodle's existing framework cannot accommodate, a custom activity module is the right path. For our peer-review module in Kuala Lumpur, the unique anonymous grading and complex rubric requirements simply couldn't be shoehorned into an existing assignment or workshop module without major performance hits and a terrible user experience. The initial estimates of extending an existing module showed development costs would exceed a custom module, purely because of the convoluted overrides needed.

Performance is another critical consideration. Be mindful of database queries. N+1 query problems are common. Use `$DB->get_records_sql()` or `$DB->get_records_array()` with appropriate `LIMIT` and `OFFSET` clauses, and ensure your tables have necessary indexes (as in `install.xml`). I once encountered a custom report that, for 10,000 students, executed over 50,000 database queries, resulting in a 25-second load time. By optimizing the queries to use `JOIN`s and caching lookup data, we brought that down to under 2 seconds.

Developing for Moodle means understanding its place in a larger ecosystem. Just as you need to ensure your module integrates seamlessly within Moodle's internal frameworks, the entire LMS often needs to integrate with broader campus systems, like single sign-on. I've personally been involved in deployments where [Building a Campus-Wide Single Sign-On (SSO) with Keycloak](/blog/building-campus-wide-sso-keycloak/) transformed user experience and simplified administration for thousands of students. A robust, well-integrated custom Moodle activity contributes to this larger, stable ecosystem.

Building your first custom Moodle activity module is an incredibly rewarding experience that unlocks the true power of Moodle's extensibility. You'll move beyond configuration and truly tailor the learning platform to your institution's unique needs. It's a journey filled with technical challenges, but armed with the right debugging tools, a solid understanding of Moodle's architecture, and a healthy respect for its internal APIs, you'll navigate these waters successfully. The lessons learned here, while Moodle-specific, resonate across the EdTech landscape. Whether you're customizing Moodle or tackling challenges like [Automating Canvas LMS Enrollments Using Python and REST APIs](/blog/automating-canvas-lms-enrollments/), the principles of robust architecture, API interaction, and meticulous debugging remain universally critical.