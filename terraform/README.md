# Terraform Deployment

This directory contains Terraform configuration for deploying the complete Splunk observable catalog infrastructure.

**📖 For complete production deployment instructions, see [PRODUCTION_DEPLOYMENT.md](../PRODUCTION_DEPLOYMENT.md)**

## What Gets Deployed

### Storage
- **S3 Bucket**: For historical observable storage
  - Versioning enabled
  - Encryption at rest (AES-256)
  - Lifecycle policies (90 days → Glacier IR, 365 days → Glacier)
  
- **DynamoDB Table**: For fast IP lookups
  - On-demand billing (auto-scaling)
  - Global secondary index on `indicator_type` + `last_seen`
  - TTL enabled (90-day automatic expiration)
  - Point-in-time recovery
  - Encryption at rest

### Compute
- **Lambda Function**: Splunk observable exporter
  - Runtime: Python 3.11
  - Timeout: 15 minutes
  - Memory: 512MB
  - Includes Lambda layer for dependencies
  
- **EventBridge Rule**: Scheduled trigger
  - Default: Hourly (`rate(1 hour)`)
  - Configurable via `schedule_expression`

### Security
- **Secrets Manager Secret**: For Splunk credentials
  - Placeholder created, you add the actual credentials
  
- **IAM Role**: Lambda execution role with least privilege
  - Secrets Manager read access
  - DynamoDB write access
  - S3 write access
  - CloudWatch Logs write access

### Monitoring
- **CloudWatch Log Group**: Lambda logs (30-day retention)
- **CloudWatch Alarm**: Alerts on Lambda errors

## Prerequisites

1. **AWS CLI** configured with credentials
2. **Terraform** installed (version 1.0+)
3. **Lambda packages** built (run `../deploy_lambda.sh` first)

## Deployment Steps

### 1. Build Lambda Packages

```bash
cd ..
./deploy_lambda.sh
cd terraform
```

This creates:
- `lambda_layer.zip` - Dependencies
- `lambda_function.zip` - Application code

### 2. Configure Variables

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
```hcl
aws_region          = "us-east-1"
environment         = "production"
s3_bucket_name      = "your-unique-bucket-name"  # Must be globally unique
dynamodb_table_name = "observable_catalog"
lookback_days       = 1
schedule_expression = "rate(1 hour)"
```

### 3. Initialize Terraform

```bash
terraform init
```

### 4. Review Plan

```bash
terraform plan
```

Review the resources that will be created.

### 5. Deploy

```bash
terraform apply
```

Type `yes` when prompted.

### 6. Store Splunk Credentials

After deployment, add your Splunk credentials to Secrets Manager:

```bash
aws secretsmanager put-secret-value \
  --secret-id splunk/credentials \
  --secret-string '{
    "host": "splunk.example.com",
    "port": "8089",
    "username": "api_user",
    "password": "your_secure_password",
    "scheme": "https"
  }'
```

## Configuration Options

### Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `aws_region` | AWS region | `us-east-1` |
| `environment` | Environment name | `production` |
| `s3_bucket_name` | S3 bucket name (must be unique) | Required |
| `dynamodb_table_name` | DynamoDB table name | `observable_catalog` |
| `lookback_days` | Days to look back in Splunk | `1` |
| `schedule_expression` | EventBridge schedule | `rate(1 hour)` |

### Schedule Expressions

**Hourly:**
```hcl
schedule_expression = "rate(1 hour)"
```

**Every 15 minutes:**
```hcl
schedule_expression = "rate(15 minutes)"
```

**Daily at 2 AM:**
```hcl
schedule_expression = "cron(0 2 * * ? *)"
```

**Every 2 hours:**
```hcl
schedule_expression = "rate(2 hours)"
```

## Outputs

After deployment, Terraform provides these outputs:

```bash
terraform output
```

- `s3_bucket_name` - Name of the S3 bucket
- `dynamodb_table_name` - Name of the DynamoDB table
- `lambda_function_name` - Name of the Lambda function
- `lambda_function_arn` - ARN of the Lambda function
- `secrets_manager_secret_arn` - ARN of the Secrets Manager secret
- `cloudwatch_log_group` - CloudWatch log group name

## Testing

### Test Lambda Function

```bash
FUNCTION_NAME=$(terraform output -raw lambda_function_name)

aws lambda invoke \
  --function-name $FUNCTION_NAME \
  --payload '{}' \
  response.json

cat response.json
```

### Check CloudWatch Logs

```bash
LOG_GROUP=$(terraform output -raw cloudwatch_log_group)

aws logs tail $LOG_GROUP --follow
```

### Verify DynamoDB

```bash
TABLE_NAME=$(terraform output -raw dynamodb_table_name)

aws dynamodb scan \
  --table-name $TABLE_NAME \
  --limit 5
```

### Check S3 Contents

```bash
BUCKET_NAME=$(terraform output -raw s3_bucket_name)

aws s3 ls s3://$BUCKET_NAME/observables/ --recursive
```

## Updating

### Change Lambda Code

1. Make changes to `export_to_aws.py` or `lambda_function.py`
2. Rebuild: `../deploy_lambda.sh`
3. Apply: `terraform apply`

### Change Schedule

1. Edit `terraform.tfvars`:
   ```hcl
   schedule_expression = "rate(30 minutes)"
   ```
2. Apply: `terraform apply`

### Increase Lambda Resources

1. Edit `main.tf`:
   ```hcl
   memory_size = 1024  # Was 512
   timeout     = 1800  # Was 900
   ```
2. Apply: `terraform apply`

## Cost Estimate

Based on `terraform plan`, you can estimate costs:

```bash
terraform plan -out=plan.out
terraform show -json plan.out | jq '.configuration.root_module.resources'
```

**Typical monthly costs:**
- DynamoDB (on-demand, 10K IPs): ~$15
- S3 (100GB stored): ~$3
- Lambda (720 invocations/month): ~$5
- Secrets Manager: ~$0.40
- **Total: ~$23-25/month**

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Warning**: This will delete:
- All data in S3 bucket
- All data in DynamoDB table
- Lambda function
- CloudWatch logs

Make sure you have backups before destroying!

## Troubleshooting

### Deployment Fails

**Error: S3 bucket name already exists**
- Bucket names must be globally unique
- Change `s3_bucket_name` in `terraform.tfvars`

**Error: lambda_function.zip not found**
- Run `../deploy_lambda.sh` first

**Error: Secrets Manager secret already exists**
- Delete existing secret: `aws secretsmanager delete-secret --secret-id splunk/credentials --force-delete-without-recovery`
- Or remove from Terraform and manage manually

### Lambda Not Running

**Check EventBridge rule:**
```bash
aws events describe-rule --name splunk-observable-export-hourly
```

**Check Lambda permissions:**
```bash
aws lambda get-policy --function-name splunk-observable-exporter
```

**Manually invoke:**
```bash
aws lambda invoke --function-name splunk-observable-exporter response.json
```

## State Management

### Remote State (Recommended for Teams)

Create `backend.tf`:
```hcl
terraform {
  backend "s3" {
    bucket = "your-terraform-state-bucket"
    key    = "splunk-observable-catalog/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
  }
}
```

### State Commands

**List resources:**
```bash
terraform state list
```

**Show resource:**
```bash
terraform state show aws_lambda_function.observable_exporter
```

**Import existing resource:**
```bash
terraform import aws_dynamodb_table.observable_catalog observable_catalog
```

## Best Practices

1. **Always run `terraform plan` before `apply`**
2. **Use remote state for team environments**
3. **Tag resources appropriately** (already configured)
4. **Enable MFA delete on S3 bucket** (for production)
5. **Review IAM permissions regularly**
6. **Monitor CloudWatch alarms**
7. **Back up Terraform state file**

## Additional Resources

- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)

