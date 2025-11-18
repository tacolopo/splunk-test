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

**What this created in AWS:**
- Table name: `observable_catalog`
- Region: us-east-1
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
docker run -d \
  -p 8000:8000 \
  -p 8089:8089 \
  -e SPLUNK_START_ARGS='--accept-license' \
  -e SPLUNK_PASSWORD='Changeme123!' \
  --name splunk \
  splunk/splunk:latest

# Wait for Splunk to start (takes 2-3 minutes)
echo "Waiting for Splunk to start..."
sleep 120

# Check if it's running
docker logs splunk | tail -20
```

Look for "Ansible playbook complete" in the logs - that means Splunk is ready.

**Verify Splunk is running:**
- Open browser: http://localhost:8000
- Login: `admin` / `Changeme123!`
- You should see the Splunk dashboard

---

### Step 7: Add Sample Data to Splunk (Local Machine)

```bash
# Run on YOUR LOCAL MACHINE
cd /home/user/Documents/Splunk\ to\ AWS\ Project

# Create sample security logs
cat > sample_logs.json << 'EOF'
{"_time": "2024-01-15T10:00:00", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.1", "action": "blocked", "user": "admin"}
{"_time": "2024-01-15T10:05:00", "src_ip": "8.8.8.8", "dest_ip": "10.0.0.2", "action": "allowed", "user": "user1"}
{"_time": "2024-01-15T10:10:00", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.3", "action": "blocked", "user": "admin"}
{"_time": "2024-01-15T10:15:00", "src_ip": "192.168.1.100", "dest_ip": "8.8.8.8", "action": "allowed", "user": "user2"}
{"_time": "2024-01-15T10:20:00", "email": "user@example.com", "action": "login", "src_ip": "203.0.113.5"}
{"_time": "2024-01-15T10:25:00", "hash": "5d41402abc4b2a76b9719d911017c592", "action": "detected", "file": "malware.exe"}
{"_time": "2024-01-15T10:30:00", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.5", "action": "blocked", "user": "admin"}
{"_time": "2024-01-15T10:35:00", "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "action": "web_request"}
EOF

# Copy file into Splunk container
docker cp sample_logs.json splunk:/opt/splunk/sample_logs.json

# Index the data in Splunk
docker exec splunk /opt/splunk/bin/splunk add oneshot /opt/splunk/sample_logs.json \
  -sourcetype _json \
  -index main \
  -auth admin:Changeme123!
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
2. Run this search:
   ```
   index=main earliest=-24h | head 10
   ```
3. You should see 8 events with IPs, emails, hashes

#### 8c. Create Scheduled Search

1. Go to **Settings** → **Searches, reports, and alerts**
2. Click **New Report**
3. **Title:** `Observable Catalog - Hourly Summary`
4. **Search:** Copy the entire query from `splunk_queries/observable_catalog.spl`

To copy the query:
```bash
# Run on YOUR LOCAL MACHINE
cat splunk_queries/observable_catalog.spl
```

Copy the entire output and paste into Splunk search box.

5. Click **Save**
6. Click **Edit Schedule**:
   - Enable scheduling: Yes
   - **Cron Schedule:** `0 * * * *` (every hour)
   - **Time Range:** `-1h@h to @h`
7. Click **Save**

#### 8d. Run Search Manually (for immediate results)

1. In the scheduled search, click **Open in Search**
2. Change time range to **Last 24 hours**
3. Click the green **Search** button
4. Wait ~10 seconds

#### 8e. Verify Summary Index Has Data

Run this search in Splunk:
```
index=observable_catalog | head 10
```

You should see aggregated observables (IPs with counts, first_seen, last_seen).

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
aws dynamodb get-item \
  --table-name observable_catalog \
  --key '{"indicator_key": {"S": "ip#1.2.3.4"}}' \
  --region us-east-1

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

