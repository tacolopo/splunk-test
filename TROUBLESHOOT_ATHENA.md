# Troubleshooting Athena Access Issues

## Problem: AccessDeniedException when running Athena queries

### Step 1: Verify Policies Are Attached

**If you have root/admin access:**
```bash
aws iam list-attached-user-policies --user-name test --profile root
```

**Should show:**
- AmazonAthenaFullAccess
- AWSGlueServiceRole
- AmazonS3FullAccess (also required)

**If policies are missing, attach them:**
```bash
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonAthenaFullAccess \
  --profile root

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AWSGlueServiceRole \
  --profile root
```

### Step 2: Wait for IAM Propagation

IAM changes can take 5-10 seconds to propagate. Wait a moment and try again.

### Step 3: Verify S3 Bucket Permissions

Athena needs to:
1. **Read** from your data bucket (`s3://your-bucket/observables/`)
2. **Write** to results location (`s3://your-bucket/athena-results/`)

**Create the results folder:**
```bash
export S3_BUCKET="your-bucket-name"
aws s3api put-object --bucket ${S3_BUCKET} --key athena-results/
```

**Verify S3 access:**
```bash
# Test read access
aws s3 ls s3://${S3_BUCKET}/observables/

# Test write access (create test file)
echo "test" | aws s3 cp - s3://${S3_BUCKET}/athena-results/test.txt
aws s3 rm s3://${S3_BUCKET}/athena-results/test.txt
```

### Step 4: Check Bucket Policy

If your bucket has a restrictive policy, Athena might be blocked. Check:
```bash
aws s3api get-bucket-policy --bucket ${S3_BUCKET} 2>/dev/null || echo "No bucket policy"
```

**If bucket policy exists**, ensure it allows:
- `s3:GetObject` on `observables/*`
- `s3:PutObject` on `athena-results/*`
- `s3:ListBucket` on the bucket root

### Step 5: Try Using AWS Console Instead

Sometimes the console works when CLI doesn't:

1. Go to: https://console.aws.amazon.com/athena/
2. Click **Query Editor**
3. Run: `CREATE DATABASE IF NOT EXISTS splunk_observables`
4. Set **Query result location** to: `s3://your-bucket/athena-results/`

### Step 6: Check Service Control Policies (SCPs)

If you're in an AWS Organization, SCPs might block Athena. Contact your AWS admin.

### Step 7: Minimal Permissions (If Full Access Doesn't Work)

If `AmazonAthenaFullAccess` still doesn't work, try creating a custom policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "athena:*",
        "glue:CreateDatabase",
        "glue:DeleteDatabase",
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:UpdateDatabase",
        "glue:CreateTable",
        "glue:DeleteTable",
        "glue:BatchDeleteTable",
        "glue:UpdateTable",
        "glue:GetTable",
        "glue:GetTables",
        "glue:BatchCreatePartition",
        "glue:CreatePartition",
        "glue:DeletePartition",
        "glue:BatchDeletePartition",
        "glue:UpdatePartition",
        "glue:GetPartition",
        "glue:GetPartitions",
        "glue:BatchGetPartition",
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:ListBucketMultipartUploads",
        "s3:ListMultipartUploadParts",
        "s3:AbortMultipartUpload",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "*"
    }
  ]
}
```

Save as `athena-policy.json`, then:
```bash
aws iam create-policy \
  --policy-name AthenaCustomAccess \
  --policy-document file://athena-policy.json \
  --profile root

# Get the policy ARN from output, then:
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/AthenaCustomAccess \
  --profile root
```

## Alternative: Use DynamoDB Instead

If Athena continues to have permission issues, **DynamoDB is faster and simpler** for operational lookups:

```bash
# Fast IP lookup (< 1 second)
aws dynamodb get-item \
  --table-name observable_catalog \
  --key '{"indicator_key": {"S": "ip#10.0.0.1"}}' \
  --region us-east-1 | python3 -m json.tool
```

Athena is only needed for **historical analysis across many months/years**. For recent data (last 90 days), DynamoDB is better.

