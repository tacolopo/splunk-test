# Terraform + Lambda Deployment Guide

This guide walks you through deploying the fully automated Splunk observable export system using Terraform and AWS Lambda.

## Architecture Overview

```
Splunk (Hourly) → Lambda (Hourly) → DynamoDB (90-day TTL) + S3 (Lifetime Master)
```

**Components:**
- **DynamoDB**: Fast operational lookups, 90-day TTL for cost control
- **S3**: Lifetime master file with merged history
- **Lambda**: Runs hourly, exports from Splunk to DynamoDB + S3
- **EventBridge**: Triggers Lambda on schedule
- **Secrets Manager**: Stores Splunk credentials securely

## Prerequisites

1. **AWS CLI configured** with appropriate permissions
2. **Terraform installed** (>= 1.0)
3. **Python 3.11+** for building Lambda packages
4. **Splunk credentials** ready to store in Secrets Manager

## Step-by-Step Deployment

### Step 1: Configure Terraform Variables

Copy the example variables file:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region          = "us-east-1"
environment         = "production"
s3_bucket_name      = "your-org-splunk-observables-UNIQUE_ID"
dynamodb_table_name = "observable_catalog"
lookback_days       = 1
schedule_expression = "rate(1 hour)"  # Or "cron(0 * * * ? *)" for hourly at :00
```

**Important:** Make `s3_bucket_name` unique (add your org name or random ID).

### Step 2: Store Splunk Credentials in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name splunk/credentials \
  --description "Splunk API credentials for observable export" \
  --secret-string '{
    "host": "splunk.example.com",
    "port": "8089",
    "username": "api_user",
    "password": "your_secure_password",
    "scheme": "https"
  }' \
  --region us-east-1
```

**Or update existing secret:**

```bash
aws secretsmanager put-secret-value \
  --secret-id splunk/credentials \
  --secret-string '{
    "host": "splunk.example.com",
    "port": "8089",
    "username": "api_user",
    "password": "your_secure_password",
    "scheme": "https"
  }' \
  --region us-east-1
```

### Step 3: Build Lambda Deployment Packages

From the project root:

```bash
cd "/home/user/Documents/Splunk to AWS Project"
./deploy_lambda.sh
```

This creates:
- `lambda_layer.zip` - Python dependencies (pandas, pyarrow, boto3, splunk-sdk)
- `lambda_function.zip` - Application code (export_to_aws.py, lambda_function.py, splunk_queries/)

**Move packages to terraform directory:**

```bash
mv lambda_layer.zip terraform/
mv lambda_function.zip terraform/
```

### Step 4: Initialize Terraform

```bash
cd terraform
terraform init
```

### Step 5: Review Deployment Plan

```bash
terraform plan
```

Review the plan to see what will be created:
- S3 bucket
- DynamoDB table
- Lambda function + layer
- EventBridge rule (hourly schedule)
- IAM roles and policies
- CloudWatch log group
- Error alarm

### Step 6: Deploy Infrastructure

```bash
terraform apply
```

Type `yes` when prompted. This will:
1. Create all AWS resources
2. Upload Lambda function and layer
3. Configure EventBridge to trigger Lambda hourly
4. Set up CloudWatch monitoring

**Expected time:** 2-5 minutes

### Step 7: Verify Deployment

**Check Lambda function:**

```bash
aws lambda get-function \
  --function-name splunk-observable-exporter \
  --region us-east-1
```

**Check EventBridge rule:**

```bash
aws events describe-rule \
  --name splunk-observable-export-hourly \
  --region us-east-1
```

**Manually trigger Lambda (test):**

```bash
aws lambda invoke \
  --function-name splunk-observable-exporter \
  --region us-east-1 \
  response.json

cat response.json
```

**Check CloudWatch logs:**

```bash
aws logs tail /aws/lambda/splunk-observable-exporter --follow --region us-east-1
```

### Step 8: Verify Data Export

**Check DynamoDB:**

```bash
aws dynamodb scan \
  --table-name observable_catalog \
  --limit 5 \
  --region us-east-1
```

**Check S3 master file:**

```bash
aws s3 ls s3://your-bucket-name/observables/master.parquet --region us-east-1
```

## Schedule Options

Edit `schedule_expression` in `terraform.tfvars`:

**Hourly (default):**
```hcl
schedule_expression = "rate(1 hour)"
```

**Hourly at :00 (top of hour):**
```hcl
schedule_expression = "cron(0 * * * ? *)"
```

**Daily at 2 AM:**
```hcl
schedule_expression = "cron(0 2 * * ? *)"
```

**Every 6 hours:**
```hcl
schedule_expression = "rate(6 hours)"
```

After changing, run:
```bash
terraform apply
```

## Monitoring

### CloudWatch Metrics

**Lambda Metrics:**
- Invocations: Number of times Lambda runs
- Errors: Failed executions
- Duration: Execution time
- Throttles: Rate limiting issues

**DynamoDB Metrics:**
- ConsumedReadCapacityUnits
- ConsumedWriteCapacityUnits
- UserErrors

**S3 Metrics:**
- BucketSizeBytes
- NumberOfObjects

### CloudWatch Alarms

An alarm is automatically created for Lambda errors. Check it:

```bash
aws cloudwatch describe-alarms \
  --alarm-names splunk-observable-exporter-errors \
  --region us-east-1
```

### View Logs

```bash
# Real-time logs
aws logs tail /aws/lambda/splunk-observable-exporter --follow

# Last 100 lines
aws logs tail /aws/lambda/splunk-observable-exporter --since 1h
```

## Updating the Lambda Function

After making code changes:

1. **Rebuild packages:**
   ```bash
   ./deploy_lambda.sh
   mv lambda_layer.zip terraform/
   mv lambda_function.zip terraform/
   ```

2. **Update Lambda:**
   ```bash
   cd terraform
   terraform apply
   ```

Terraform will detect the new zip files and update the Lambda function.

## Troubleshooting

### Lambda Timeout

If Lambda times out, increase timeout in `terraform/main.tf`:

```hcl
timeout = 1800  # 30 minutes (max)
```

### Lambda Out of Memory

Increase memory in `terraform/main.tf`:

```hcl
memory_size = 1024  # or 2048, 3008
```

### DynamoDB Throttling

Switch to on-demand billing (already configured) or increase provisioned capacity.

### S3 Permission Errors

Verify IAM policy includes:
- `s3:GetObject` (to read master file)
- `s3:PutObject` (to write master file)
- `s3:ListBucket` (to check if file exists)

### Splunk Connection Errors

Check Secrets Manager secret:
```bash
aws secretsmanager get-secret-value \
  --secret-id splunk/credentials \
  --region us-east-1
```

Verify Splunk API is accessible from Lambda's VPC (if using VPC).

## Cost Optimization

**Current Setup:**
- DynamoDB: On-demand billing (pay per request)
- S3: Standard storage (cheap for lifetime data)
- Lambda: Pay per invocation (~$0.20 per 1M requests)

**Estimated Monthly Cost:**
- Small org (1K IPs/day): ~$10-20/month
- Medium org (10K IPs/day): ~$30-50/month
- Large org (100K IPs/day): ~$100-200/month

**Optimization Tips:**
1. Reduce schedule frequency (daily vs hourly)
2. Increase DynamoDB TTL (90 days → 180 days)
3. Use S3 lifecycle policies (move to Glacier after 90 days)

## Cleanup

To destroy all resources:

```bash
cd terraform
terraform destroy
```

**Warning:** This will delete:
- All DynamoDB data
- All S3 data
- Lambda function and logs
- EventBridge rules

Make sure you have backups if needed!

## Next Steps

1. **Set up Splunk scheduled search** (if not already done)
2. **Monitor first few Lambda executions**
3. **Verify data in DynamoDB and S3**
4. **Set up CloudWatch dashboards** for monitoring
5. **Configure SNS alerts** for Lambda errors (optional)

## Support

Check logs first:
```bash
aws logs tail /aws/lambda/splunk-observable-exporter --since 24h
```

Common issues:
- Splunk credentials incorrect → Check Secrets Manager
- Lambda timeout → Increase timeout or reduce lookback_days
- No data exported → Verify Splunk summary index has data

