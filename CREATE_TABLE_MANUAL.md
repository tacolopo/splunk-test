# Create DynamoDB Table Manually (If You Don't Have IAM Permissions)

If you can't run `python create_dynamodb_table.py` due to permissions, create the table manually in AWS Console.

## Step-by-Step Instructions

### 1. Open DynamoDB Console

Go to: https://console.aws.amazon.com/dynamodbv2/home?region=us-east-1#tables

### 2. Create Table

1. Click **Create table** (orange button, top right)

2. **Table details:**
   - **Table name:** `observable_catalog`
   - **Partition key:** `indicator_key`
   - **Partition key type:** String
   - Leave sort key empty

3. **Table settings:**
   - **Capacity mode:** On-demand (recommended for free tier)
   - Leave other settings as default

4. Click **Create table**

5. Wait ~30 seconds for table to be created

### 3. Add Global Secondary Index (GSI)

1. Click on the `observable_catalog` table name

2. Click the **Indexes** tab

3. Click **Create index**

4. **Index details:**
   - **Partition key:** `indicator_type` (String)
   - **Sort key:** `last_seen` (String)
   - **Index name:** `indicator-type-index`

5. **Projected attributes:** Select **All**

6. Click **Create index**

7. Wait ~30 seconds for index to be created

### 4. Enable TTL (Optional but Recommended)

1. Still in the table, click **Additional info** tab

2. Scroll to **Time to live (TTL)**

3. Click **Enable TTL**

4. **TTL attribute name:** `ttl`

5. Click **Enable TTL**

This will automatically delete items after 90 days (based on the ttl field value).

### 5. Verify Table is Ready

You should see:
- **Table status:** Active
- **Indexes:** 1 (indicator-type-index)
- **Item count:** 0 (will populate when you run the export)

## What You Created

✅ Table: `observable_catalog`
- Primary key: `indicator_key` (String)
- Billing: On-demand (auto-scales)
- GSI: `indicator-type-index` for querying by type and date

## Next Steps

Continue with **LOCAL_MACHINE_GUIDE.md** Step 3 (Create S3 Bucket).

The table is ready to use!

