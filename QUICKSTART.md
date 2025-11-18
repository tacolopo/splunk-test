# Quick Start Guide: Docker Splunk + AWS Testing

This guide walks you through testing the complete Splunk observable catalog solution from scratch using Docker Splunk and AWS Free Tier.

**Time Required:** 30 minutes  
**Cost:** $0 (using AWS Free Tier)  
**Prerequisites:** AWS account, Docker installed, AWS CLI configured

---

## Step 1: Clone the Repository

```bash
# Clone from GitHub
git clone https://github.com/tacolopo/splunk-test.git
cd splunk-test

# Verify files
ls -la
```

You should see:
- `export_to_aws.py` - Main export script
- `terraform/` - Infrastructure as code
- `splunk_queries/` - Splunk SPL queries
- `test_*.py` - Testing scripts
- `TESTING.md` - Full testing documentation

---

## Step 2: Install Python Dependencies

```bash
# Install required Python packages
pip install -r requirements.txt

# Verify installation
python -c "import splunklib; import boto3; print('✓ Dependencies installed')"
```

Expected output: `✓ Dependencies installed`

---

## Step 3: Set Up Docker Splunk

```bash
# Pull and run Splunk container
docker run -d \
  -p 8000:8000 \
  -p 8089:8089 \
  -e SPLUNK_GENERAL_TERMS='--accept-sgt-current-at-splunk-com' \
  -e SPLUNK_START_ARGS='--accept-license' \
  -e SPLUNK_PASSWORD='Changeme123!' \
  --name splunk \
  splunk/splunk:latest

# Wait for Splunk to start (2-3 minutes)
echo "Waiting for Splunk to start..."
sleep 30

# Check Splunk logs
docker logs splunk | tail -20

# Look for "Ansible playbook complete" - means it's ready
```

**Verify Splunk is running:**
- Open browser: http://localhost:8000
- Login: `admin` / `Changeme123!`
- You should see the Splunk dashboard

---

## Step 4: Configure Splunk Summary Index

In the Splunk Web UI:

### 4.1 Create Summary Index

1. Click **Settings** → **Indexes**
2. Click **New Index** (top right)
3. Fill in:
   - **Index Name:** `observable_catalog`
   - **Index Data Type:** Events
   - **Max Size:** 500 MB (or leave default)
4. Click **Save**

### 4.2 Add Sample Data

Create a sample log file:

```bash
# Create sample security events
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

# Upload to Splunk via Docker
docker cp sample_logs.json splunk:/opt/splunk/sample_logs.json

# Index the data
docker exec splunk /opt/splunk/bin/splunk add oneshot /opt/splunk/sample_logs.json \
  -sourcetype _json \
  -index main \
  -auth admin:Changeme123!
```

### 4.3 Verify Data in Splunk

In Splunk Web UI:
1. Click **Search & Reporting** (left sidebar)
2. Run search:
   ```
   index=main earliest=-24h | head 10
   ```
3. You should see 8 events with IPs, emails, hashes

### 4.4 Create Scheduled Search

1. In Splunk, go to **Settings** → **Searches, reports, and alerts**
2. Click **New Report**
3. Fill in:
   - **Title:** `Observable Catalog - Hourly Summary`
   - **Description:** `Aggregate observables for AWS export`
   - **Search:** Copy the entire query from `splunk_queries/observable_catalog.spl`

Here's the search (you can also copy from the file):

```spl
index=main earliest=-1h@h latest=@h
| eval indicator_type=case(
    isnotnull(dest_ip) OR isnotnull(src_ip), "ip",
    isnotnull(user_agent) AND user_agent!="", "ua",
    match(email, ".+@.+\\..+"), "email",
    match(hash, "^[A-Fa-f0-9]{32}$"), "md5",
    match(hash, "^[A-Fa-f0-9]{40}$"), "sha1",
    match(hash, "^[A-Fa-f0-9]{64}$"), "sha256",
    isnotnull(domain) AND domain!="", "domain",
    1=1, "other"
  )
| eval indicator=case(
    indicator_type="ip", coalesce(dest_ip, src_ip),
    indicator_type="email", email,
    indicator_type="ua", user_agent,
    indicator_type="md5", hash,
    indicator_type="sha1", hash,
    indicator_type="sha256", hash,
    indicator_type="domain", domain,
    true(), null()
  )
| where isnotnull(indicator) AND indicator!=""
| stats earliest(_time) as first_seen
        latest(_time) as last_seen
        count as hit_count
        values(src_ip) as src_ips
        values(dest_ip) as dest_ips
        values(user) as users
        values(sourcetype) as sourcetypes
        values(action) as actions
        dc(src_ip) as unique_src_ips
        dc(dest_ip) as unique_dest_ips
  by indicator indicator_type
| eval first_seen=strftime(first_seen,"%Y-%m-%dT%H:%M:%SZ"),
      last_seen=strftime(last_seen,"%Y-%m-%dT%H:%M:%SZ"),
      catalog_timestamp=strftime(now(),"%Y-%m-%dT%H:%M:%SZ")
| collect index=observable_catalog sourcetype=observable_summary
```

4. Click **Next** → **Save**
5. Click **Edit Schedule**:
   - Enable scheduling
   - **Cron Schedule:** `0 * * * *` (every hour at :00)
   - **Time Range:** `-1h@h to @h`
   - **Priority:** Default
6. Click **Save**

7. **Run the search manually now** to populate the summary index:
   - Click **Open in Search**
   - Change time range to "Last 24 hours"
   - Click the green **Search** button
   - Wait ~10 seconds for results

### 4.5 Verify Summary Index

Run this search in Splunk:
```
index=observable_catalog | head 10
```

You should see aggregated observables (IPs, emails, hashes).

---

## Step 5: Configure AWS CLI

```bash
# Check if AWS CLI is configured
aws sts get-caller-identity

# If not configured, run:
aws configure
# Enter your:
# - AWS Access Key ID
# - AWS Secret Access Key
# - Default region: us-east-1
# - Default output format: json
```

**Verify AWS access:**
```bash
aws sts get-caller-identity
```

Expected output:
```json
{
    "UserId": "AIDAXXXXXXXXXXXXXXXXX",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-username"
}
```

---

## Step 6: Create AWS Resources

### 6.1 Create DynamoDB Table

```bash
# Create table for observable catalog
python create_dynamodb_table.py --region us-east-1
```

Expected output:
```
Creating table observable_catalog...
Table observable_catalog created successfully!
```

**Verify table:**
```bash
aws dynamodb describe-table \
  --table-name observable_catalog \
  --region us-east-1 \
  --query 'Table.[TableName,TableStatus,ItemCount]'
```

### 6.2 Create S3 Bucket

```bash
# Replace with a unique bucket name (must be globally unique)
BUCKET_NAME="splunk-observables-$(date +%s)"

# Create bucket
aws s3 mb s3://${BUCKET_NAME} --region us-east-1

# Verify bucket
aws s3 ls | grep splunk-observables

# Save bucket name for later
echo "export S3_BUCKET=${BUCKET_NAME}" >> ~/.bashrc
echo "S3 Bucket: ${BUCKET_NAME}"
```

**Write down your bucket name!** You'll need it in the next step.

### 6.3 Store Splunk Credentials in Secrets Manager

```bash
# Create secret with Splunk credentials
aws secretsmanager create-secret \
  --name splunk/credentials \
  --description "Splunk API credentials for observable export" \
  --secret-string '{
    "host": "localhost",
    "port": "8089",
    "username": "admin",
    "password": "Changeme123!",
    "scheme": "https"
  }' \
  --region us-east-1
```

Expected output:
```json
{
    "ARN": "arn:aws:secretsmanager:us-east-1:...:secret:splunk/credentials-xxxxx",
    "Name": "splunk/credentials",
    "VersionId": "..."
}
```

---

## Step 7: Test the Export Script

### 7.1 Create Configuration File

```bash
# Create config.json (use your S3 bucket name from Step 6.2)
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

# Verify config
cat config.json
```

### 7.2 Run Manual Export Test

```bash
# Run the export script
python export_to_aws.py \
  --config config.json \
  --format all \
  --lookback 7

# This will:
# 1. Connect to Splunk on localhost
# 2. Query observable_catalog index
# 3. Export to DynamoDB and S3
```

Expected output:
```
2024-01-15 10:00:00 - INFO - Connected to Splunk successfully
2024-01-15 10:00:01 - INFO - S3 client initialized
2024-01-15 10:00:01 - INFO - DynamoDB client initialized
2024-01-15 10:00:02 - INFO - Executing Splunk search (lookback: 7 days)
2024-01-15 10:00:05 - INFO - Retrieved 5 observables from Splunk
2024-01-15 10:00:06 - INFO - Uploaded CSV to s3://...
2024-01-15 10:00:06 - INFO - Uploaded JSON to s3://...
2024-01-15 10:00:08 - INFO - Successfully exported to DynamoDB
2024-01-15 10:00:08 - INFO - Export completed successfully
```

---

## Step 8: Verify the Data

### 8.1 Check DynamoDB

```bash
# Query DynamoDB for IP 1.2.3.4
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
python test_ip_address.py
```

Expected output:
```
Testing DynamoDB IP address storage...
============================================================
Test IP Address: 1.2.3.4
Indicator Type: ip
Composite Key: ip#1.2.3.4
✓ Successfully wrote IP address to DynamoDB!
✓ Successfully retrieved IP address from DynamoDB!
```

### 8.2 Check S3

```bash
# List S3 objects
aws s3 ls s3://${S3_BUCKET}/observables/ --recursive --human-readable

# Download and view CSV
aws s3 cp s3://${S3_BUCKET}/observables/$(aws s3 ls s3://${S3_BUCKET}/observables/ --recursive | grep csv | head -1 | awk '{print $4}') observables.csv

# View first 10 lines
head -10 observables.csv
```

### 8.3 Query Data

**DynamoDB - Fast lookup:**
```bash
# Find a specific IP
aws dynamodb query \
  --table-name observable_catalog \
  --index-name indicator-type-index \
  --key-condition-expression "indicator_type = :type" \
  --expression-attribute-values '{":type": {"S": "ip"}}' \
  --region us-east-1 \
  --max-items 5
```

**Splunk - Historical query:**
```
index=observable_catalog indicator="1.2.3.4"
| stats min(strptime(first_seen,"%Y-%m-%dT%H:%M:%SZ")) as first_seen_epoch
        max(strptime(last_seen,"%Y-%m-%dT%H:%M:%SZ")) as last_seen_epoch
        sum(hit_count) as total_hits
| eval first_seen=strftime(first_seen_epoch,"%Y-%m-%dT%H:%M:%SZ"),
      last_seen=strftime(last_seen_epoch,"%Y-%m-%dT%H:%M:%SZ")
```

---

## Step 9: (Optional) Deploy Lambda for Automation

If you want fully automated hourly exports:

```bash
# Build Lambda deployment package
./deploy_lambda.sh

# Deploy with Terraform
cd terraform
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your S3 bucket name
nano terraform.tfvars
# Change: s3_bucket_name = "your-bucket-name-here"

# Deploy infrastructure
terraform init
terraform plan
terraform apply

# Terraform will create:
# - Lambda function
# - EventBridge schedule (hourly)
# - IAM roles
# - CloudWatch alarms
```

**Test Lambda:**
```bash
aws lambda invoke \
  --function-name splunk-observable-exporter \
  --region us-east-1 \
  response.json

cat response.json
```

---

## Step 10: Monitoring and Validation

### Check Splunk Search Performance

In Splunk Web UI:
```
index=_audit action=search savedsearch_name="Observable Catalog*"
| stats avg(total_run_time) as avg_seconds max(total_run_time) as max_seconds count
```

### Check AWS Costs

```bash
# Check estimated costs (may take 24hrs to appear)
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=SERVICE
```

Expected: ~$0 within free tier limits

---

## Troubleshooting

### Splunk Connection Failed

```bash
# Test Splunk API
curl -k -u admin:Changeme123! \
  https://localhost:8089/services/auth/login \
  -d username=admin \
  -d password=Changeme123!

# Check Splunk container
docker ps | grep splunk
docker logs splunk | tail -50
```

### DynamoDB Access Denied

```bash
# Verify AWS credentials
aws sts get-caller-identity

# Check IAM permissions (should have dynamodb:PutItem)
aws iam list-attached-user-policies --user-name $(aws sts get-caller-identity --query 'Arn' --output text | cut -d'/' -f2)
```

### No Data Found

```bash
# Check Splunk has data
# In Splunk Web UI:
index=main earliest=-24h | stats count

# Check summary index
index=observable_catalog | stats count

# If zero, re-run the scheduled search manually
```

### S3 Upload Failed

```bash
# Test S3 write permissions
echo "test" > test.txt
aws s3 cp test.txt s3://${S3_BUCKET}/test.txt
aws s3 rm s3://${S3_BUCKET}/test.txt
rm test.txt
```

---

## Cleanup

When you're done testing:

```bash
# Stop and remove Splunk container
docker stop splunk
docker rm splunk

# Delete DynamoDB table
aws dynamodb delete-table \
  --table-name observable_catalog \
  --region us-east-1

# Delete S3 bucket (and all contents)
aws s3 rb s3://${S3_BUCKET} --force --region us-east-1

# Delete Secrets Manager secret
aws secretsmanager delete-secret \
  --secret-id splunk/credentials \
  --force-delete-without-recovery \
  --region us-east-1

# If you deployed Lambda with Terraform:
cd terraform
terraform destroy

# Remove config file
rm config.json
```

---

## Success Checklist

- [ ] Splunk running in Docker (http://localhost:8000)
- [ ] Sample data indexed in Splunk
- [ ] Summary index created (`observable_catalog`)
- [ ] Scheduled search created and run manually
- [ ] AWS CLI configured
- [ ] DynamoDB table created
- [ ] S3 bucket created
- [ ] Secrets Manager secret created
- [ ] Export script ran successfully
- [ ] Data visible in DynamoDB
- [ ] Data visible in S3
- [ ] Can query specific IP addresses

---

## Next Steps

1. **Add more data**: Index additional logs in Splunk
2. **Adjust schedule**: Change search frequency based on volume
3. **Deploy Lambda**: Automate with hourly Lambda execution
4. **Create dashboards**: Build Splunk dashboards for quick lookups
5. **Set up alerts**: Alert on high-risk IPs or suspicious activity
6. **Integrate threat intel**: Enrich observables with threat feeds

---

## Support

- **Full Documentation**: See `README.md`
- **Testing Guide**: See `TESTING.md`
- **Architecture**: See `ARCHITECTURE.md`
- **Security**: See `SECURITY.md`
- **Performance**: See `SPLUNK_PERFORMANCE.md`

**GitHub Repository**: https://github.com/tacolopo/splunk-test

**Estimated Time**: 30 minutes  
**Cost**: $0 (within AWS Free Tier)

