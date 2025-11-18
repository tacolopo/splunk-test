# Production Deployment Guide: Splunk to AWS Observable Catalog

Complete step-by-step guide for deploying the Splunk observable catalog system in a production environment.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Planning & Architecture](#planning--architecture)
3. [Splunk Configuration](#splunk-configuration)
4. [AWS Setup](#aws-setup)
5. [Security Configuration](#security-configuration)
6. [Terraform Deployment](#terraform-deployment)
7. [Lambda Deployment](#lambda-deployment)
8. [Verification & Testing](#verification--testing)
9. [Querying Data](#querying-data)
10. [Monitoring & Maintenance](#monitoring--maintenance)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Access

- **Splunk Admin Access**: To create scheduled searches and summary indexes
- **AWS Admin Access**: To create resources (or IAM permissions for Lambda, DynamoDB, S3, Secrets Manager, EventBridge)
- **Network Access**: Lambda must be able to reach Splunk API (port 8089/443)

### Required Tools

```bash
# AWS CLI
aws --version  # Should be 2.x

# Terraform
terraform version  # Should be >= 1.0

# Python
python3 --version  # Should be 3.11+

# Git (optional, for version control)
git --version
```

### Required Information

- Splunk hostname/IP and port
- Splunk API username and password (or service account)
- AWS region for deployment
- Unique S3 bucket name (globally unique)
- Organization/team name for tagging

---

## Planning & Architecture

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION SPLUNK                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Raw Logs: proxy, email, edr, web, firewall         │  │
│  └────────────────────┬─────────────────────────────────┘  │
│                       │                                      │
│                       │ Scheduled Search (Hourly)           │
│                       │ Time: 0 * * * * (top of hour)      │
│                       │                                      │
│  ┌────────────────────▼─────────────────────────────────┐  │
│  │  Summary Index: observable_catalog                   │  │
│  │  - Aggregates observables                             │  │
│  │  - Stores: first_seen, last_seen, counts              │  │
│  └──────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            │ HTTPS (Port 8089)
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    AWS PRODUCTION                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Lambda Function (runs hourly)                       │  │
│  │  - Reads Splunk summary index                        │  │
│  │  - Updates DynamoDB (90-day TTL)                     │  │
│  │  - Updates S3 master file (daily)                    │  │
│  └───────┬───────────────────────────────┬──────────────┘  │
│          │                               │                  │
│  ┌───────▼────────┐            ┌─────────▼──────────┐      │
│  │   DynamoDB     │            │   S3 Bucket        │      │
│  │   (Hot Data)   │            │   (Cold Data)      │      │
│  │                │            │                    │      │
│  │ - 90-day TTL   │            │ - master.parquet  │      │
│  │ - Fast queries │            │ - Lifetime history │      │
│  │ - On-demand    │            │ - Daily updates    │      │
│  └────────────────┘            └────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Resource Requirements

**Splunk:**
- Summary index: `observable_catalog` (auto-created)
- Scheduled search runs hourly
- Estimated: 30 seconds - 5 minutes per run

**AWS:**
- DynamoDB: On-demand billing (scales automatically)
- S3: Standard storage (lifecycle to Glacier after 90 days)
- Lambda: 512MB memory, 15-minute timeout
- EventBridge: Hourly schedule

### Cost Estimate (Production)

**Small Organization (1,000 IPs/day):**
- DynamoDB: ~$5-10/month
- S3: ~$2-5/month
- Lambda: ~$1-2/month
- **Total: ~$10-20/month**

**Medium Organization (10,000 IPs/day):**
- DynamoDB: ~$15-30/month
- S3: ~$10-20/month
- Lambda: ~$5-10/month
- **Total: ~$30-60/month**

**Large Organization (100,000 IPs/day):**
- DynamoDB: ~$50-100/month
- S3: ~$40-80/month
- Lambda: ~$20-40/month
- **Total: ~$110-220/month**

---

## Splunk Configuration

### Step 1: Create Summary Index

**In Splunk Web UI:**

1. Go to **Settings** → **Indexes**
2. Click **New Index**
3. Configure:
   - **Index Name:** `observable_catalog`
   - **Index Type:** Events
   - **Max Data Size:** 500GB (adjust based on needs)
   - **Max Hot Buckets:** 10
   - **Max Warm Buckets:** 300
   - **Max Total Data Size:** 1000GB
4. Click **Save**

**Or via CLI:**

```bash
# SSH to Splunk server
splunk add index observable_catalog -maxDataSizeMB 512000 -maxHotBuckets 10 -maxWarmBuckets 300
```

### Step 2: Create Scheduled Search

**In Splunk Web UI:**

1. Go to **Settings** → **Searches, reports, and alerts**
2. Click **New Search**
3. **Name:** `Observable Catalog - Hourly Aggregation`
4. **Search:** Copy contents from `splunk_queries/observable_catalog.spl`

```spl
index=proxy OR index=email OR index=edr OR index=web OR index=firewall earliest=-1h@h latest=@h
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

5. **Schedule:**
   - Enable scheduling: **Yes**
   - **Cron Schedule:** `0 * * * *` (every hour at :00)
   - **Time Range:** `-1h@h to @h`
   - **Priority:** Default
   - **Run as:** Service account user (recommended)

6. **Summary Indexing:**
   - Enable summary indexing: **Yes**
   - **Summary Index:** `observable_catalog`
   - **Sourcetype:** `observable_summary`

7. Click **Save**

### Step 3: Create API User (Service Account)

**Best Practice:** Use a dedicated service account, not a personal account.

1. Go to **Settings** → **Access controls** → **Users**
2. Click **New User**
3. Configure:
   - **Full Name:** `splunk-aws-exporter`
   - **User Name:** `splunk-aws-exporter`
   - **Email:** (optional)
   - **Password:** Generate strong password (store securely)
   - **Roles:** `power` (minimum required)
4. Click **Save**

**Or via CLI:**

```bash
splunk add user splunk-aws-exporter -password "STRONG_PASSWORD_HERE" -role power -full-name "Splunk AWS Exporter Service Account"
```

### Step 4: Verify Summary Index Has Data

**Wait 1-2 hours after creating scheduled search, then verify:**

```spl
index=observable_catalog | head 10
```

You should see aggregated observables. If empty:
- Check scheduled search ran successfully
- Verify indexes (proxy, email, etc.) have data
- Check search job status

---

## AWS Setup

### Step 1: Configure AWS CLI

```bash
# Configure AWS credentials
aws configure

# Enter:
# AWS Access Key ID: [Your access key]
# AWS Secret Access Key: [Your secret key]
# Default region name: us-east-1
# Default output format: json

# Verify configuration
aws sts get-caller-identity
```

**For Production:** Use IAM roles instead of access keys when possible.

### Step 2: Create IAM User for Terraform (Optional but Recommended)

**If using Terraform with IAM user (not role):**

1. Go to **IAM Console** → **Users** → **Create user**
2. **User name:** `terraform-splunk-exporter`
3. **Access type:** Programmatic access
4. **Permissions:** Attach policy `AdministratorAccess` (or custom policy with required permissions)
5. **Download credentials** (CSV file) - store securely

**Required IAM Permissions:**
- `dynamodb:*`
- `s3:*`
- `lambda:*`
- `iam:*` (for creating roles)
- `events:*` (EventBridge)
- `logs:*` (CloudWatch)
- `secretsmanager:*`
- `cloudwatch:*`

### Step 3: Prepare Project Files

**Clone or download the project:**

```bash
cd /opt/splunk-aws-exporter  # Or your preferred location
# Copy project files here
```

**Required files:**
- `export_to_aws.py` - Main export script
- `lambda_function.py` - Lambda handler
- `splunk_queries/` - Directory with all .spl files
- `requirements.txt` - Python dependencies
- `terraform/` - Terraform configuration
- `deploy_lambda.sh` - Lambda packaging script

**Verify files exist:**

```bash
ls -la export_to_aws.py lambda_function.py requirements.txt
ls -la splunk_queries/*.spl
ls -la terraform/*.tf
```

---

## Security Configuration

### Step 1: Store Splunk Credentials in AWS Secrets Manager

**DO NOT** store credentials in code or config files!

**Create secret:**

```bash
aws secretsmanager create-secret \
  --name splunk/credentials \
  --description "Splunk API credentials for observable export" \
  --secret-string '{
    "host": "splunk.production.example.com",
    "port": "8089",
    "username": "splunk-aws-exporter",
    "password": "YOUR_SECURE_PASSWORD_HERE",
    "scheme": "https"
  }' \
  --region us-east-1 \
  --tags Key=Environment,Value=Production Key=Application,Value=SplunkExporter
```

**Verify secret created:**

```bash
aws secretsmanager describe-secret \
  --secret-id splunk/credentials \
  --region us-east-1
```

**Note:** The password should NOT be visible in the output. Only metadata is shown.

### Step 2: Enable Secret Rotation (Optional but Recommended)

For production, consider setting up automatic password rotation:

```bash
aws secretsmanager rotate-secret \
  --secret-id splunk/credentials \
  --rotation-lambda-arn arn:aws:lambda:us-east-1:ACCOUNT:function:rotate-splunk-password
```

### Step 3: Restrict Secret Access

**Update Lambda IAM role** (done automatically by Terraform) to only allow Lambda to read the secret.

**Verify IAM policy includes:**

```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue"
  ],
  "Resource": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:splunk/credentials-*"
}
```

### Step 4: Secure S3 Bucket

**Enable versioning** (done by Terraform):
- Protects against accidental deletion
- Allows recovery of previous versions

**Enable encryption** (done by Terraform):
- Server-side encryption with AES-256

**Restrict public access** (verify):
```bash
aws s3api get-public-access-block \
  --bucket your-bucket-name
```

Should show all blocks enabled.

**Add bucket policy** (if needed for cross-account access):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyPublicAccess",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::your-bucket-name/*",
        "arn:aws:s3:::your-bucket-name"
      ],
      "Condition": {
        "Bool": {
          "aws:PrincipalServiceName": "false"
        }
      }
    }
  ]
}
```

---

## Terraform Deployment

### Step 1: Configure Terraform Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

**Edit `terraform.tfvars`:**

```hcl
aws_region          = "us-east-1"
environment         = "production"
s3_bucket_name      = "your-org-splunk-observables-PRODUCTION-UNIQUE-ID"
dynamodb_table_name = "observable_catalog"
lookback_days       = 1
schedule_expression = "rate(1 hour)"  # Or "cron(0 * * * ? *)" for hourly at :00
```

**Important:**
- `s3_bucket_name` must be globally unique
- Use your organization name + environment + unique ID
- Example: `acme-corp-splunk-observables-prod-2024`

### Step 2: Build Lambda Deployment Packages

**From project root:**

```bash
cd /opt/splunk-aws-exporter  # Or your project location
chmod +x deploy_lambda.sh
./deploy_lambda.sh
```

**This creates:**
- `lambda_layer.zip` - Python dependencies (~50-100MB)
- `lambda_function.zip` - Application code (~500KB-2MB)

**Move to terraform directory:**

```bash
mv lambda_layer.zip terraform/
mv lambda_function.zip terraform/
```

**Verify packages:**

```bash
cd terraform
ls -lh lambda_*.zip
```

### Step 3: Initialize Terraform

```bash
cd terraform
terraform init
```

**Expected output:**
```
Initializing the backend...
Initializing provider plugins...
Terraform has been successfully initialized!
```

### Step 4: Review Deployment Plan

```bash
terraform plan
```

**Review the plan carefully:**
- Verify S3 bucket name is correct
- Check DynamoDB table name
- Confirm Lambda function name
- Review IAM permissions
- Verify schedule expression

**Expected resources:**
- 1x S3 bucket
- 1x DynamoDB table
- 1x Lambda function
- 1x Lambda layer
- 1x IAM role
- 1x IAM policy
- 1x EventBridge rule
- 1x CloudWatch log group
- 1x CloudWatch alarm
- 1x Secrets Manager secret (if creating new)

### Step 5: Deploy Infrastructure

```bash
terraform apply
```

**Type `yes` when prompted.**

**Expected time:** 3-5 minutes

**Save outputs:**

```bash
terraform output > terraform_outputs.txt
```

**Important outputs:**
- `s3_bucket_name` - Your S3 bucket
- `dynamodb_table_name` - DynamoDB table name
- `lambda_function_name` - Lambda function name
- `lambda_function_arn` - Lambda ARN
- `secrets_manager_secret_arn` - Secret ARN

### Step 6: Verify Resources Created

**Check S3 bucket:**

```bash
BUCKET=$(terraform output -raw s3_bucket_name)
aws s3 ls s3://$BUCKET/
```

**Check DynamoDB table:**

```bash
TABLE=$(terraform output -raw dynamodb_table_name)
aws dynamodb describe-table --table-name $TABLE --region us-east-1
```

**Check Lambda function:**

```bash
FUNCTION=$(terraform output -raw lambda_function_name)
aws lambda get-function --function-name $FUNCTION --region us-east-1
```

**Check EventBridge rule:**

```bash
aws events describe-rule --name splunk-observable-export-hourly --region us-east-1
```

---

## Lambda Deployment

### Step 1: Verify Lambda Package Upload

Terraform automatically uploads the Lambda packages. Verify:

```bash
FUNCTION=$(terraform output -raw lambda_function_name)
aws lambda get-function --function-name $FUNCTION --region us-east-1 | jq '.Code.Location'
```

### Step 2: Test Lambda Function Manually

**Invoke Lambda:**

```bash
FUNCTION=$(terraform output -raw lambda_function_name)
aws lambda invoke \
  --function-name $FUNCTION \
  --region us-east-1 \
  --payload '{}' \
  response.json

cat response.json
```

**Expected response:**

```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Export completed successfully\", ...}"
}
```

**Check logs:**

```bash
aws logs tail /aws/lambda/$FUNCTION --follow --region us-east-1
```

**Look for:**
- ✅ "Connected to Splunk successfully"
- ✅ "Retrieved X observables from Splunk"
- ✅ "Successfully exported to DynamoDB"
- ✅ "S3 master file updated" (first run) or "already updated today" (subsequent runs)

### Step 3: Verify EventBridge Schedule

**Check rule is enabled:**

```bash
aws events describe-rule \
  --name splunk-observable-export-hourly \
  --region us-east-1 \
  --query 'State' \
  --output text
```

Should return: `ENABLED`

**Check targets:**

```bash
aws events list-targets-by-rule \
  --rule splunk-observable-export-hourly \
  --region us-east-1
```

Should show Lambda function as target.

### Step 4: Wait for First Scheduled Run

**Lambda runs hourly.** Wait for the next scheduled run, then check:

```bash
# Check recent invocations
aws lambda get-function \
  --function-name $FUNCTION \
  --region us-east-1 \
  --query 'Configuration.LastModified'

# Check logs for last execution
aws logs tail /aws/lambda/$FUNCTION --since 2h --region us-east-1
```

---

## Verification & Testing

### Step 1: Verify DynamoDB Data

**Check item count:**

```bash
TABLE=$(terraform output -raw dynamodb_table_name)
aws dynamodb scan \
  --table-name $TABLE \
  --select COUNT \
  --region us-east-1
```

**Get sample items:**

```bash
aws dynamodb scan \
  --table-name $TABLE \
  --limit 5 \
  --region us-east-1 | jq '.Items[] | {indicator: .indicator.S, type: .indicator_type.S, first_seen: .first_seen.S, last_seen: .last_seen.S, total_hits: .total_hits.N}'
```

**Query specific IP:**

```bash
aws dynamodb get-item \
  --table-name $TABLE \
  --key '{"indicator_key": {"S": "ip#8.8.8.8"}}' \
  --region us-east-1 | jq '.Item'
```

### Step 2: Verify S3 Master File

**Check master file exists:**

```bash
BUCKET=$(terraform output -raw s3_bucket_name)
aws s3 ls s3://$BUCKET/observables/master.parquet --region us-east-1
```

**Download and inspect:**

```bash
aws s3 cp s3://$BUCKET/observables/master.parquet ./master.parquet --region us-east-1

# Inspect with Python
python3 << 'EOF'
import pandas as pd
df = pd.read_parquet('master.parquet')
print(f"Total records: {len(df)}")
print(f"\nColumns: {df.columns.tolist()}")
print(f"\nFirst few rows:")
print(df.head())
print(f"\nSample IP record:")
ip_record = df[df['indicator_type'] == 'ip'].iloc[0] if len(df[df['indicator_type'] == 'ip']) > 0 else None
if ip_record is not None:
    print(ip_record.to_dict())
EOF
```

**Verify merge logic:**

Run Lambda twice in the same day - second run should skip S3 update:
```bash
aws lambda invoke --function-name $FUNCTION response.json
cat response.json
# Check logs - should see "S3 master file already updated today, skipping"
```

### Step 3: Verify Data Accuracy

**Check first_seen/last_seen are preserved:**

1. Note an IP's `first_seen` and `last_seen` in DynamoDB
2. Wait for next Lambda run
3. Verify values are preserved (not overwritten)
4. Verify `total_hits` accumulates correctly

**Check S3 master file has lifetime data:**

1. Check an IP that was seen 30 days ago
2. Verify `first_seen` in S3 master file matches original date
3. Verify `total_hits` reflects lifetime total

---

## Querying Data

### Querying DynamoDB

#### Single IP Lookup (Fast - < 5ms)

```bash
TABLE=$(terraform output -raw dynamodb_table_name)

# Get specific IP
aws dynamodb get-item \
  --table-name $TABLE \
  --key '{"indicator_key": {"S": "ip#8.8.8.8"}}' \
  --region us-east-1 | jq '.Item'

# Parse output
aws dynamodb get-item \
  --table-name $TABLE \
  --key '{"indicator_key": {"S": "ip#8.8.8.8"}}' \
  --region us-east-1 | jq '{
    indicator: .Item.indicator.S,
    type: .Item.indicator_type.S,
    first_seen: .Item.first_seen.S,
    last_seen: .Item.last_seen.S,
    total_hits: .Item.total_hits.N,
    days_seen: .Item.days_seen.N
  }'
```

#### Query by Type (Using GSI)

```bash
# Get all IPs seen in last 7 days
aws dynamodb query \
  --table-name $TABLE \
  --index-name indicator-type-index \
  --key-condition-expression "indicator_type = :type AND last_seen >= :date" \
  --expression-attribute-values '{
    ":type": {"S": "ip"},
    ":date": {"S": "2025-11-11T00:00:00Z"}
  }' \
  --region us-east-1 | jq '.Items[] | {indicator: .indicator.S, last_seen: .last_seen.S, total_hits: .total_hits.N}'
```

#### Scan All (Use Sparingly - Expensive)

```bash
# Get all observables (limit to avoid high costs)
aws dynamodb scan \
  --table-name $TABLE \
  --limit 100 \
  --region us-east-1 | jq '.Items[] | {indicator: .indicator.S, type: .indicator_type.S}'
```

#### Using Python SDK

```python
import boto3
import json
from datetime import datetime, timedelta

dynamodb = boto3.client('dynamodb', region_name='us-east-1')
table_name = 'observable_catalog'

# Get specific IP
def get_ip(ip_address):
    response = dynamodb.get_item(
        TableName=table_name,
        Key={'indicator_key': {'S': f'ip#{ip_address}'}}
    )
    if 'Item' in response:
        item = response['Item']
        return {
            'indicator': item['indicator']['S'],
            'first_seen': item['first_seen']['S'],
            'last_seen': item['last_seen']['S'],
            'total_hits': int(item['total_hits']['N']),
            'days_seen': float(item['days_seen']['N'])
        }
    return None

# Query recent IPs
def get_recent_ips(days=7):
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat() + 'Z'
    response = dynamodb.query(
        TableName=table_name,
        IndexName='indicator-type-index',
        KeyConditionExpression='indicator_type = :type AND last_seen >= :date',
        ExpressionAttributeValues={
            ':type': {'S': 'ip'},
            ':date': {'S': cutoff_date}
        }
    )
    return response['Items']

# Usage
ip_info = get_ip('8.8.8.8')
print(json.dumps(ip_info, indent=2))
```

### Querying S3 Master File with Athena

#### Step 1: Create Athena Database

**In AWS Athena Console:**

1. Go to: https://console.aws.amazon.com/athena/
2. Click **Settings** → Set **Query result location** to: `s3://your-bucket-name/athena-results/`
3. Click **Save**
4. Go to **Editor** tab

**Create database:**

```sql
CREATE DATABASE IF NOT EXISTS splunk_observables
```

#### Step 2: Create Athena Table

**Drop existing table (if any):**

```sql
DROP TABLE IF EXISTS splunk_observables.observables
```

**Create table pointing to master file:**

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS splunk_observables.observables (
  actions string,
  dest_ips string,
  export_timestamp string,
  first_seen string,
  indicator string,
  indicator_type string,
  last_seen string,
  sourcetypes string,
  src_ips string,
  total_hits bigint,
  types string,
  unique_dest_ips bigint,
  unique_src_ips bigint,
  users string,
  days_seen double
)
STORED AS PARQUET
LOCATION 's3://your-bucket-name/observables/master.parquet'
TBLPROPERTIES ('parquet.compress'='SNAPPY')
```

**Note:** No partitions needed since it's a single master file.

#### Step 3: Query Examples

**Get all IPs:**

```sql
SELECT indicator, indicator_type, first_seen, last_seen, total_hits, days_seen
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
ORDER BY total_hits DESC
LIMIT 100
```

**Find specific IP:**

```sql
SELECT indicator, first_seen, last_seen, total_hits, days_seen, src_ips, dest_ips
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
  AND indicator = '8.8.8.8'
```

**Top 10 most active IPs:**

```sql
SELECT indicator, total_hits, days_seen, first_seen, last_seen
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
ORDER BY total_hits DESC
LIMIT 10
```

**IPs seen for more than 30 days:**

```sql
SELECT indicator, first_seen, last_seen, days_seen, total_hits
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
  AND days_seen > 30
ORDER BY days_seen DESC
```

**IPs with most unique source IPs:**

```sql
SELECT indicator, unique_src_ips, unique_dest_ips, total_hits
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
ORDER BY unique_src_ips DESC
LIMIT 20
```

**Time-based analysis:**

```sql
SELECT 
  indicator,
  first_seen,
  last_seen,
  CAST(first_seen AS timestamp) as first_seen_ts,
  CAST(last_seen AS timestamp) as last_seen_ts,
  date_diff('day', CAST(first_seen AS timestamp), CAST(last_seen AS timestamp)) as days_between,
  total_hits
FROM splunk_observables.observables
WHERE indicator_type = 'ip'
  AND CAST(first_seen AS timestamp) >= timestamp '2025-01-01 00:00:00'
ORDER BY total_hits DESC
```

#### Step 4: Download Results

**In Athena Console:**
- Click **Download results** button
- Choose CSV or JSON format

**Or use AWS CLI:**

```bash
# Get query execution ID from Athena console
QUERY_ID="your-query-execution-id"

aws athena get-query-results \
  --query-execution-id $QUERY_ID \
  --region us-east-1 > results.json
```

### Querying S3 Master File Directly (Python)

```python
import boto3
import pandas as pd
from io import BytesIO

s3 = boto3.client('s3', region_name='us-east-1')
bucket = 'your-bucket-name'
key = 'observables/master.parquet'

# Download and read Parquet file
obj = s3.get_object(Bucket=bucket, Key=key)
df = pd.read_parquet(BytesIO(obj['Body'].read()))

# Query data
print(f"Total records: {len(df)}")
print(f"\nIPs only:")
ips = df[df['indicator_type'] == 'ip']
print(f"  Count: {len(ips)}")
print(f"  Top 10 by total_hits:")
print(ips.nlargest(10, 'total_hits')[['indicator', 'total_hits', 'first_seen', 'last_seen']])

# Find specific IP
ip_record = df[(df['indicator_type'] == 'ip') & (df['indicator'] == '8.8.8.8')]
if len(ip_record) > 0:
    print(f"\nFound IP 8.8.8.8:")
    print(ip_record.iloc[0].to_dict())
```

---

## Monitoring & Maintenance

### CloudWatch Dashboards

**Create dashboard:**

1. Go to **CloudWatch** → **Dashboards** → **Create dashboard**
2. Add widgets for:
   - Lambda invocations (line chart)
   - Lambda errors (number)
   - Lambda duration (line chart)
   - DynamoDB consumed read capacity (line chart)
   - DynamoDB consumed write capacity (line chart)
   - S3 bucket size (line chart)

**Or use AWS CLI:**

```bash
# Get Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=splunk-observable-exporter \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum \
  --region us-east-1
```

### CloudWatch Alarms

**Alarms automatically created:**
- Lambda errors (alerts on any error)

**Create additional alarms:**

```bash
# Lambda duration alarm
aws cloudwatch put-metric-alarm \
  --alarm-name splunk-exporter-duration-high \
  --alarm-description "Alert when Lambda takes too long" \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Average \
  --period 300 \
  --threshold 600000 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions Name=FunctionName,Value=splunk-observable-exporter \
  --region us-east-1

# DynamoDB throttling alarm
aws cloudwatch put-metric-alarm \
  --alarm-name dynamodb-throttles \
  --alarm-description "Alert on DynamoDB throttling" \
  --metric-name UserErrors \
  --namespace AWS/DynamoDB \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions Name=TableName,Value=observable_catalog \
  --region us-east-1
```

### Log Monitoring

**View recent logs:**

```bash
FUNCTION=$(terraform output -raw lambda_function_name)
aws logs tail /aws/lambda/$FUNCTION --since 24h --region us-east-1
```

**Search for errors:**

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/splunk-observable-exporter \
  --filter-pattern "ERROR" \
  --start-time $(date -d '24 hours ago' +%s)000 \
  --region us-east-1
```

**Export logs to S3 (for long-term retention):**

```bash
aws logs create-export-task \
  --log-group-name /aws/lambda/splunk-observable-exporter \
  --from $(date -d '7 days ago' +%s)000 \
  --to $(date +%s)000 \
  --destination s3://your-bucket-name/logs/ \
  --destination-prefix lambda-logs/ \
  --region us-east-1
```

### Regular Maintenance Tasks

#### Weekly

1. **Review CloudWatch alarms** - Check for any alerts
2. **Review Lambda logs** - Look for errors or warnings
3. **Check DynamoDB metrics** - Verify no throttling
4. **Verify S3 master file** - Check it's updating daily

#### Monthly

1. **Review costs** - Check AWS Cost Explorer
2. **Verify data accuracy** - Spot check DynamoDB vs S3
3. **Review Splunk performance** - Check scheduled search performance
4. **Update dependencies** - Check for security updates

#### Quarterly

1. **Review retention policies** - Adjust DynamoDB TTL if needed
2. **Optimize S3 lifecycle** - Review Glacier transition policies
3. **Capacity planning** - Review growth trends
4. **Security audit** - Review IAM permissions

### Backup Strategy

**DynamoDB:**
- Point-in-time recovery enabled (by Terraform)
- 35-day retention
- Manual backups: `aws dynamodb create-backup --table-name observable_catalog --backup-name backup-YYYY-MM-DD`

**S3:**
- Versioning enabled (by Terraform)
- Lifecycle to Glacier after 90 days
- Cross-region replication (optional, configure manually)

**Terraform State:**
- Store in S3 backend (recommended for teams)
- Enable versioning on state bucket
- Use state locking (DynamoDB table)

---

## Troubleshooting

### Lambda Not Running

**Check EventBridge rule:**

```bash
aws events describe-rule --name splunk-observable-export-hourly --region us-east-1
```

**Check Lambda permissions:**

```bash
aws lambda get-policy --function-name splunk-observable-exporter --region us-east-1
```

**Manually invoke:**

```bash
aws lambda invoke --function-name splunk-observable-exporter --payload '{}' response.json
cat response.json
```

### Lambda Errors

**Common errors:**

1. **Splunk connection failed:**
   - Check Secrets Manager secret is correct
   - Verify Splunk API is accessible from Lambda
   - Check firewall rules

2. **DynamoDB permission denied:**
   - Verify IAM role has `dynamodb:UpdateItem`, `dynamodb:Scan` permissions
   - Check table name matches

3. **S3 permission denied:**
   - Verify IAM role has `s3:GetObject`, `s3:PutObject` permissions
   - Check bucket name matches

4. **Lambda timeout:**
   - Increase timeout in Terraform (max 15 minutes)
   - Reduce `lookback_days` in terraform.tfvars
   - Check Splunk query performance

**View error details:**

```bash
aws logs tail /aws/lambda/splunk-observable-exporter --since 1h --filter-pattern "ERROR"
```

### No Data in DynamoDB

**Check Splunk summary index:**

```spl
index=observable_catalog | head 10
```

**Check Lambda logs:**

```bash
aws logs tail /aws/lambda/splunk-observable-exporter --since 24h
```

Look for:
- "Retrieved X observables from Splunk" (should be > 0)
- "Successfully exported to DynamoDB"

**Verify Splunk query:**

Run the query manually in Splunk to verify it returns data.

### S3 Master File Not Updating

**Check if file exists:**

```bash
aws s3 ls s3://your-bucket/observables/master.parquet
```

**Check last modified:**

```bash
aws s3api head-object --bucket your-bucket --key observables/master.parquet
```

**Check Lambda logs for S3 update:**

```bash
aws logs tail /aws/lambda/splunk-observable-exporter --since 24h | grep -i "S3 master"
```

Should see either:
- "S3 master file updated with merged DynamoDB data" (first run of day)
- "S3 master file already updated today, skipping" (subsequent runs)

### DynamoDB TTL Not Working

**Verify TTL is enabled:**

```bash
aws dynamodb describe-time-to-live --table-name observable_catalog --region us-east-1
```

Should show: `"TimeToLiveStatus": "ENABLED"`

**Check items have ttl field:**

```bash
aws dynamodb scan --table-name observable_catalog --limit 1 --region us-east-1 | jq '.Items[0].ttl'
```

Should show a numeric timestamp.

### High Costs

**DynamoDB costs:**
- Switch to on-demand billing (already configured)
- Increase TTL to reduce storage
- Review write patterns

**S3 costs:**
- Enable lifecycle policies (already configured)
- Review storage class transitions
- Consider Glacier for older data

**Lambda costs:**
- Reduce execution frequency (hourly → daily)
- Optimize code execution time
- Review memory allocation

---

## Security Best Practices

### 1. Credential Management

✅ **DO:**
- Use AWS Secrets Manager for Splunk credentials
- Rotate credentials regularly
- Use service accounts (not personal accounts)
- Enable MFA for AWS console access
- Use IAM roles instead of access keys when possible

❌ **DON'T:**
- Store credentials in code
- Commit credentials to git
- Use personal Splunk accounts
- Share AWS access keys
- Use root AWS account

### 2. Network Security

✅ **DO:**
- Use HTTPS for Splunk API (scheme: "https")
- Restrict Lambda VPC if needed
- Use security groups to limit access
- Enable VPC endpoints for AWS services

❌ **DON'T:**
- Use HTTP for Splunk API
- Expose Splunk API publicly
- Allow unrestricted network access

### 3. Data Protection

✅ **DO:**
- Enable encryption at rest (S3, DynamoDB)
- Enable encryption in transit (HTTPS)
- Use least privilege IAM policies
- Enable S3 versioning
- Enable DynamoDB point-in-time recovery

❌ **DON'T:**
- Store sensitive data unencrypted
- Use public S3 buckets
- Grant excessive IAM permissions
- Disable logging

### 4. Monitoring & Auditing

✅ **DO:**
- Enable CloudWatch logging
- Set up CloudWatch alarms
- Review logs regularly
- Monitor for unusual activity
- Use AWS CloudTrail for API auditing

❌ **DON'T:**
- Disable logging
- Ignore error alarms
- Skip security reviews

---

## File Reference Checklist

### Required Files for Deployment

**Project Root:**
- [ ] `export_to_aws.py` - Main export script
- [ ] `lambda_function.py` - Lambda handler
- [ ] `requirements.txt` - Python dependencies
- [ ] `deploy_lambda.sh` - Lambda packaging script

**Splunk Queries:**
- [ ] `splunk_queries/observable_catalog.spl` - Scheduled search query
- [ ] `splunk_queries/export_all_observables.spl` - Export query

**Terraform:**
- [ ] `terraform/main.tf` - Main infrastructure
- [ ] `terraform/variables.tf` - Variable definitions
- [ ] `terraform/outputs.tf` - Output definitions
- [ ] `terraform/terraform.tfvars` - Your configuration (create from example)

**Deployment Packages (generated):**
- [ ] `terraform/lambda_layer.zip` - Dependencies
- [ ] `terraform/lambda_function.zip` - Application code

### Files NOT to Upload/Commit

❌ **Never commit:**
- `terraform/terraform.tfvars` (contains sensitive values)
- `config.json` (if using local config)
- AWS credentials
- Splunk passwords
- `.terraform/` directory
- `*.tfstate` files
- `*.tfstate.backup` files

**Add to `.gitignore`:**

```
terraform/terraform.tfvars
terraform/*.tfstate
terraform/*.tfstate.backup
terraform/.terraform/
terraform/lambda_*.zip
config.json
*.log
```

---

## Quick Reference Commands

### Deployment

```bash
# Build Lambda packages
./deploy_lambda.sh
mv lambda_*.zip terraform/

# Deploy with Terraform
cd terraform
terraform init
terraform plan
terraform apply
```

### Verification

```bash
# Test Lambda
aws lambda invoke --function-name splunk-observable-exporter response.json

# Check logs
aws logs tail /aws/lambda/splunk-observable-exporter --follow

# Check DynamoDB
aws dynamodb scan --table-name observable_catalog --limit 5

# Check S3
aws s3 ls s3://your-bucket/observables/master.parquet
```

### Querying

```bash
# Get IP from DynamoDB
aws dynamodb get-item --table-name observable_catalog --key '{"indicator_key": {"S": "ip#8.8.8.8"}}'

# Query S3 with Athena (in Athena console)
SELECT * FROM splunk_observables.observables WHERE indicator = '8.8.8.8' LIMIT 10
```

---

## Support & Resources

### Documentation Files

- `PRODUCTION_DEPLOYMENT.md` - This file (complete guide)
- `terraform/DEPLOYMENT.md` - Terraform-specific deployment
- `LOCAL_MACHINE_GUIDE.md` - Local testing guide
- `README.md` - Project overview
- `ARCHITECTURE.md` - Architecture details

### AWS Resources

- [Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [S3 Security Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html)

### Splunk Resources

- [Summary Indexing](https://docs.splunk.com/Documentation/Splunk/latest/Knowledge/Aboutsummaryindexing)
- [Scheduled Searches](https://docs.splunk.com/Documentation/Splunk/latest/Knowledge/Managescheduledsearches)

---

## Conclusion

You now have a complete production deployment of the Splunk observable catalog system. The system will:

✅ **Automatically export** observables from Splunk hourly  
✅ **Store recent data** in DynamoDB (90-day TTL)  
✅ **Maintain lifetime history** in S3 master file (daily updates)  
✅ **Preserve first_seen/last_seen** across all time  
✅ **Accumulate total_hits** correctly  
✅ **Scale automatically** with your data volume  

**Next Steps:**
1. Monitor first few Lambda executions
2. Verify data accuracy in DynamoDB and S3
3. Set up CloudWatch dashboards
4. Configure alerting for your team
5. Document your organization-specific procedures

**Remember:**
- Review logs weekly
- Monitor costs monthly
- Update credentials quarterly
- Test disaster recovery procedures

Good luck with your production deployment! 🚀

