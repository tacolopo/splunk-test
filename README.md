# Splunk to AWS Observable Exporter

Automated export of Splunk observables to AWS (DynamoDB and S3).

## Data Architecture

This system maintains observable data (IPs, domains, etc.) in two complementary storage systems:

**DynamoDB (Fast Lookup Cache - 90 days)**
- Updated hourly from Splunk
- Automatically merges new data with existing records (cumulative hit counts, earliest first_seen, latest last_seen)
- TTL of 90 days - old records automatically expire to save costs
- Optimized for fast queries and lookups

**S3 Master File (Lifetime Archive)**
- Updated once per day by merging S3 lifetime data with DynamoDB current data
- Preserves **infinite lifetime history** of all observables
- Field-by-field intelligent merge:
  - `first_seen`: Preserves earliest timestamp ever recorded (from S3 or DynamoDB)
  - `last_seen`: Updates to most recent observation (from DynamoDB)
  - `total_hits`: Accumulates cumulative counts (intelligent MAX or ADD logic)
  - Lists: Merges and deduplicates (all unique IPs, users, etc. ever seen)
- Records older than 90 days (expired from DynamoDB) are preserved with their original first_seen dates
- When records reappear after expiring, their lifetime history is maintained and extended
- Format: CSV and JSON files at `observables/master.csv` and `observables/master.json`

**Lambda Function Execution Flow:**

**Trigger:**
- EventBridge (CloudWatch Events) invokes Lambda on schedule (default: hourly via `schedule_expression` in Terraform)
- Can be configured for any frequency: `rate(1 hour)`, `rate(30 minutes)`, `cron(0 * * * ? *)`, etc.

**Step 1: Authentication**
- Lambda retrieves Splunk credentials from AWS Secrets Manager
  - Secret name: `splunk/credentials` (configurable via `SPLUNK_SECRET_NAME` env var)
  - Contains: `{"host":"...", "port":"8089", "username":"...", "password":"...", "scheme":"https"}`
- IAM role grants Lambda permissions to:
  - Read from Secrets Manager
  - Query/Write to DynamoDB
  - Read/Write to S3 bucket
  - Write logs to CloudWatch

**Step 2: Query Splunk**
- Connects to Splunk REST API using credentials
- Executes SPL query from `splunk_queries/export_all_observables.spl`
- Queries the **`observable_catalog` summary index** (which is pre-populated by Splunk's own scheduled searches)

**Important:** Lambda does NOT create the summary data. Here's the separation of duties:

**In Splunk (separate process, runs continuously):**
  - Your Splunk scheduled searches analyze raw events (firewall logs, DNS, proxy, IDS alerts, etc.)
  - They identify observables (IPs, domains, hashes) and aggregate statistics
  - They write results to `index=observable_catalog` using the `collect` or `summary` command
  - Example: A search might run every 5-15 minutes analyzing the last hour of firewall data
  - These searches are configured in Splunk, not in this Lambda project

**Lambda's Role (aggregates summary data into single records per observable):**
  - Connects to Splunk and reads from the already-populated `observable_catalog` index
  - Uses `lookback_days` parameter to query a time window (e.g., last 1 day)
  - **Key function**: Aggregates MULTIPLE summary index events into ONE record per observable
    - Example: IP `10.0.0.1` may have 96 separate events in the index (one every 15 min for 24 hours)
    - Lambda query uses `| stats ... by indicator indicator_type` to combine them:
      - `min(first_seen)` - Earliest time this observable was seen
      - `max(last_seen)` - Latest time this observable was seen
      - `sum(hit_count)` - Total of all hit counts across all events
      - `values(src_ips)` - Deduplicated list of all source IPs across all events
      - `values(users)` - Deduplicated list of all users across all events
  - Exports this single consolidated record per observable to AWS

**Example Timeline:**
  ```
  Splunk scheduled searches (continuous):
    12:00 AM - Analyze last hour of logs → Write events to observable_catalog
               Example: IP 10.0.0.1 → 50 hits, IP 10.0.0.2 → 30 hits
    12:15 AM - Analyze last hour of logs → Write events to observable_catalog
               Example: IP 10.0.0.1 → 45 hits, IP 10.0.0.3 → 20 hits
    12:30 AM - Analyze last hour of logs → Write events to observable_catalog
               Example: IP 10.0.0.1 → 55 hits, IP 10.0.0.2 → 25 hits
    ...every 15 minutes... (96 events per observable over 24 hours)
  
  Observable_catalog index now contains:
    - 96 separate events for IP 10.0.0.1 (one per 15-min interval)
    - 64 separate events for IP 10.0.0.2 (appeared in some intervals)
    - 32 separate events for IP 10.0.0.3 (appeared in some intervals)
  
  Lambda (hourly at top of hour):
    1:00 AM - Query observable_catalog for last 24 hours
            - SPL query groups by indicator: | stats ... by indicator indicator_type
            - Aggregates 96 events for IP 10.0.0.1 → 1 consolidated record (total: 4,800 hits)
            - Aggregates 64 events for IP 10.0.0.2 → 1 consolidated record (total: 1,600 hits)
            - Aggregates 32 events for IP 10.0.0.3 → 1 consolidated record (total: 640 hits)
            - Export these 3 consolidated records to DynamoDB/S3
  ```

**Result:** 
- **Splunk**: Does the heavy lifting of analyzing raw logs continuously, writing many small incremental summary events
- **Lambda**: Aggregates those many summary events into single consolidated records per observable and exports to AWS for long-term storage

**Why this two-stage approach?**
- Splunk scheduled searches write incremental summaries (avoiding re-processing all historical data each time)
- Lambda aggregates these incremental summaries into complete daily/historical views
- This is more efficient than having Splunk maintain the full lifetime aggregation (which would slow down as data grows)

**Data Lifecycle & Retention:**
```
Raw Logs (Splunk main indexes)
    ↓
    → Analyzed by scheduled searches
    ↓
Summary Index (observable_catalog) - RETENTION: 2-7 days
    ↓ Auto-deleted by Splunk after retention period
    → Lambda reads & aggregates (within 24 hours)
    ↓
DynamoDB - RETENTION: 90 days
    ↓ Auto-deleted by TTL after 90 days
    → Lambda reads & merges to S3 (daily)
    ↓
S3 Master Files - RETENTION: Permanent (lifetime archive)
    → Never deleted, accumulates all historical data
```

**Key insight:** Each storage layer has progressively longer retention:
- Summary index: Days (just long enough for Lambda to process)
- DynamoDB: Months (fast queries for recent data)
- S3: Forever (complete historical archive)

**Step 3: Export to DynamoDB** (Every Run)
- For each observable from Splunk:
  - Checks if record exists in DynamoDB (by composite key: `indicator_type#indicator`)
  - **If exists**: Merges data intelligently
    - `first_seen`: Takes earliest timestamp
    - `last_seen`: Takes latest timestamp
    - `total_hits`: **Adds** new hits to existing count
    - `days_seen`: Recalculates based on time span
    - Lists (src_ips, users, etc.): Merges and deduplicates
  - **If new**: Creates new record
  - Sets TTL to 90 days from now
- Result: DynamoDB contains cumulative data for last 90 days

**Step 4: Export to S3** (Once Per Day)
- Lambda checks if S3 master file was already updated today
  - If yes: Skip S3 update (prevents redundant work)
  - If no: Proceed with S3 update
- Process:
  1. Scans entire DynamoDB table (pagination handled automatically)
  2. Downloads existing S3 master file (`observables/master.json` and `master.csv`)
  3. **Intelligent Merge** (field-by-field for records in both S3 and DynamoDB):
     - `first_seen`: Takes EARLIEST from S3 or DynamoDB (preserves lifetime first observation)
     - `last_seen`: Takes LATEST from S3 or DynamoDB (most recent observation)
     - `total_hits`: **Intelligent logic**:
       - If continuous tracking (no gap): Take MAX (DynamoDB has cumulative total)
       - If gap detected (expired and returned): ADD (preserve S3 history + new DynamoDB count)
     - Lists (`src_ips`, `dest_ips`, `users`, etc.): Merge and deduplicate from both sources
     - `days_seen`: Recalculate based on final first_seen and last_seen span
  4. **Records only in S3**: Keep unchanged (lifetime historical records older than 90 days)
  5. **Records only in DynamoDB**: Add as new (observables that appeared in last 90 days)
  6. Uploads merged data to S3 (replaces master files)
- Result: S3 contains **infinite lifetime history** with earliest first_seen dates and cumulative hit counts

**IAM Permissions:**
The Lambda execution role has fine-grained permissions:
- `secretsmanager:GetSecretValue` on Splunk credentials secret
- `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` on observables bucket
- `dynamodb:UpdateItem`, `dynamodb:PutItem`, `dynamodb:GetItem`, `dynamodb:Scan` on observable_catalog table
- `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` for CloudWatch Logs

**Monitoring:**
- CloudWatch Logs: All execution details logged to `/aws/lambda/splunk-observable-exporter`
- CloudWatch Alarm: Triggers if Lambda function errors occur
- Metrics: Duration, invocations, errors, concurrent executions

**Complete System Flow Diagram:**
```
┌────────────────────────────────────────────────────────────────────────┐
│ SPLUNK ENVIRONMENT (Your scheduled searches - configured separately)   │
└────────────────────────────────────────────────────────────────────────┘
         │
         │ Continuous (every 5-15 min, or your schedule)
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Splunk Scheduled Searches                                              │
│  - Analyze raw events: firewall, DNS, proxy, IDS, threat intel         │
│  - Identify observables: IPs, domains, hashes, URLs                     │
│  - Aggregate statistics: hit counts, src/dest IPs, users                │
│  - Write to summary index using | collect or | summary                  │
└─────────────────┬───────────────────────────────────────────────────────┘
                  │
                  ▼ Writes to
         ┌────────────────────┐
         │ Splunk Summary     │
         │ Index:             │
         │ observable_catalog │
         └────────┬───────────┘
                  │
                  │ Read by Lambda (below)
                  │
┌────────────────────────────────────────────────────────────────────────┐
│ AWS LAMBDA ENVIRONMENT (This project)                                  │
└────────────────────────────────────────────────────────────────────────┘
         │
         │ Hourly (or your configured schedule)
         ▼
┌─────────────────┐
│  EventBridge    │  ← Scheduled trigger
│  (CloudWatch    │
│    Events)      │
└────────┬────────┘
         │ Invokes
         ▼
┌─────────────────┐
│  Lambda         │
│  Function       │
└────────┬────────┘
         │
         ├─── 1. Get credentials ──→ ┌──────────────────┐
         │                           │ Secrets Manager  │
         │                           │ (Splunk creds)   │
         │                           └──────────────────┘
         │
         ├─── 2. Query SPL ────────→ ┌──────────────────┐
         │                           │ Splunk REST API  │
         │    ┌──────────────────────│ Read from:       │
         │    │   Query results       │ observable_      │
         │    │                       │   catalog index  │
         │    │                       └──────────────────┘
         ▼    ▼
         │
         ├─── 3a. Every run ───────→ ┌──────────────────┐
         │         Write/Merge       │   DynamoDB       │
         │                           │  (90-day cache)  │
         │                           │  TTL enabled     │
         │    ┌──────────────────────└──────────────────┘
         │    │   Read (daily)
         │    │
         ├─── 3b. Once/day ────────→ ┌──────────────────┐
         │         Scan all          │   S3 Bucket      │
         │                           │  master.json     │
         │         Load existing ────│  master.csv      │
         │         Merge & Save      │ (lifetime data)  │
         │                           └──────────────────┘
         │
         └─── Logs ────────────────→ ┌──────────────────┐
                                     │ CloudWatch Logs  │
                                     │ CloudWatch       │
                                     │   Alarms         │
                                     └──────────────────┘

FREQUENCY SUMMARY:
  - Splunk scheduled searches: Continuous (your configuration, typically 5-15 min)
  - Splunk summary index retention: 2-7 days (auto-deletion via frozenTimePeriodInSecs)
  - Lambda execution: Hourly (configurable via schedule_expression)
  - DynamoDB updates: Every Lambda run (hourly)
  - DynamoDB retention: 90 days (auto-deletion via TTL)
  - S3 master file updates: Once per day (automatic deduplication)
  - S3 retention: Permanent (lifetime archive)
```

**Hit Count Accumulation Example:**

*Scenario 1: Continuous Tracking*
- Day 1, midnight: S3 master has IP `10.0.0.1` with 1000 hits
- Day 2, hourly: DynamoDB accumulates hits from Splunk: 1000 → 1050 → 1100 → 1200
- Day 3, midnight: S3 update runs
  - S3 reads its old value: 1000 hits
  - S3 reads DynamoDB current value: 1200 hits (already cumulative)
  - **S3 takes DynamoDB value: 1200** ✓ (DynamoDB has been continuously tracking, no need to add)

*Scenario 2: Record Expires and Returns*
- Day 1: S3 has IP `10.0.0.2` with 5000 hits, last_seen = Aug 1
- Days 2-91: IP stops appearing in Splunk, eventually expires from DynamoDB (90-day TTL)
- Day 101: IP reappears! Splunk finds 100 new hits
- Day 102: S3 update runs
  - S3 has: 5000 hits, last_seen = Aug 1
  - DynamoDB has: 100 hits (fresh start), first_seen = Nov 10
  - Gap detected (Nov 10 > Aug 1)
  - **S3 adds: 5000 + 100 = 5100** ✓ (Preserves lifetime history)

## Prerequisites

**Splunk Configuration:**
This system queries the `observable_catalog` summary index in Splunk. Before deploying, ensure you have:

1. **Summary Index Created**: Create an index named `observable_catalog` in Splunk with SHORT retention
   
   **Critical: Configure data retention to prevent infinite growth**
   
   In `indexes.conf` or via Splunk Web (Settings > Indexes):
   ```conf
   [observable_catalog]
   homePath = $SPLUNK_DB/observable_catalog/db
   coldPath = $SPLUNK_DB/observable_catalog/colddb
   thawedPath = $SPLUNK_DB/observable_catalog/thaweddb
   
   # Keep data for 2-7 days (Lambda reads within 24 hours)
   frozenTimePeriodInSecs = 172800    # 2 days (recommended minimum)
   # OR: frozenTimePeriodInSecs = 604800    # 7 days (safer buffer)
   
   # Optional: Limit index size as additional safeguard
   maxTotalDataSizeMB = 10000    # 10 GB max
   ```
   
   **Why short retention is safe:**
   - Lambda reads and aggregates the data within 24 hours (configurable via `lookback_days`)
   - Once Lambda exports to AWS, the Splunk summary data is redundant
   - DynamoDB and S3 become the system of record for historical data
   - Short retention (2-7 days) provides a safety buffer for Lambda failures/delays
   
   **Alternative: Use Splunk's built-in data model acceleration** instead of summary indexing if you prefer not to manage retention policies.
   
   **Monitoring:** Check your summary index size regularly to ensure retention is working:
   ```spl
   | dbinspect index=observable_catalog
   | stats sum(sizeOnDiskMB) as totalSizeMB, min(startEpoch) as oldestData, max(endEpoch) as newestData
   | eval oldestDataTime=strftime(oldestData,"%Y-%m-%d %H:%M:%S"), 
          newestDataTime=strftime(newestData,"%Y-%m-%d %H:%M:%S"),
          retentionDays=round((newestData-oldestData)/86400,1)
   ```
   If `retentionDays` keeps growing beyond your configured period, check your `frozenTimePeriodInSecs` setting.

2. **Scheduled Searches**: Set up Splunk scheduled searches to populate the summary index with observable data
   - **Frequency**: Run continuously (recommended: every 5-15 minutes) to analyze raw logs in near real-time
   - **What they do**: Parse raw security logs (firewall, DNS, IDS, proxy, etc.) to identify and aggregate observables
   - **Output**: Write events to `index=observable_catalog` using SPL commands like `| collect` or `| summary`
   - **Required fields**: `indicator`, `indicator_type`, `hit_count`, `first_seen`, `last_seen`, `src_ips`, `dest_ips`, `users`, `sourcetypes`, `actions`, etc.
   - **Example sources**: Network traffic analysis, DNS logs, threat intelligence feeds, proxy logs, web logs, email logs

3. **Data Format**: Observables can include:
   - IPs (IPv4/IPv6)
   - Domains
   - URLs
   - File hashes (MD5, SHA1, SHA256)
   - User agents
   - Email addresses
   - Any other security indicators

**AWS Requirements:**
- AWS Account with permissions to create: Lambda, S3, DynamoDB, IAM roles, Secrets Manager, EventBridge
- AWS CLI configured (for deploying Splunk credentials)
- Terraform installed (>= 1.0)

## Quick Start

1. Build Lambda package:
   ```bash
   ./deploy_lambda.sh
   ```

2. Configure Terraform:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your production values:
   #   - s3_bucket_name: Choose a globally unique name (e.g., "mycompany-splunk-observables-prod")
   #                     Terraform will CREATE this bucket with the name you specify
   #   - aws_region: Your AWS region
   #   - dynamodb_table_name: Choose a table name (e.g., "observable_catalog")
   #                          Terraform will CREATE this table with the name you specify
   #   - lookback_days: Days to look back in Splunk
   #   - schedule_expression: How often to run (e.g., "rate(1 hour)")
   ```

3. Deploy:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

4. Add Splunk credentials:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id splunk/credentials \
     --secret-string '{"host":"YOUR_HOST","port":"8089","username":"USER","password":"PASS","scheme":"https"}' \
     --region us-east-1
   ```

## Files

### Core Application
- **`export_to_aws.py`** - Main export logic
  - `SplunkObservableExporter` class with all business logic
  - Handles Splunk authentication via Secrets Manager
  - Executes SPL queries against Splunk REST API
  - Implements intelligent merge logic for DynamoDB and S3
  - Can be run locally or in Lambda
  
- **`lambda_function.py`** - AWS Lambda entry point
  - `lambda_handler()` function invoked by EventBridge
  - Configures exporter from environment variables
  - Returns JSON response with status/errors
  
### Splunk Queries
- **`splunk_queries/export_all_observables.spl`** - Production query used by Lambda
  - Queries `index=observable_catalog` summary index
  - Aggregates observables by indicator and indicator_type
  - Calculates cumulative stats: hit counts, first/last seen, associated IPs/users
  - Uses `$lookback$` variable (replaced with `LOOKBACK_DAYS` env var)
  
- **`splunk_queries/observable_catalog.spl`** - Reference/documentation query
  - Example query showing the expected structure of the summary index
  - Can be used as a template for your Splunk scheduled searches
  
### Infrastructure
- **`terraform/`** - Infrastructure as Code
  - `main.tf` - All AWS resources (Lambda, S3, DynamoDB, IAM, EventBridge, Alarms)
  - `variables.tf` - Input variables
  - `outputs.tf` - Output values (bucket name, DynamoDB table name, etc.)
  - `terraform.tfvars.example` - Template for your configuration
  
### Deployment
- **`deploy_lambda.sh`** - Build script
  - Creates Python virtual environment
  - Installs dependencies from `requirements.txt`
  - Packages code and dependencies into `lambda_tiny.zip`
  - Used by Terraform to deploy Lambda function
  
- **`requirements.txt`** - Python dependencies
  - `splunk-sdk` - Splunk REST API client
  - `boto3` - AWS SDK (included in Lambda runtime, but listed for local dev)

See `terraform/terraform.tfvars.example` for all configuration options.
