# Quick Permissions Fix - Step by Step

## The Problem
Your "test" user doesn't have IAM permissions to grant itself DynamoDB/S3 permissions.

## The Solution
Use your root account (the email you signed up with) to grant permissions.

---

## Step 1: Get Root Account Access Keys

1. Go to: https://console.aws.amazon.com
2. Click your username (top right corner)
3. Click **Security credentials**
4. Scroll down to **Access keys** section
5. Click **Create access key**
6. Select **Command Line Interface (CLI)**
7. Click **Next** → **Create access key**
8. **COPY BOTH VALUES:**
   - Access Key ID: `AKIA...` (starts with AKIA)
   - Secret Access Key: `wJalr...` (long string)

**⚠️ SAVE THESE - you won't see the secret again!**

---

## Step 2: Configure Root Profile in AWS CLI

Run this command:
```bash
aws configure --profile root
```

**When it asks for each value, paste from Step 1:**

```
AWS Access Key ID [None]: AKIA... (paste your Access Key ID)
AWS Secret Access Key [None]: wJalr... (paste your Secret Access Key)
Default region name [None]: us-east-1
Default output format [None]: json
```

Press Enter after each line.

**This creates a NEW profile called "root". Your "test" profile stays the same.**

---

## Step 3: Grant Permissions Using Root Profile

Now run these commands (they use `--profile root` to use the root credentials):

```bash
aws iam attach-user-policy --user-name test --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess --profile root

aws iam attach-user-policy --user-name test --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess --profile root

aws iam attach-user-policy --user-name test --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite --profile root
```

Each command should complete without errors.

---

## Step 4: Verify Permissions

```bash
aws iam list-attached-user-policies --user-name test
```

You should see all 3 policies listed.

---

## Step 5: Continue Testing

Now go back to `LOCAL_MACHINE_GUIDE.md` Step 2 and run:

```bash
python create_dynamodb_table.py --region us-east-1
```

It should work now!

---

## Summary

- **"test" profile** = your regular user (doesn't have IAM permissions)
- **"root" profile** = root account credentials (has all permissions)
- You configure root profile once, then use `--profile root` when you need admin powers
- Your test profile stays configured for normal use

