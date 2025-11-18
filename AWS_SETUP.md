# AWS Setup From Scratch

## Prerequisites

- AWS account (sign up at https://aws.amazon.com if you don't have one)
- AWS CLI installed and configured

---

## Step 1: Configure AWS CLI

If you haven't configured AWS CLI yet:

```bash
aws configure
```

You'll be prompted for:
1. **AWS Access Key ID**: Get this from AWS Console → IAM → Users → Security credentials
2. **AWS Secret Access Key**: Get this with the Access Key
3. **Default region**: `us-east-1` (recommended)
4. **Default output format**: `json`

**Verify it works:**
```bash
aws sts get-caller-identity
```

You should see your account ID and user ARN.

---

## Step 2: Create Required AWS Resources

You need to create 3 resources:

### 1. DynamoDB Table (for fast IP lookups)

```bash
# Clone the repo first if you haven't
git clone https://github.com/tacolopo/splunk-test.git
cd splunk-test

# Install Python dependencies
pip install -r requirements.txt

# Create DynamoDB table
python create_dynamodb_table.py --region us-east-1
```

**What this creates:**
- Table name: `observable_catalog`
- Primary key: `indicator_key` (String)
- Global Secondary Index: `indicator-type-index`
- TTL enabled (90-day expiration)
- On-demand billing (auto-scales)

**Verify:**
```bash
aws dynamodb describe-table --table-name observable_catalog --region us-east-1
```

### 2. S3 Bucket (for historical data storage)

```bash
# Create bucket with unique name
BUCKET_NAME="splunk-observables-$(date +%s)"
aws s3 mb s3://${BUCKET_NAME} --region us-east-1

# Save the bucket name - you'll need it!
echo ${BUCKET_NAME}
echo "export S3_BUCKET=${BUCKET_NAME}" >> ~/.bashrc
```

**What this creates:**
- Bucket name: `splunk-observables-<timestamp>` (globally unique)
- Region: us-east-1
- Used for: CSV and JSON exports of observables

**Verify:**
```bash
aws s3 ls | grep splunk-observables
```

**IMPORTANT**: Write down your bucket name! You'll need it in the config file.

### 3. Secrets Manager Secret (for Splunk credentials)

```bash
# Store Splunk credentials securely
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

**What this creates:**
- Secret name: `splunk/credentials`
- Contains: Splunk connection details (host, port, username, password)
- Used by: Lambda function and export script

**Verify:**
```bash
aws secretsmanager describe-secret --secret-id splunk/credentials --region us-east-1
```

---

## Step 3: Create Configuration File

Now that you have the AWS resources, create your config file:

```bash
cd splunk-test

# Create config.json (replace YOUR_BUCKET_NAME with the value from Step 2)
cat > config.json << 'EOF'
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
    "s3_bucket": "YOUR_BUCKET_NAME_HERE",
    "s3_prefix": "observables",
    "dynamodb_table": "observable_catalog"
  }
}
EOF

# Edit the file to add your actual bucket name
nano config.json
# Change "YOUR_BUCKET_NAME_HERE" to your actual bucket name from Step 2
```

Or if you saved the bucket name to environment variable:
```bash
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
```

---

## Summary of AWS Resources Created

| Resource | Name/ID | Purpose | Cost |
|----------|---------|---------|------|
| **DynamoDB Table** | `observable_catalog` | Fast lookups for recent IPs (90 days) | Free tier: 25GB |
| **S3 Bucket** | `splunk-observables-<timestamp>` | Historical data archive | Free tier: 5GB |
| **Secrets Manager** | `splunk/credentials` | Secure Splunk credentials | $0.40/month after 30 days |

**Total Setup Cost**: $0 for first 30 days, then ~$0.40/month

---

## Verification Checklist

Run these commands to verify everything is set up:

```bash
# 1. Check DynamoDB table exists
aws dynamodb describe-table --table-name observable_catalog --region us-east-1 --query 'Table.TableStatus'
# Expected: "ACTIVE"

# 2. Check S3 bucket exists
aws s3 ls | grep splunk-observables
# Expected: Shows your bucket name

# 3. Check Secrets Manager secret exists
aws secretsmanager describe-secret --secret-id splunk/credentials --region us-east-1 --query 'Name'
# Expected: "splunk/credentials"

# 4. Check config file exists
cat config.json | grep s3_bucket
# Expected: Shows your actual bucket name
```

If all 4 commands work, you're ready to proceed! ✅

---

## IAM Permissions Required

Your AWS user needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DescribeTable",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:GetItem",
        "dynamodb:Scan",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/observable_catalog*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:ListBucket",
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::splunk-observables-*",
        "arn:aws:s3:::splunk-observables-*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:splunk/credentials-*"
    }
  ]
}
```

Most AWS accounts have `AdministratorAccess` or `PowerUserAccess` which includes these permissions.

---

## Quick Setup Script

Want to create everything in one go? Run this:

```bash
#!/bin/bash

# Clone repo
git clone https://github.com/tacolopo/splunk-test.git
cd splunk-test

# Install dependencies
pip install -r requirements.txt

# Create DynamoDB table
python create_dynamodb_table.py --region us-east-1

# Create S3 bucket
BUCKET_NAME="splunk-observables-$(date +%s)"
aws s3 mb s3://${BUCKET_NAME} --region us-east-1
echo "S3 Bucket created: ${BUCKET_NAME}"

# Create Secrets Manager secret
aws secretsmanager create-secret \
  --name splunk/credentials \
  --secret-string '{
    "host": "localhost",
    "port": "8089",
    "username": "admin",
    "password": "Changeme123!",
    "scheme": "https"
  }' \
  --region us-east-1

# Create config file
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
    "s3_bucket": "${BUCKET_NAME}",
    "s3_prefix": "observables",
    "dynamodb_table": "observable_catalog"
  }
}
EOF

echo ""
echo "✅ AWS resources created successfully!"
echo ""
echo "Resources:"
echo "  - DynamoDB Table: observable_catalog"
echo "  - S3 Bucket: ${BUCKET_NAME}"
echo "  - Secrets Manager: splunk/credentials"
echo "  - Config file: config.json"
echo ""
echo "Next: Follow QUICKSTART.md Step 3 (Set Up Docker Splunk)"
```

Save as `setup_aws.sh`, make executable (`chmod +x setup_aws.sh`), and run (`./setup_aws.sh`).

---

## What's Next?

After AWS resources are created, continue with:
1. **Docker Splunk Setup** - See `QUICKSTART.md` Step 3
2. **Test the Export** - See `QUICKSTART.md` Step 7
3. **Verify Data** - See `QUICKSTART.md` Step 8

---

## Cleanup (when done testing)

To delete all AWS resources:

```bash
# Delete DynamoDB table
aws dynamodb delete-table --table-name observable_catalog --region us-east-1

# Delete S3 bucket (and all contents)
aws s3 rb s3://${S3_BUCKET} --force --region us-east-1

# Delete Secrets Manager secret
aws secretsmanager delete-secret \
  --secret-id splunk/credentials \
  --force-delete-without-recovery \
  --region us-east-1

# Delete config file
rm config.json
```

---

## Troubleshooting

### "Access Denied" errors

Your AWS user needs appropriate IAM permissions. Check with:
```bash
aws iam get-user
aws iam list-attached-user-policies --user-name YOUR_USERNAME
```

### DynamoDB table already exists

```bash
# Delete and recreate
aws dynamodb delete-table --table-name observable_catalog --region us-east-1
# Wait 30 seconds, then:
python create_dynamodb_table.py --region us-east-1
```

### S3 bucket name taken

Bucket names must be globally unique. Try a different timestamp:
```bash
BUCKET_NAME="splunk-obs-myorg-$(date +%s)"
aws s3 mb s3://${BUCKET_NAME} --region us-east-1
```

### Secrets Manager secret already exists

```bash
# Delete and recreate
aws secretsmanager delete-secret --secret-id splunk/credentials --force-delete-without-recovery --region us-east-1
# Then re-run the create-secret command
```

