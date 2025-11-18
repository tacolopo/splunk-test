# AWS Setup From Scratch

## Step 0: Get Access to a Machine

**You need a machine to run commands on!** Choose one option:

### Option A: Use Your Local Machine (Easiest)

If you have a laptop/desktop with Python and Docker:
```bash
# Install requirements (if not already installed):
# - Python 3.7+ (python.org)
# - Docker Desktop (docker.com)
# - AWS CLI (aws.amazon.com/cli)
# - Git (git-scm.com)

# Verify installations
python --version
docker --version
aws --version
git --version
```

**Continue to Step 1 below.**

---

### Option B: Use AWS CloudShell (Quick, Browser-based)

CloudShell is a free browser-based shell in AWS Console.

1. Log into AWS Console: https://console.aws.amazon.com
2. Click the CloudShell icon (terminal icon) in the top-right toolbar
3. Wait for shell to initialize (~30 seconds)

**Pros:** 
- Free, no setup needed
- AWS CLI pre-configured
- Python pre-installed

**Cons:**
- Can't run Docker Splunk (but you can still test AWS resources)
- Limited storage

**If using CloudShell, skip Docker Splunk steps and use Option 2 testing (AWS only).**

---

### Option C: Launch EC2 Instance (Full AWS Experience)

Launch an Amazon Linux 2 EC2 instance:

**Via AWS Console:**
1. Go to EC2 Dashboard: https://console.aws.amazon.com/ec2
2. Click **Launch Instance**
3. Configure:
   - **Name**: splunk-test
   - **AMI**: Amazon Linux 2023
   - **Instance type**: t2.medium (for Splunk) or t2.micro (for testing only)
   - **Key pair**: Create new or select existing
   - **Security group**: Allow SSH (port 22) and HTTP (ports 8000, 8089)
4. Click **Launch Instance**
5. Wait 2 minutes for instance to start
6. Click **Connect** → **SSH client** for connection instructions

**Via AWS CLI:**
```bash
# Create security group
aws ec2 create-security-group \
  --group-name splunk-test-sg \
  --description "Security group for Splunk testing"

# Allow SSH, Splunk Web (8000), Splunk API (8089)
aws ec2 authorize-security-group-ingress \
  --group-name splunk-test-sg \
  --protocol tcp --port 22 --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-name splunk-test-sg \
  --protocol tcp --port 8000 --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-name splunk-test-sg \
  --protocol tcp --port 8089 --cidr 0.0.0.0/0

# Launch instance (replace YOUR-KEY-NAME with your key pair name)
aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --instance-type t2.medium \
  --key-name YOUR-KEY-NAME \
  --security-groups splunk-test-sg \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=splunk-test}]'

# Get instance public IP
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=splunk-test" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text
```

**Connect to instance:**
```bash
ssh -i your-key.pem ec2-user@YOUR-INSTANCE-IP
```

**Once connected, install Docker:**
```bash
# Install Docker on Amazon Linux
sudo yum update -y
sudo yum install -y docker git python3-pip
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ec2-user

# Log out and back in for group changes
exit
# ssh back in
ssh -i your-key.pem ec2-user@YOUR-INSTANCE-IP

# Verify Docker works
docker ps
```

**Now continue to Step 1 below.**

---

### Option D: Use AWS Cloud9 (IDE in Browser)

Cloud9 provides a full IDE in your browser with terminal access.

1. Go to Cloud9: https://console.aws.amazon.com/cloud9
2. Click **Create environment**
3. Configure:
   - **Name**: splunk-test
   - **Instance type**: t2.medium (recommended) or t2.micro
   - **Platform**: Amazon Linux 2
4. Click **Create**
5. Wait 2-3 minutes, then click **Open IDE**

Cloud9 includes Python, Git, and AWS CLI pre-installed.

**Install Docker:**
```bash
sudo yum install -y docker
sudo systemctl start docker
sudo usermod -a -G docker ec2-user
```

**Now continue to Step 1 below.**

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

