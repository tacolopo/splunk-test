# Complete Testing Guide - Running from Your Local Machine

This guide is for testing the solution using **your local machine** where you already have the code.

---

## Prerequisites on Your Local Machine

Make sure you have these installed:

```bash
# Check what you have
python --version    # Need 3.7+
docker --version    # Need Docker Desktop running
aws --version       # Need AWS CLI
git --version       # Already have this (you're in the repo!)
```

If missing anything:
- **Python**: https://www.python.org/downloads/
- **Docker Desktop**: https://www.docker.com/products/docker-desktop/
- **AWS CLI**: https://aws.amazon.com/cli/

---

## Part 1: AWS Setup (Browser + AWS CLI)

These steps create AWS resources. Some are in AWS Console (browser), some are AWS CLI commands (run on your local machine).

### Step 1: Configure AWS CLI (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE
aws configure
```

Enter:
- **AWS Access Key ID**: Get from AWS Console → IAM → Users → Security credentials → Create access key
- **AWS Secret Access Key**: Shows when you create the key
- **Default region**: `us-east-1`
- **Output format**: `json`

**Verify it works:**
```bash
# Run on YOUR LOCAL MACHINE
aws sts get-caller-identity
```

You should see your account info.

---

### Step 2: Create DynamoDB Table (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE (you're already in the repo directory)
cd /home/user/Documents/Splunk\ to\ AWS\ Project

# Install Python dependencies
pip install -r requirements.txt

# Create the DynamoDB table
python create_dynamodb_table.py --region us-east-1
```

**Expected output:**
```
Creating table observable_catalog...
Table observable_catalog created successfully!
```

**If you get a permissions error:**

You need to add DynamoDB permissions to your user. As admin, run:

```bash
# Run on YOUR LOCAL MACHINE (as admin)
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess

# Verify it was attached
aws iam list-attached-user-policies --user-name test
```

Then run the create table command again:
```bash
python create_dynamodb_table.py --region us-east-1
```

**What this created in AWS:**
- Table name: `observable_catalog`
- Region: us-east-1
- Billing: PAY_PER_REQUEST (auto-scales, free tier eligible)
- You can view it: AWS Console → DynamoDB → Tables

---

### Step 3: Create S3 Bucket (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE
BUCKET_NAME="splunk-observables-$(date +%s)"
aws s3 mb s3://${BUCKET_NAME} --region us-east-1

# Show the bucket name (WRITE THIS DOWN!)
echo "Your S3 bucket: ${BUCKET_NAME}"

# Save it for later use
echo "export S3_BUCKET=${BUCKET_NAME}" >> ~/.bashrc
source ~/.bashrc
```

**If you get permissions error:**
```bash
# Add S3 permissions
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
```

**What this created in AWS:**
- A unique S3 bucket
- Region: us-east-1
- You can view it: AWS Console → S3 → Buckets

**⚠️ IMPORTANT: Write down your bucket name! You'll need it in Step 6.**

---

### Step 4: Create Secrets Manager Secret (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE
aws secretsmanager create-secret \
  --name splunk/credentials \
  --description "Splunk API credentials" \
  --secret-string '{
    "host": "localhost",
    "port": "8089",
    "username": "admin",
    "password": "Changeme123!",
    "scheme": "https"
  }' \
  --region us-east-1
```

**If you get permissions error:**
```bash
# Add Secrets Manager permissions
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite
```

**What this created in AWS:**
- Secret name: `splunk/credentials`
- Contains Splunk connection info
- You can view it: AWS Console → Secrets Manager

---

### Step 5: Verify AWS Resources Created

```bash
# Run on YOUR LOCAL MACHINE

# Check DynamoDB table
aws dynamodb describe-table --table-name observable_catalog --region us-east-1 --query 'Table.TableStatus'
# Should show: "ACTIVE"

# Check S3 bucket
aws s3 ls | grep splunk-observables
# Should show your bucket

# Check Secrets Manager
aws secretsmanager describe-secret --secret-id splunk/credentials --region us-east-1 --query 'Name'
# Should show: "splunk/credentials"
```

✅ **AWS Setup Complete!** You now have:
- DynamoDB table for fast IP lookups
- S3 bucket for historical data
- Secrets Manager for credentials

---

## Part 2: Docker Splunk Setup (Local Machine)

All these commands run on **your local machine**.

### Step 6: Start Splunk in Docker (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE
# First, stop and remove any existing Splunk container
docker stop splunk 2>/dev/null || true
docker rm splunk 2>/dev/null || true

# Start Splunk with proper license acceptance
docker run -d \
  -p 8000:8000 \
  -p 8089:8089 \
  -e SPLUNK_GENERAL_TERMS='--accept-sgt-current-at-splunk-com' \
  -e SPLUNK_START_ARGS='--accept-license' \
  -e SPLUNK_PASSWORD='Changeme123!' \
  --name splunk \
  splunk/splunk:latest

# Wait for Splunk to start (takes 2-3 minutes)
echo "Waiting for Splunk to start..."
sleep 120

# Check if it's running
docker logs splunk | tail -30
```

**What to look for:**

Splunk is still starting if you see:
- Ansible tasks running (like "TASK [splunk_standalone...]")
- "Check for required restarts"
- Various initialization tasks

**Splunk is ready when you see:**
- "Ansible playbook complete" OR
- "Splunk started successfully" OR
- No new log entries for 30+ seconds

**If logs keep scrolling, wait another minute and check again:**
```bash
docker logs splunk | tail -10
```

**Once Splunk is ready, verify it's running:**
```bash
# Check if Splunk web interface responds (use HTTP, not HTTPS)
curl http://localhost:8000 2>&1 | head -5

# Should see HTML response with "Splunk" in it
```

**Or open in browser:**
- Go to: **http://localhost:8000** (HTTP, not HTTPS)
- Login: `admin` / `Changeme123!`
- You should see the Splunk dashboard

**Note:** Splunk web UI uses HTTP on port 8000. The API uses HTTPS on port 8089.

**If you see license errors**, make sure you have both environment variables:
- `SPLUNK_GENERAL_TERMS='--accept-sgt-current-at-splunk-com'`
- `SPLUNK_START_ARGS='--accept-license'`

---

### Step 7: Add Sample Data to Splunk (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE
cd /home/user/Documents/Splunk\ to\ AWS\ Project

# Create sample security logs with CURRENT date (so time filters work)
CURRENT_DATE=$(date +%Y-%m-%d)
cat > sample_logs.json << EOF
{"_time": "${CURRENT_DATE}T10:00:00", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.1", "action": "blocked", "user": "admin"}
{"_time": "${CURRENT_DATE}T10:05:00", "src_ip": "8.8.8.8", "dest_ip": "10.0.0.2", "action": "allowed", "user": "user1"}
{"_time": "${CURRENT_DATE}T10:10:00", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.3", "action": "blocked", "user": "admin"}
{"_time": "${CURRENT_DATE}T10:15:00", "src_ip": "192.168.1.100", "dest_ip": "8.8.8.8", "action": "allowed", "user": "user2"}
{"_time": "${CURRENT_DATE}T10:20:00", "email": "user@example.com", "action": "login", "src_ip": "203.0.113.5"}
{"_time": "${CURRENT_DATE}T10:25:00", "hash": "5d41402abc4b2a76b9719d911017c592", "action": "detected", "file": "malware.exe"}
{"_time": "${CURRENT_DATE}T10:30:00", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.5", "action": "blocked", "user": "admin"}
{"_time": "${CURRENT_DATE}T10:35:00", "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "action": "web_request"}
EOF

# Method 1: Add data via REST API (Recommended - most reliable)
# Send each JSON line as a separate event via Splunk's simple receiver
while IFS= read -r line; do
  curl -k -s -u admin:Changeme123! \
    https://localhost:8089/services/receivers/simple \
    -d "sourcetype=_json" \
    -d "index=main" \
    --data-urlencode "event=$line" > /dev/null
done < sample_logs.json

echo "✓ Data sent to Splunk. Verify with: index=main | head 10"

# Method 2: Use the helper script (Alternative)
# ./add_data_to_splunk.sh

# Method 3: Add data via Splunk Web UI (Alternative)
# 1. Open Splunk: http://localhost:8000
# 2. Login: admin / Changeme123!
# 3. Click "Add Data" (top right) or Settings → Add Data
# 4. Select "Upload" → Choose Files
# 5. Select sample_logs.json
# 6. Set sourcetype to: _json
# 7. Set index to: main
# 8. Click "Review" → "Submit"
```

---

### Step 8: Configure Splunk (Browser)

**Open Splunk Web UI:** http://localhost:8000 (login: admin/Changeme123!)

#### 8a. Create Summary Index

1. Click **Settings** → **Indexes**
2. Click **New Index** (top right)
3. Fill in:
   - **Index Name:** `observable_catalog`
   - Leave other settings as default
4. Click **Save**

#### 8b. Verify Sample Data

1. Click **Search & Reporting** (left sidebar)

2. **Search WITHOUT time filter first (data might have old timestamps):**
   ```
   index=main | head 10
   ```
   OR search all indexes:
   ```
   index=* | head 10
   ```

3. **If you see data, check by source:**
   ```
   source="*sample_logs*" | head 10
   ```

4. **Check what index the data is in:**
   ```
   source="*sample_logs*" | stats count by index
   ```

**Expected:** You should see 8 events with fields like `src_ip`, `dest_ip`, `email`, `hash`, etc.

**Common Issue:** If your sample_logs.json has dates from 2024 but today is 2025, the `earliest=-24h` filter won't match. Either:
- Search without time filter: `index=main | head 10`
- Or recreate sample_logs.json with current date (the script above does this automatically)

#### 8c. Create Scheduled Search

1. Go to **Settings** → **Searches, reports, and alerts**
2. Click **New Report**
3. **Title:** `Observable Catalog - Hourly Summary`
4. **Search:** Copy the query from `splunk_queries/observable_catalog.spl`

**For testing with sample data, use this TEST version instead:**

To copy the test query (searches `index=main` instead of production indexes):
```bash
# Run on YOUR LOCAL MACHINE
cat splunk_queries/observable_catalog_test.spl
```

**OR for production (searches proxy/email/edr indexes):**
```bash
cat splunk_queries/observable_catalog.spl
```

Copy the entire output and paste into Splunk search box.

**Note:** The test version searches `index=main` (where your sample data is). The production version searches `index=proxy OR index=email OR index=edr...` (for real production data).

5. Click **Save**

6. **Enable Scheduling:**
   - After saving, click **Edit Schedule** button
   - In the "Edit Schedule" dialog, check the box **"Schedule Report"** (this enables scheduling)
   - **Schedule Type:** Cron
   - **Cron Schedule:** `0 * * * *` (runs every hour at :00)
   - **Time Range:** `-1h@h to @h` (last hour)
   - **Priority:** Default
   - Click **Save**

**Note:** If you see a warning about "removal of the time picker", that's normal - click through it.

#### 8d. Run Search Manually (for immediate results)

**IMPORTANT:** The query searches `index=main` - make sure your sample data is in the `main` index!

1. In the scheduled search, click **Open in Search**

2. **First, verify your data exists:**
   ```
   index=main | head 10
   ```
   If this shows no results, your data might be in a different index. Check:
   ```
   index=* | head 10
   ```
   Then update the query to use the correct index.

3. **First, debug what fields exist:**
   ```
   index=main | head 1 | fields *
   ```
   This shows all fields in your data. Verify you see: `src_ip`, `dest_ip`, `email`, `hash`, `user_agent`

4. **First, check if data exists at all:**
   ```
   index=main | head 10
   ```
   If this shows 0 results, your data isn't in the main index. Try:
   ```
   index=* | head 10
   ```
   This searches all indexes.

5. **Check what sourcetype your data has:**
   ```
   index=main | head 1 | fields sourcetype, source, _raw
   ```
   OR check all sourcetypes:
   ```
   index=main | stats count by sourcetype
   ```

6. **If sourcetype is NOT _json (like `unknown-too_small`), extract JSON from URL-encoded form data:**
   ```
   index=main
   | eval _raw=urldecode(_raw)
   | rex field=_raw "event=(?<json_event>.+)"
   | eval json_event=urldecode(json_event)
   | spath input=json_event
   | head 10
   ```
   The data comes as URL-encoded form data (`event={...}`), so we extract the `event` parameter, decode it, then parse JSON.

7. **If still nothing, check the raw event:**
   ```
   index=main | head 1 | table _raw
   ```
   This shows the raw JSON. Verify it looks like: `{"_time": "...", "src_ip": "1.2.3.4", ...}`

5. **Run the full query (skip test steps - just run it):**
   - Get the query: `cat splunk_queries/observable_catalog_test.spl`
   - Copy the ENTIRE query
   - Paste into Splunk search box
   - Change time range to **All time** (to ensure it processes your data)
   - Click the green **Search** button
   - Wait ~10 seconds

#### 8e. Verify Summary Index Has Data

**After running the search manually (Step 8d), check if data was written to summary index:**

Run this search in Splunk:
```
index=observable_catalog | head 10
```

**IMPORTANT: Change time range to "All time"** (the default "Last 24 hours" won't show your data if it's older)

**Expected:** You should see aggregated observables (IPs with counts, first_seen, last_seen, indicator_type, etc.)

**If you see data:** Great! Continue to Step 9 (Run the Export Script).

---

## Part 3: Run the Export (Local Machine)

All commands run on **your local machine**.

### Step 9: Create Config File (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE
cd /home/user/Documents/Splunk\ to\ AWS\ Project

# Create config.json with YOUR S3 bucket name
# Replace the placeholder with your actual bucket from Step 3
cat > config.json << EOF
{
  "splunk": {
    "host": "localhost",
    "port": 8089,
    "username": "admin",
    "password": "Changeme123!",
    "scheme": "https"
  },
  "aws": {
    "region": "us-east-1",
    "s3_bucket": "${S3_BUCKET}",
    "s3_prefix": "observables",
    "dynamodb_table": "observable_catalog"
  }
}
EOF

# Verify the config has your bucket name
cat config.json | grep s3_bucket
```

**Make sure you see your actual bucket name, not "${S3_BUCKET}"!**

If it shows `"${S3_BUCKET}"`, manually edit the file:
```bash
nano config.json
# Change "s3_bucket": "${S3_BUCKET}" to your actual bucket name
```

---

### Step 10: Run the Export Script (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE
cd /home/user/Documents/Splunk\ to\ AWS\ Project

python export_to_aws.py \
  --config config.json \
  --format all \
  --lookback 7
```

**Expected output:**
```
2024-XX-XX XX:XX:XX - INFO - Connected to Splunk successfully
2024-XX-XX XX:XX:XX - INFO - S3 client initialized
2024-XX-XX XX:XX:XX - INFO - DynamoDB client initialized
2024-XX-XX XX:XX:XX - INFO - Executing Splunk search (lookback: 7 days)
2024-XX-XX XX:XX:XX - INFO - Retrieved X observables from Splunk
2024-XX-XX XX:XX:XX - INFO - Uploaded CSV to s3://...
2024-XX-XX XX:XX:XX - INFO - Uploaded JSON to s3://...
2024-XX-XX XX:XX:XX - INFO - Successfully exported to DynamoDB
2024-XX-XX XX:XX:XX - INFO - Export completed successfully
```

---

## Part 4: Verify the Results

### Step 11: Check DynamoDB (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE

# Query for a specific IP
# First, see what keys exist:
aws dynamodb scan --table-name observable_catalog --region us-east-1 --max-items 5 \
  --projection-expression "indicator_key" | python3 -m json.tool

# Then query a specific item (replace with an actual key from above):
aws dynamodb get-item \
  --table-name observable_catalog \
  --key '{"indicator_key": {"S": "ip#10.0.0.1"}}' \
  --region us-east-1 | python3 -m json.tool

# Or query by indicator_type using GSI:
aws dynamodb query \
  --table-name observable_catalog \
  --index-name indicator-type-index \
  --key-condition-expression "indicator_type = :it" \
  --expression-attribute-values '{":it": {"S": "ip"}}' \
  --region us-east-1 | python3 -m json.tool

# List all observables
aws dynamodb scan \
  --table-name observable_catalog \
  --region us-east-1 \
  --max-items 10
```

Or use the test script:
```bash
# Run on YOUR LOCAL MACHINE
python test_ip_address.py
```

---

### Step 12: Check S3 (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE

# List files in S3
aws s3 ls s3://${S3_BUCKET}/observables/ --recursive --human-readable

# Download a CSV file to view
aws s3 cp s3://${S3_BUCKET}/observables/$(aws s3 ls s3://${S3_BUCKET}/observables/ --recursive | grep csv | tail -1 | awk '{print $4}') ./downloaded_observables.csv

# View the CSV
head -20 downloaded_observables.csv
```

**⚠️ IMPORTANT: How to Search S3 Data**

S3 has multiple files, so searching requires one of these approaches:

**Option 1: Use DynamoDB (FASTEST - Recommended for operational lookups)**
```bash
# DynamoDB is designed for fast lookups - use it instead of searching S3!
aws dynamodb get-item \
  --table-name observable_catalog \
  --key '{"indicator_key": {"S": "ip#10.0.0.1"}}' \
  --region us-east-1 | python3 -m json.tool
```

**Option 2: Use AWS Athena (Best for historical analysis across many files)**

**Use AWS Console (CLI has permission issues):**

1. Go to: https://console.aws.amazon.com/athena/
2. Click **Settings** tab → Set **Query result location** to: `s3://splunk-observables-1763476191/athena-results/`
3. Click **Save**
4. Go to **Editor** tab

**Step 1: Create Database**
Copy and paste ONLY this line (not the "sql" part):
```
CREATE DATABASE IF NOT EXISTS splunk_observables
```

**Step 2: Create Table**
Copy and paste ONLY the SQL below (replace bucket name if different):
**IMPORTANT: Drop the table first if it already exists:**
```
DROP TABLE IF EXISTS splunk_observables.observables
```

Then create the table matching your CSV format:
```
CREATE EXTERNAL TABLE IF NOT EXISTS splunk_observables.observables (
  actions string,
  dest_ips string,
  export_timestamp string,
  indicator string,
  indicator_type string,
  sourcetypes string,
  src_ips string,
  total_hits bigint,
  types string,
  unique_dest_ips bigint,
  unique_src_ips bigint,
  users string
)
PARTITIONED BY (date string)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe'
WITH SERDEPROPERTIES (
  'serialization.format' = ',',
  'field.delim' = ','
)
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://splunk-observables-1763476191/observables/'
TBLPROPERTIES ('skip.header.line.count'='1')
```

**Step 3: Add Partitions**
Copy and paste ONLY this line:
```
MSCK REPAIR TABLE splunk_observables.observables
```

**Step 3b: Verify Partitions Were Added**
Run this to see if partitions were discovered:
```
SHOW PARTITIONS splunk_observables.observables
```

If no partitions show up, manually add the partition:
```
ALTER TABLE splunk_observables.observables ADD PARTITION (date='2025-11-18') LOCATION 's3://splunk-observables-1763476191/observables/date=2025-11-18/'
```

**Step 4: Query Your Data**
**CRITICAL: First verify partitions exist:**
```
SHOW PARTITIONS splunk_observables.observables
```

If no partitions show, manually add:
```
ALTER TABLE splunk_observables.observables ADD PARTITION (date='2025-11-18') LOCATION 's3://splunk-observables-1763476191/observables/date=2025-11-18/'
```

Then check if ANY data exists (remove date filter):
```
SELECT * FROM splunk_observables.observables LIMIT 10
```

If still no results, check the raw S3 location:
```
SELECT * FROM splunk_observables.observables WHERE date = '2025-11-18' LIMIT 10
```

Then query specific IPs:
Now you can run queries like (copy ONLY the SQL, not the "sql" marker):

Find a specific IP across all dates:
```
SELECT indicator, indicator_type, total_hits, src_ips, dest_ips, date
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
  AND indicator = '10.0.0.1'
ORDER BY date DESC
```

Find all IPs (remove date filter if you only have today's data):
```
SELECT indicator, SUM(total_hits) as total_hits, MAX(export_timestamp) as last_export
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
GROUP BY indicator
ORDER BY total_hits DESC
```

Find all IPs for a specific date:
```
SELECT indicator, SUM(total_hits) as total_hits, MAX(export_timestamp) as last_export
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
  AND date = '2025-11-18'
GROUP BY indicator
ORDER BY total_hits DESC
```

**Option 3: Quick Local Search (for testing)**
```bash
# Download all CSVs and search locally (only for small datasets!)
mkdir -p /tmp/s3_search
aws s3 sync s3://${S3_BUCKET}/observables/ /tmp/s3_search/ --exclude "*.json"

# Search for IP in all CSVs
grep -r "10.0.0.1" /tmp/s3_search/*.csv

# Or use jq for JSON files
aws s3 cp s3://${S3_BUCKET}/observables/date=2025-11-18/observables_20251118_105738.json - | \
  jq '.[] | select(.indicator == "10.0.0.1")'
```

**Summary:**
- **Fast lookups (< 1 second)**: Use DynamoDB (already set up!)
- **Historical analysis**: Use AWS Athena (query multiple files)
- **Quick testing**: Download and search locally

---

### Step 13: Verify in AWS Console (Browser)

**Check DynamoDB:**
1. Go to: AWS Console → DynamoDB → Tables
2. Click `observable_catalog`
3. Click **Explore table items**
4. You should see items like `ip#1.2.3.4`, `ip#8.8.8.8`, etc.

**Check S3:**
1. Go to: AWS Console → S3 → Buckets
2. Click your `splunk-observables-*` bucket
3. Navigate to `observables/date=YYYY-MM-DD/`
4. You should see CSV and JSON files

---

## Summary of Where Things Run

| Step | Location | What You're Doing |
|------|----------|-------------------|
| **AWS CLI commands** | Your local machine terminal | Creating AWS resources |
| **Python scripts** | Your local machine terminal | Running export, tests |
| **Docker commands** | Your local machine terminal | Managing Splunk container |
| **Splunk Web UI** | Your local browser (localhost:8000) | Configuring indexes, searches |
| **AWS Console** | Your browser (console.aws.amazon.com) | Viewing AWS resources |

---

## Complete Command Summary

Here's everything in order:

```bash
# === ON YOUR LOCAL MACHINE ===

# 1. Configure AWS
aws configure

# 2. Install dependencies (already in repo directory)
cd /home/user/Documents/Splunk\ to\ AWS\ Project
pip install -r requirements.txt

# 3. Create AWS resources
python create_dynamodb_table.py --region us-east-1
BUCKET_NAME="splunk-observables-$(date +%s)"
aws s3 mb s3://${BUCKET_NAME} --region us-east-1
echo "export S3_BUCKET=${BUCKET_NAME}" >> ~/.bashrc
source ~/.bashrc

aws secretsmanager create-secret --name splunk/credentials \
  --secret-string '{"host":"localhost","port":"8089","username":"admin","password":"Changeme123!","scheme":"https"}' \
  --region us-east-1

# 4. Start Splunk Docker
docker run -d -p 8000:8000 -p 8089:8089 \
  -e SPLUNK_PASSWORD='Changeme123!' --name splunk splunk/splunk:latest
  
sleep 120  # Wait for Splunk to start

# 5. Add sample data
cat > sample_logs.json << 'EOF'
{"_time": "2024-01-15T10:00:00", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.1", "action": "blocked"}
{"_time": "2024-01-15T10:05:00", "src_ip": "8.8.8.8", "dest_ip": "10.0.0.2", "action": "allowed"}
{"_time": "2024-01-15T10:10:00", "email": "user@example.com", "action": "login"}
{"_time": "2024-01-15T10:15:00", "hash": "5d41402abc4b2a76b9719d911017c592", "action": "detected"}
EOF

docker cp sample_logs.json splunk:/opt/splunk/sample_logs.json
docker exec splunk /opt/splunk/bin/splunk add oneshot /opt/splunk/sample_logs.json \
  -sourcetype _json -index main -auth admin:Changeme123!

# === IN BROWSER (http://localhost:8000) ===
# - Create observable_catalog index
# - Create scheduled search
# - Run search manually

# === BACK ON LOCAL MACHINE ===

# 6. Create config
cat > config.json << EOF
{
  "splunk": {
    "host": "localhost",
    "port": 8089,
    "username": "admin",
    "password": "Changeme123!",
    "scheme": "https"
  },
  "aws": {
    "region": "us-east-1",
    "s3_bucket": "${S3_BUCKET}",
    "s3_prefix": "observables",
    "dynamodb_table": "observable_catalog"
  }
}
EOF

# 7. Run export
python export_to_aws.py --config config.json --format all --lookback 7

# 8. Verify results
python test_ip_address.py
aws dynamodb scan --table-name observable_catalog --max-items 5
aws s3 ls s3://${S3_BUCKET}/observables/ --recursive
```

---

## Troubleshooting

### Permissions Errors (Admin Fix)

If you get any "AccessDenied" errors, add the required policies:

```bash
# Add all required policies at once
aws iam attach-user-policy --user-name test --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
aws iam attach-user-policy --user-name test --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-user-policy --user-name test --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite

# Verify policies attached
aws iam list-attached-user-policies --user-name test
```

### Splunk not starting

```bash
# Check Docker logs
docker logs splunk | tail -50

# Restart Splunk
docker restart splunk
```

### AWS CLI not configured

```bash
# Reconfigure
aws configure

# Test
aws sts get-caller-identity
```

### Can't connect to Splunk from script

```bash
# Test API connection
curl -k -u admin:Changeme123! \
  https://localhost:8089/services/auth/login \
  -d username=admin \
  -d password=Changeme123!
```

### Bucket name not set in config

```bash
# Check environment variable
echo $S3_BUCKET

# If empty, set it manually:
export S3_BUCKET="your-bucket-name-here"

# Then recreate config.json
```

---

## Cleanup When Done

```bash
# Stop and remove Splunk
docker stop splunk
docker rm splunk

# Delete AWS resources
aws dynamodb delete-table --table-name observable_catalog --region us-east-1
aws s3 rb s3://${S3_BUCKET} --force --region us-east-1
aws secretsmanager delete-secret --secret-id splunk/credentials --force-delete-without-recovery --region us-east-1

# Remove local files
rm config.json sample_logs.json downloaded_observables.csv
```

---

## Success! ✅

You've successfully:
- Created AWS resources (DynamoDB, S3, Secrets Manager)
- Run Splunk locally in Docker
- Indexed sample security data
- Exported observables to AWS
- Verified data in both DynamoDB and S3

**Next Steps:**
- Add more data to Splunk
- Deploy Lambda for automation (see DEPLOYMENT.md)
- Set up monitoring (see README.md)

