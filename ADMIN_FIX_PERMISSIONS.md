# Admin: Grant Permissions to User

## Quick Fix - Run These Commands

```bash
# Grant DynamoDB permissions
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess

# Grant S3 permissions
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

# Grant Secrets Manager permissions
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite

# Grant Athena permissions (for querying S3 data)
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonAthenaFullAccess

# Grant Glue permissions (Athena uses Glue Data Catalog)
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AWSGlueServiceRole

# Verify policies are attached
aws iam list-attached-user-policies --user-name test
```

## If You Get "AccessDenied" Error

Your current AWS credentials don't have IAM permissions. Use one of these:

### Option 1: Use Root Account Credentials

**Step 1: Get Root Account Access Keys**

1. Log into AWS Console: https://console.aws.amazon.com
2. Click your username (top right) → **Security credentials**
3. Scroll to **Access keys** section
4. Click **Create access key**
5. Select **Command Line Interface (CLI)**
6. Click **Next** → **Create access key**
7. **SAVE THE ACCESS KEY ID AND SECRET ACCESS KEY** (you won't see the secret again!)

**Step 2: Configure AWS CLI with Root Credentials**

Run this command:
```bash
aws configure --profile root
```

**When prompted, enter:**
- **AWS Access Key ID:** [paste the Access Key ID you got from Step 1]
- **AWS Secret Access Key:** [paste the Secret Access Key you got from Step 1]
- **Default region name:** `us-east-1`
- **Default output format:** `json`

**Important:** This creates a NEW profile called "root". Your existing "test" profile stays configured. You're just adding another profile.

**Step 3: Attach Policies Using Root Profile**

```bash
# Attach policies using root profile
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess \
  --profile root

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess \
  --profile root

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite \
  --profile root

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonAthenaFullAccess \
  --profile root

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AWSGlueServiceRole \
  --profile root
```

**Note:** Root account = the email/password you used to sign up for AWS. You don't create it in IAM - it's the account owner.

### Option 2: Use AWS Console (Browser)

1. Go to: https://console.aws.amazon.com/iam/home#/users/test
2. Click **Add permissions** → **Attach policies directly**
3. Search and select:
   - `AmazonDynamoDBFullAccess`
   - `AmazonS3FullAccess`
   - `SecretsManagerReadWrite`
   - `AmazonAthenaFullAccess`
   - `AWSGlueServiceRole`
4. Click **Next** → **Add permissions**

### Option 3: Create Admin User with IAM Permissions

```bash
# Create admin user
aws iam create-user --user-name admin-iam

# Attach IAM full access to admin user
aws iam attach-user-policy \
  --user-name admin-iam \
  --policy-arn arn:aws:iam::aws:policy/IAMFullAccess

# Create access key for admin user
aws iam create-access-key --user-name admin-iam

# Use those credentials to configure AWS CLI
aws configure --profile admin-iam
# Enter the access key ID and secret from above

# Now attach policies to 'test' user using admin-iam profile
aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess \
  --profile admin-iam

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess \
  --profile admin-iam

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite \
  --profile admin-iam

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AmazonAthenaFullAccess \
  --profile admin-iam

aws iam attach-user-policy \
  --user-name test \
  --policy-arn arn:aws:iam::aws:policy/AWSGlueServiceRole \
  --profile admin-iam
```

## Verify It Worked

```bash
# Check attached policies
aws iam list-attached-user-policies --user-name test

# Should show:
# - AmazonDynamoDBFullAccess
# - AmazonS3FullAccess
# - SecretsManagerReadWrite
# - AmazonAthenaFullAccess
# - AWSGlueServiceRole
```

## Then Continue Testing

After permissions are granted, go back to `LOCAL_MACHINE_GUIDE.md` and continue from Step 2:

```bash
python create_dynamodb_table.py --region us-east-1
```

