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

# Verify policies are attached
aws iam list-attached-user-policies --user-name test
```

## If You Get "AccessDenied" Error

Your current AWS credentials don't have IAM permissions. Use one of these:

### Option 1: Use Root Account Credentials

```bash
# Configure root account
aws configure --profile root
# Enter root account access key and secret

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
```

### Option 2: Use AWS Console (Browser)

1. Go to: https://console.aws.amazon.com/iam/home#/users/test
2. Click **Add permissions** → **Attach policies directly**
3. Search and select:
   - `AmazonDynamoDBFullAccess`
   - `AmazonS3FullAccess`
   - `SecretsManagerReadWrite`
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
```

## Verify It Worked

```bash
# Check attached policies
aws iam list-attached-user-policies --user-name test

# Should show:
# - AmazonDynamoDBFullAccess
# - AmazonS3FullAccess
# - SecretsManagerReadWrite
```

## Then Continue Testing

After permissions are granted, go back to `LOCAL_MACHINE_GUIDE.md` and continue from Step 2:

```bash
python create_dynamodb_table.py --region us-east-1
```

