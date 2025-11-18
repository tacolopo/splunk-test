# Splunk Observable Catalog to AWS

A production-ready solution for cataloging security observables (IP addresses, email addresses, hashes, user agent strings, etc.) from Splunk and exporting them to AWS S3, DynamoDB, or RDS PostgreSQL.

## Overview

This solution provides:

- **Splunk Summary Indexing**: Scheduled searches that aggregate observables with first_seen, last_seen, and hit counts
- **Automated Export**: AWS Lambda automatically exports data hourly
- **Dual Storage**: DynamoDB for fast operational lookups (90-day TTL), S3 for long-term historical analysis
- **Comprehensive Cataloging**: Tracks IPs, emails, hashes (MD5, SHA1, SHA256), user agents, domains, and more
- **Production Ready**: Error handling, logging, monitoring, and cost optimization
- **Infrastructure as Code**: Terraform templates for complete deployment

## Architecture

```
Splunk Raw Logs → Summary Index → Lambda (Hourly) → DynamoDB + S3
                                                    ↓         ↓
                                            Fast Lookups  Analytics
```

1. **Splunk Side**: Scheduled searches aggregate observables into a summary index (hourly)
2. **Lambda Export**: Automated function queries Splunk and exports to AWS (hourly, 10-min delay)
3. **DynamoDB**: Fast operational lookups for recent IPs (90-day TTL, automatic expiration)
4. **S3**: Long-term historical storage with lifecycle policies (Glacier after 90 days)

**See `ARCHITECTURE.md` for detailed diagrams and `SPLUNK_PERFORMANCE.md` for performance considerations.**

## Prerequisites

- Splunk Enterprise with API access
- Python 3.7+
- AWS account with appropriate permissions
- Splunk indexes: `proxy`, `email`, `edr`, `web`, `firewall` (or modify queries to match your indexes)

## Quick Start (Automated with Lambda)

**Note**: This solution works for all indicator types (IPs, emails, hashes, user agents, domains), but IP addresses are the primary use case.

### Option 1: Fully Automated (Recommended)

1. **Store Splunk credentials in AWS Secrets Manager**:
```bash
aws secretsmanager create-secret \
  --name splunk/credentials \
  --secret-string '{"host":"splunk.example.com","port":"8089","username":"user","password":"pass","scheme":"https"}'
```

2. **Build and deploy Lambda**:
```bash
./deploy_lambda.sh

cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your S3 bucket name
terraform init
terraform apply
```

3. **Configure Splunk** (create summary index and scheduled search - see Installation section)

4. **Done!** Lambda runs hourly, automatically exporting to DynamoDB + S3.

**See `DEPLOYMENT.md` for complete automated deployment guide.**

### Option 2: Manual Testing

For testing before full automation:

1. **Install dependencies**: 
```bash
pip install -r requirements.txt
```

2. **Set environment variables**:
```bash
export SPLUNK_HOST="your-splunk-host"
export SPLUNK_USERNAME="your-username"  
export SPLUNK_PASSWORD="your-password"
```

3. **Create DynamoDB table**:
```bash
python create_dynamodb_table.py --region us-east-1
```

4. **Test export**:
```bash
python export_to_aws.py --config config.json --format all --lookback 1
```

## Installation

1. **Clone or download this repository**

2. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure Splunk**:
   - Create a summary index named `observable_catalog`:
     - Settings → Indexes → New Index
     - Index name: `observable_catalog`
   
   - Create a scheduled search using `splunk_queries/observable_catalog.spl`:
     - Settings → Searches, reports, and alerts → New Report
     - Set schedule to run hourly (or as needed)
     - Paste the query from `observable_catalog.spl`
     - Enable "Summary indexing" and select `observable_catalog` index

4. **Configure AWS**:
   - Create an S3 bucket (if using S3 export)
   - Create a DynamoDB table (if using DynamoDB export):
     ```bash
     python create_dynamodb_table.py --region us-east-1
     ```
   - Set up RDS PostgreSQL database (if using RDS export)

5. **Create configuration file**:
```bash
cp config.json.example config.json
```

Edit `config.json` with your credentials:
- Splunk host, port, username, password
- AWS region, profile, S3 bucket name
- DynamoDB table name (if using)
- RDS connection details (if using)

## Usage

### Basic Export (all formats)

```bash
python export_to_aws.py --config config.json --lookback 1
```

### Export to S3 only

```bash
python export_to_aws.py --config config.json --format s3 --lookback 7
```

### Export to DynamoDB only

```bash
python export_to_aws.py --config config.json --format dynamodb --lookback 1
```

### Export to RDS only

```bash
python export_to_aws.py --config config.json --format rds --lookback 1
```

### Command-line Options

- `--config, -c`: Path to configuration file (default: `config.json`)
- `--lookback, -l`: Number of days to look back (default: 1)
- `--format, -f`: Export format: `all`, `s3`, `dynamodb`, or `rds` (default: `all`)

## Splunk Queries

### observable_catalog.spl
Main query for scheduled search. Aggregates observables from raw logs and writes to summary index.

**Schedule**: Run hourly (or adjust time window in query)

### query_catalog.spl
Query template for looking up a specific observable in the catalog.

**Usage**: Replace `$indicator$` with the value you're searching for.

### export_all_observables.spl
Query used by the export script to retrieve all observables for export.

## Data Schema

### Observable Fields

- `indicator`: The observable value (IP, email, hash, etc.)
- `indicator_type`: Type of observable (`ip`, `email`, `ua`, `md5`, `sha1`, `sha256`, `domain`)
- `first_seen`: ISO timestamp of first occurrence
- `last_seen`: ISO timestamp of most recent occurrence
- `total_hits`: Total count of occurrences
- `days_seen`: Number of days between first and last seen
- `src_ips`: Source IPs (multivalue)
- `dest_ips`: Destination IPs (multivalue)
- `users`: Associated users (multivalue)
- `sourcetypes`: Splunk sourcetypes (multivalue)
- `actions`: Actions taken (multivalue)
- `unique_src_ips`: Count of unique source IPs
- `unique_dest_ips`: Count of unique destination IPs

## Storage Formats

### S3 Export

Files are stored in partitioned format:
```
s3://bucket/observables/date=YYYY-MM-DD/observables_TIMESTAMP.csv
s3://bucket/observables/date=YYYY-MM-DD/observables_TIMESTAMP.json
```

### DynamoDB Export

- **Table**: `observable_catalog`
- **Primary Key**: `indicator_key` (format: `{indicator_type}#{indicator}`)
  - Example for IP: `ip#1.2.3.4`
  - Example for email: `email#user@example.com`
  - Example for hash: `md5#abc123...`
- **GSI**: `indicator-type-index` for querying by type and last_seen
- **Supports all indicator types**: IPs, emails, hashes, user agents, domains, etc.

### RDS PostgreSQL Export

Table: `observable_catalog`
- Uses upsert logic (INSERT ... ON CONFLICT UPDATE)
- Aggregates counts and merges multivalue fields
- Preserves earliest `first_seen` and latest `last_seen`

## Automation

### Cron Job (Linux/Mac)

Add to crontab for daily export:
```bash
0 2 * * * /usr/bin/python3 /path/to/export_to_aws.py --config /path/to/config.json --lookback 1
```

### AWS Lambda

1. Package the script and dependencies:
```bash
pip install -r requirements.txt -t lambda_package/
cp export_to_aws.py lambda_package/
cp -r splunk_queries lambda_package/
```

2. Create a Lambda function with:
   - Runtime: Python 3.9+
   - Handler: `export_to_aws.main`
   - Environment variables: Store config as JSON or use Secrets Manager
   - Timeout: 5-15 minutes (depending on data volume)
   - Schedule: EventBridge rule for daily/hourly execution

### Docker

Create a Dockerfile:
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "export_to_aws.py"]
```

## Querying Exported Data

### S3 (using AWS Athena)

```sql
CREATE EXTERNAL TABLE observables (
  indicator string,
  indicator_type string,
  first_seen string,
  last_seen string,
  total_hits bigint,
  ...
)
PARTITIONED BY (date string)
STORED AS PARQUET
LOCATION 's3://your-bucket/observables/';

SELECT * FROM observables 
WHERE indicator = '1.2.3.4' 
AND date >= '2024-01-01';
```

### DynamoDB

```python
import boto3

dynamodb = boto3.client('dynamodb')
response = dynamodb.get_item(
    TableName='observable_catalog',
    Key={'indicator_key': {'S': 'ip#1.2.3.4'}}
)
```

### PostgreSQL

```sql
SELECT * FROM observable_catalog 
WHERE indicator = '1.2.3.4' 
AND indicator_type = 'ip';
```

## Customization

### Adding New Observable Types

1. Edit `splunk_queries/observable_catalog.spl`:
   - Add new `indicator_type` case in the `eval` statement
   - Add corresponding `indicator` extraction logic

2. The export script will automatically handle new types

### Modifying Export Fields

Edit the `stats` command in `export_all_observables.spl` to include/exclude fields.

### Changing Time Windows

Modify `earliest` and `latest` in `observable_catalog.spl`:
- Hourly: `earliest=-1h@h latest=@h`
- Daily: `earliest=-1d@d latest=@d`

## Troubleshooting

### Splunk Connection Issues

- Verify host, port, and credentials in `config.json`
- Check Splunk firewall rules
- Ensure API access is enabled

### AWS Permission Issues

Required permissions:
- **S3**: `s3:PutObject`, `s3:PutObjectAcl`
- **DynamoDB**: `dynamodb:UpdateItem`, `dynamodb:PutItem`
- **RDS**: Database connection permissions

### No Data Exported

- Verify summary index has data: `index=observable_catalog | head 10`
- Check scheduled search is running successfully
- Verify lookback period matches your data availability

## Security Considerations

**⚠️ IMPORTANT: Never commit plain text credentials to version control!**

This solution supports multiple secure credential management methods:

1. **Environment Variables** (Recommended for local development):
   ```bash
   export SPLUNK_HOST="splunk.example.com"
   export SPLUNK_USERNAME="user"
   export SPLUNK_PASSWORD="pass"
   ```

2. **AWS Secrets Manager** (Recommended for production):
   - Store credentials in AWS Secrets Manager
   - Set `use_secrets_manager: true` in config.json
   - Provide `secrets_manager_secret_name`

3. **IAM Roles**: Use IAM roles instead of access keys when running on AWS infrastructure

4. **File Permissions**: Protect config.json: `chmod 600 config.json`

5. **Encryption**: Enable encryption at rest for S3, DynamoDB, and RDS

See `SECURITY.md` for detailed security best practices.

## Testing

See `TESTING.md` for comprehensive testing strategies including:
- Local testing with mock data (no AWS/Splunk needed)
- AWS Free Tier testing
- Splunk Docker/Cloud trial setup
- Full integration testing

**Quick test:**
```bash
# Test with sample data (no Splunk needed)
python test_with_sample_data.py

# Run mock unit tests
python test_mock_export.py
```

## License

This solution is provided as-is for organizational use.

