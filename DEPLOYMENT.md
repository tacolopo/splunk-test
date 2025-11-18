# Automated Deployment Guide

This guide covers deploying the fully automated Splunk observable catalog solution using AWS Lambda.

## Architecture Decision: DynamoDB + S3

**Recommendation: Use BOTH DynamoDB and S3**

### DynamoDB (Hot Data - 90 Days)
- **Purpose:** Fast operational lookups for recent IP addresses
- **Use Case:** "Has this IP been seen in the last 90 days?"
- **Features:** 
  - Millisecond query latency
  - Automatic TTL expiration after 90 days
  - Pay-per-request scaling
  - Perfect for incident response

### S3 (Cold Data - Unlimited)
- **Purpose:** Long-term historical storage and analytics
- **Use Case:** "Show me all IPs seen in 2023" or "Generate annual report"
- **Features:**
  - Unlimited retention
  - CSV + JSON formats
  - Query with Athena
  - Lifecycle policies to Glacier
  - Much cheaper per GB

### Cost Comparison

**DynamoDB Only (1M IPs):**
- Storage: ~$2.50/GB × 5GB = $12.50/month
- Writes: ~$1.25 per million writes
- **Total:** ~$50-100/month

**S3 Only (1M IPs/day for 1 year):**
- S3 Standard: ~$0.023/GB × 1,825GB = $42/month
- S3 Glacier (after 90 days): ~$0.004/GB × 1,640GB = $6.56/month
- **Total:** ~$50/month

**DynamoDB + S3 (Recommended):**
- DynamoDB (90 days): $15/month
- S3 (all history): $25/month
- **Total:** ~$40/month + query costs

## Prerequisites

- AWS CLI configured
- Terraform installed (or use AWS Console)
- Python 3.11+
- Splunk credentials

## Deployment Steps

### 1. Store Splunk Credentials in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name splunk/credentials \
  --description "Splunk API credentials" \
  --secret-string '{
    "host": "splunk.example.com",
    "port": "8089",
    "username": "api_user",
    "password": "your_secure_password",
    "scheme": "https"
  }' \
  --region us-east-1
```

### 2. Build Lambda Deployment Packages

```bash
cd "/home/user/Documents/Splunk to AWS Project"
./deploy_lambda.sh
```

This creates:
- `lambda_layer.zip` - Python dependencies
- `lambda_function.zip` - Application code

### 3. Deploy with Terraform (Recommended)

```bash
cd terraform

cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
```hcl
aws_region          = "us-east-1"
environment         = "production"
s3_bucket_name      = "your-org-splunk-observables"
dynamodb_table_name = "observable_catalog"
lookback_days       = 1
schedule_expression = "rate(1 hour)"
```

Deploy:
```bash
terraform init
terraform plan
terraform apply
```

### 4. Configure Splunk Summary Index

In Splunk:

1. **Create Summary Index:**
   - Settings → Indexes → New Index
   - Name: `observable_catalog`
   - Max size: 10GB (or as needed)

2. **Create Scheduled Search:**
   - Settings → Searches, reports, and alerts → New Report
   - Title: `Observable Catalog - Hourly Summary`
   - Schedule: `Cron: 0 * * * *` (top of every hour)
   - Earliest: `-1h@h`
   - Latest: `@h`
   - Copy query from `splunk_queries/observable_catalog.spl`
   - Enable "Summary indexing"
   - Select index: `observable_catalog`
   - Priority: Default or Low

3. **Performance Settings (Important!):**
   - Search window: 1 hour (adjust based on volume)
   - Schedule during off-peak hours if possible
   - Set appropriate priority
   - See `SPLUNK_PERFORMANCE.md` for details

### 5. Test the Pipeline

#### Test Splunk Search
```spl
index=observable_catalog earliest=-1h
| head 10
```

#### Test Lambda Locally
```bash
export SPLUNK_SECRET_NAME="splunk/credentials"
export S3_BUCKET="your-org-splunk-observables"
export DYNAMODB_TABLE="observable_catalog"
export AWS_REGION="us-east-1"

python -c "
import lambda_function
result = lambda_function.lambda_handler({}, None)
print(result)
"
```

#### Test Lambda in AWS
```bash
aws lambda invoke \
  --function-name splunk-observable-exporter \
  --payload '{}' \
  --region us-east-1 \
  response.json

cat response.json
```

### 6. Verify Data in DynamoDB

```bash
aws dynamodb get-item \
  --table-name observable_catalog \
  --key '{"indicator_key": {"S": "ip#1.2.3.4"}}' \
  --region us-east-1
```

Or use the test script:
```bash
python test_ip_address.py
```

### 7. Verify Data in S3

```bash
aws s3 ls s3://your-org-splunk-observables/observables/ --recursive
```

Download and inspect:
```bash
aws s3 cp s3://your-org-splunk-observables/observables/date=2024-01-15/observables_20240115_120000.csv .
head observables_20240115_120000.csv
```

## Querying the Data

### DynamoDB - Fast Lookups

**Single IP lookup:**
```bash
aws dynamodb get-item \
  --table-name observable_catalog \
  --key '{"indicator_key": {"S": "ip#1.2.3.4"}}'
```

**Query by type (last 7 days):**
```bash
aws dynamodb query \
  --table-name observable_catalog \
  --index-name indicator-type-index \
  --key-condition-expression "indicator_type = :type AND last_seen >= :date" \
  --expression-attribute-values '{
    ":type": {"S": "ip"},
    ":date": {"S": "2024-01-08T00:00:00Z"}
  }'
```

### S3 + Athena - Historical Analysis

**Create Athena table:**
```sql
CREATE EXTERNAL TABLE IF NOT EXISTS observables (
  indicator STRING,
  indicator_type STRING,
  first_seen STRING,
  last_seen STRING,
  total_hits BIGINT,
  days_seen DOUBLE,
  src_ips STRING,
  dest_ips STRING,
  users STRING,
  export_timestamp STRING
)
PARTITIONED BY (date STRING)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://your-org-splunk-observables/observables/'
TBLPROPERTIES ('skip.header.line.count'='1');
```

**Add partitions:**
```sql
MSCK REPAIR TABLE observables;
```

**Query historical data:**
```sql
SELECT indicator, first_seen, last_seen, total_hits
FROM observables
WHERE indicator_type = 'ip'
  AND indicator = '1.2.3.4'
  AND date >= '2024-01-01'
ORDER BY date;
```

**Find most active IPs in last month:**
```sql
SELECT indicator, SUM(total_hits) as total
FROM observables
WHERE indicator_type = 'ip'
  AND date >= DATE_FORMAT(DATE_ADD('day', -30, CURRENT_DATE), '%Y-%m-%d')
GROUP BY indicator
ORDER BY total DESC
LIMIT 100;
```

## Monitoring

### CloudWatch Dashboards

Create a dashboard to monitor:
- Lambda execution duration
- Lambda errors
- DynamoDB consumed capacity
- S3 bucket size
- Splunk search run time

### Alarms

Terraform creates an alarm for Lambda errors. Add more:

**DynamoDB throttling:**
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name dynamodb-throttling \
  --metric-name UserErrors \
  --namespace AWS/DynamoDB \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

**Lambda duration:**
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name lambda-duration \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Average \
  --period 300 \
  --threshold 300000 \
  --comparison-operator GreaterThanThreshold
```

## Maintenance

### Regular Tasks

1. **Monitor Splunk search performance** (weekly)
2. **Review CloudWatch logs** (daily initially, then weekly)
3. **Check S3 costs** (monthly)
4. **Validate data completeness** (weekly)

### Troubleshooting

**Lambda timing out:**
```bash
aws lambda update-function-configuration \
  --function-name splunk-observable-exporter \
  --timeout 900 \
  --memory-size 1024
```

**DynamoDB throttling:**
```bash
# Switch to on-demand (if using provisioned)
aws dynamodb update-table \
  --table-name observable_catalog \
  --billing-mode PAY_PER_REQUEST
```

**Splunk search too slow:**
- See `SPLUNK_PERFORMANCE.md`
- Reduce time window
- Add more specific filters
- Use `tstats` instead of `stats`

## Scaling

### Adjusting Schedule

**More frequent (every 15 minutes):**
```hcl
schedule_expression = "rate(15 minutes)"
```

**Less frequent (daily):**
```hcl
schedule_expression = "cron(0 2 * * ? *)"  # 2 AM daily
```

### High-Volume Environments

For >1TB/day in Splunk:

1. Reduce summary search window to 15 minutes
2. Increase Lambda memory to 1024MB
3. Enable DynamoDB auto-scaling
4. Consider multiple Lambda functions by indicator type
5. Use Kinesis Firehose for real-time streaming

## Cost Optimization

### DynamoDB TTL

Automatically expires items after 90 days (already configured in Terraform).

### S3 Lifecycle

Terraform configures:
- Day 0-90: S3 Standard
- Day 90-365: Glacier Instant Retrieval
- Day 365+: Glacier Deep Archive

### Lambda

- Right-size memory (test with 256MB, 512MB, 1024MB)
- Use reserved concurrency to prevent runaway costs
- Monitor invocation count

## Security Checklist

- [x] Credentials stored in Secrets Manager
- [x] IAM roles with least privilege
- [x] S3 bucket encryption enabled
- [x] DynamoDB encryption enabled
- [x] VPC endpoints for S3/DynamoDB (optional)
- [x] CloudWatch logs encrypted
- [x] S3 bucket versioning enabled
- [x] DynamoDB point-in-time recovery enabled

## Next Steps

1. Set up CloudWatch dashboard
2. Create runbook for common issues
3. Document incident response procedures
4. Schedule quarterly cost review
5. Plan for data retention compliance

