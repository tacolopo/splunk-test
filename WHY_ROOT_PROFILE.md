# Why You Need Root Profile - Simple Explanation

## The Problem

- **"test" user** = IAM user in your AWS account
- **"test" user's credentials** = Already configured in AWS CLI (default profile)
- **"test" user's permissions** = Does NOT have IAM permissions
- **Result** = "test" user CANNOT grant itself DynamoDB/S3 permissions

## The Solution

- **Root account** = The account owner (email you signed up with)
- **Root account permissions** = Has ALL permissions, including IAM
- **What we do** = Use root account to grant permissions TO the "test" user

## How It Works

1. **"test" profile** (already configured) = Uses "test" user credentials
   - Can do: DynamoDB operations (once permissions granted)
   - Cannot do: Grant IAM permissions

2. **"root" profile** (you're creating) = Uses root account credentials  
   - Can do: Grant IAM permissions to any user
   - Can do: Everything

3. **The flow:**
   ```
   Root account → Grants permissions → "test" user
   (using root profile)              (test user can now use DynamoDB)
   ```

## What You're Actually Doing

When you run:
```bash
aws iam attach-user-policy --user-name test --policy-arn ... --profile root
```

You're saying:
- **Use root account credentials** (`--profile root`)
- **Grant permissions** (`attach-user-policy`)
- **To the "test" user** (`--user-name test`)

After this, the "test" user has DynamoDB permissions, and you can use your normal "test" profile for everything else.

## Summary

- **"test" profile** = Your normal user (limited permissions)
- **"root" profile** = Account owner (all permissions, used only to grant permissions)
- **You configure root profile** = So you can use root credentials to grant permissions
- **After permissions granted** = Use "test" profile normally, root profile not needed

**The root profile is just a tool to grant permissions. After that, use your test profile.**

