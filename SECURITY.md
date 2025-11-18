# Security Best Practices

## Credential Management

**Never commit plain text credentials to version control.** This solution supports multiple secure methods for credential management:

### Option 1: Environment Variables (Recommended for Local Development)

Set these environment variables before running the script:

```bash
export SPLUNK_HOST="splunk.example.com"
export SPLUNK_PORT="8089"
export SPLUNK_USERNAME="your_username"
export SPLUNK_PASSWORD="your_password"
export SPLUNK_SCHEME="https"

export RDS_HOST="your-rds-endpoint.region.rds.amazonaws.com"
export RDS_PORT="5432"
export RDS_DATABASE="observables_db"
export RDS_USER="db_user"
export RDS_PASSWORD="db_password"
```

Then use a minimal `config.json` without credentials:

```json
{
  "splunk": {
    "host": "splunk.example.com",
    "port": 8089,
    "scheme": "https"
  },
  "aws": {
    "region": "us-east-1"
  }
}
```

### Option 2: AWS Secrets Manager (Recommended for Production)

1. **Store Splunk credentials in AWS Secrets Manager:**

```bash
aws secretsmanager create-secret \
  --name splunk/credentials \
  --secret-string '{"host":"splunk.example.com","port":"8089","username":"user","password":"pass","scheme":"https"}'
```

2. **Update config.json:**

```json
{
  "splunk": {
    "use_secrets_manager": true,
    "secrets_manager_secret_name": "splunk/credentials",
    "host": "splunk.example.com",
    "port": 8089
  }
}
```

3. **Ensure IAM permissions:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:region:account:secret:splunk/credentials-*"
    }
  ]
}
```

### Option 3: AWS IAM Roles (Recommended for Lambda/EC2)

When running on AWS infrastructure (Lambda, EC2, ECS), use IAM roles instead of access keys:

1. **Attach IAM role** with necessary permissions
2. **Remove AWS credentials** from config.json
3. **Use environment variables** or Secrets Manager for Splunk credentials

## File Permissions

Protect your `config.json` file:

```bash
chmod 600 config.json
```

## Network Security

- Use HTTPS for Splunk connections (`scheme: "https"`)
- Use SSL/TLS for RDS connections (enabled by default with psycopg2)
- Consider VPC endpoints for S3/DynamoDB if running in AWS VPC
- Use security groups to restrict access to RDS

## Encryption

- **S3**: Enable bucket encryption (SSE-S3 or SSE-KMS)
- **DynamoDB**: Enable encryption at rest
- **RDS**: Enable encryption at rest and in transit
- **Secrets Manager**: Encrypted by default

## Audit Logging

The script logs all operations. For production:

- Send logs to CloudWatch Logs (if running on AWS)
- Enable S3 access logging
- Enable DynamoDB CloudTrail logging
- Monitor for failed authentication attempts

## Least Privilege

Grant only necessary permissions:

- **Splunk**: Read-only access to `observable_catalog` index
- **S3**: `PutObject` permission only on the observables bucket
- **DynamoDB**: `UpdateItem` permission only on the catalog table
- **RDS**: INSERT/UPDATE permissions only on the catalog table

## Example Secure Config (No Credentials)

```json
{
  "splunk": {
    "use_secrets_manager": true,
    "secrets_manager_secret_name": "splunk/credentials"
  },
  "aws": {
    "region": "us-east-1",
    "s3_bucket": "your-observables-bucket",
    "dynamodb_table": "observable_catalog",
    "rds": {
      "use_secrets_manager": true,
      "secrets_manager_secret_name": "rds/observables-db"
    }
  }
}
```

All credentials retrieved from AWS Secrets Manager at runtime.

