# Testing Guide

This guide provides multiple strategies for testing the Splunk observable catalog solution, from local unit tests to full end-to-end testing.

## Testing Options Overview

| Method | Cost | Complexity | Realism | Time |
|--------|------|------------|---------|------|
| Mock Data (Local) | Free | Low | Medium | 10 min |
| Splunk Free License | Free | Medium | High | 30 min |
| AWS Free Tier | Free* | Medium | High | 20 min |
| Full Integration | Free* | High | Very High | 1 hour |

*Within free tier limits

## Option 1: Local Testing with Mock Data (Recommended First)

Test the export logic without AWS or Splunk.

### Setup

```bash
cd "/home/user/Documents/Splunk to AWS Project"
pip install -r requirements.txt
pip install pytest pytest-mock moto
```

### Create Mock Test File

Save as `test_mock_export.py`:

```python
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sys

sys.path.insert(0, '.')
from export_to_aws import SplunkObservableExporter

def test_splunk_connection():
    """Test Splunk connection with mocked credentials"""
    
    config = {
        'splunk': {
            'host': 'mock-splunk.example.com',
            'port': 8089,
            'username': 'testuser',
            'password': 'testpass'
        },
        'aws': {
            'region': 'us-east-1'
        }
    }
    
    with patch('export_to_aws.client.connect') as mock_connect:
        mock_connect.return_value = Mock()
        
        exporter = SplunkObservableExporter(config)
        exporter.connect_splunk()
        
        mock_connect.assert_called_once()
        assert exporter.splunk_client is not None

def test_dynamodb_export_with_mock_data():
    """Test DynamoDB export with mock data"""
    
    config = {
        'splunk': {'host': 'test', 'port': 8089},
        'aws': {
            'region': 'us-east-1',
            'dynamodb_table': 'test_table'
        }
    }
    
    mock_data = [
        {
            'indicator': '1.2.3.4',
            'indicator_type': 'ip',
            'first_seen': '2024-01-15T10:00:00Z',
            'last_seen': '2024-01-20T15:30:00Z',
            'total_hits': 42,
            'src_ips': ['10.0.0.1', '10.0.0.2'],
            'dest_ips': ['192.168.1.1']
        }
    ]
    
    exporter = SplunkObservableExporter(config)
    
    with patch.object(exporter, 'dynamodb_client') as mock_dynamodb:
        mock_dynamodb.update_item = Mock()
        exporter.dynamodb_client = mock_dynamodb
        
        exporter.export_to_dynamodb(mock_data)
        
        assert mock_dynamodb.update_item.called
        call_args = mock_dynamodb.update_item.call_args[1]
        assert call_args['TableName'] == 'test_table'
        assert 'ip#1.2.3.4' in str(call_args['Key'])

def test_s3_export_with_mock_data():
    """Test S3 export with mock CSV generation"""
    
    config = {
        'splunk': {'host': 'test', 'port': 8089},
        'aws': {
            'region': 'us-east-1',
            's3_bucket': 'test-bucket',
            's3_prefix': 'observables'
        }
    }
    
    mock_data = [
        {
            'indicator': '1.2.3.4',
            'indicator_type': 'ip',
            'first_seen': '2024-01-15T10:00:00Z',
            'last_seen': '2024-01-20T15:30:00Z',
            'total_hits': 42
        }
    ]
    
    exporter = SplunkObservableExporter(config)
    
    with patch.object(exporter, 's3_client') as mock_s3:
        mock_s3.upload_file = Mock()
        exporter.s3_client = mock_s3
        
        exporter.export_to_s3(mock_data, '2024-01-20')
        
        assert mock_s3.upload_file.called

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

### Run Tests

```bash
python test_mock_export.py
```

## Option 2: AWS Free Tier Testing

Test with real AWS services (free within limits).

### AWS Free Tier Includes:
- **DynamoDB**: 25GB storage, 25 WCU/RCU (more than enough)
- **S3**: 5GB storage, 20,000 GET requests, 2,000 PUT requests
- **Lambda**: 1M requests/month, 400,000 GB-seconds compute
- **Secrets Manager**: First 30 days free, then $0.40/month

### Setup AWS Test Environment

```bash
# 1. Create test DynamoDB table
python create_dynamodb_table.py --region us-east-1

# 2. Create test S3 bucket
aws s3 mb s3://your-test-observables-bucket --region us-east-1

# 3. Store test Splunk credentials (we'll mock Splunk later)
aws secretsmanager create-secret \
  --name splunk/test-credentials \
  --secret-string '{
    "host": "localhost",
    "port": "8089",
    "username": "admin",
    "password": "changeme",
    "scheme": "https"
  }' \
  --region us-east-1
```

### Test with Sample Data

Create `test_with_sample_data.py`:

```python
#!/usr/bin/env python3

import boto3
import json
from datetime import datetime

def populate_test_data():
    """Populate DynamoDB with test IP addresses"""
    
    dynamodb = boto3.client('dynamodb', region_name='us-east-1')
    table_name = 'observable_catalog'
    
    test_ips = [
        {'ip': '1.2.3.4', 'hits': 100, 'type': 'external'},
        {'ip': '8.8.8.8', 'hits': 50, 'type': 'dns'},
        {'ip': '10.0.0.1', 'hits': 200, 'type': 'internal'},
        {'ip': '192.168.1.1', 'hits': 150, 'type': 'gateway'},
        {'ip': '203.0.113.5', 'hits': 75, 'type': 'test'}
    ]
    
    print("Populating test data...")
    
    for ip_data in test_ips:
        composite_key = f"ip#{ip_data['ip']}"
        
        item = {
            'indicator_key': {'S': composite_key},
            'indicator': {'S': ip_data['ip']},
            'indicator_type': {'S': 'ip'},
            'first_seen': {'S': '2024-01-01T00:00:00Z'},
            'last_seen': {'S': datetime.now().isoformat() + 'Z'},
            'total_hits': {'N': str(ip_data['hits'])},
            'export_timestamp': {'S': datetime.now().isoformat() + 'Z'}
        }
        
        try:
            dynamodb.put_item(TableName=table_name, Item=item)
            print(f"✓ Added {ip_data['ip']} ({ip_data['hits']} hits)")
        except Exception as e:
            print(f"✗ Failed to add {ip_data['ip']}: {e}")
    
    print("\nQuerying test data...")
    
    response = dynamodb.get_item(
        TableName=table_name,
        Key={'indicator_key': {'S': 'ip#1.2.3.4'}}
    )
    
    if 'Item' in response:
        print(f"✓ Successfully retrieved: {response['Item']['indicator']['S']}")
    else:
        print("✗ Failed to retrieve test data")

if __name__ == '__main__':
    populate_test_data()
```

Run it:
```bash
python test_with_sample_data.py
```

## Option 3: Splunk Free License (500MB/day)

Get a real Splunk instance for testing.

### Method A: Splunk Cloud Trial (Easiest)

1. Go to https://www.splunk.com/en_us/download/splunk-cloud.html
2. Sign up for 15-day free trial
3. Get instant Splunk Cloud instance
4. Use provided credentials for testing

### Method B: Splunk Enterprise Free (Local Install)

```bash
# Download Splunk Enterprise (Free, 500MB/day limit)
# Linux:
wget -O splunk.tgz 'https://download.splunk.com/products/splunk/releases/9.1.2/linux/splunk-9.1.2-b6b9c8185839-Linux-x86_64.tgz'
tar xvzf splunk.tgz
cd splunk/bin
./splunk start --accept-license

# Access: http://localhost:8000
# Default: admin/changeme (you'll set on first login)
```

### Method C: Docker (Fastest)

```bash
# Run Splunk in Docker
docker run -d \
  -p 8000:8000 \
  -p 8089:8089 \
  -e SPLUNK_GENERAL_TERMS='--accept-sgt-current-at-splunk-com' \
  -e SPLUNK_START_ARGS='--accept-license' \
  -e SPLUNK_PASSWORD='Changeme123!' \
  --name splunk \
  splunk/splunk:latest

# Wait 2-3 minutes for startup
docker logs -f splunk

# Access: http://localhost:8000
# Login: admin/Changeme123!
```

### Generate Test Data in Splunk

Once Splunk is running, generate sample observable data:

```bash
# Create sample log file
cat > sample_logs.json << 'EOF'
{"timestamp": "2024-01-15T10:00:00Z", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.1", "action": "blocked"}
{"timestamp": "2024-01-15T10:05:00Z", "src_ip": "8.8.8.8", "dest_ip": "10.0.0.2", "action": "allowed"}
{"timestamp": "2024-01-15T10:10:00Z", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.3", "action": "blocked"}
{"timestamp": "2024-01-15T10:15:00Z", "email": "user@example.com", "action": "login"}
{"timestamp": "2024-01-15T10:20:00Z", "hash": "5d41402abc4b2a76b9719d911017c592", "action": "detected"}
EOF

# Index the data using Splunk CLI
docker exec splunk /opt/splunk/bin/splunk add oneshot sample_logs.json \
  -sourcetype _json \
  -index main \
  -auth admin:Changeme123!
```

Or via Splunk Web UI:
1. Settings → Add Data → Upload
2. Upload `sample_logs.json`
3. Set sourcetype to `_json`
4. Index to `main`

### Create Summary Index in Splunk

```spl
# In Splunk Web, create new index:
Settings → Indexes → New Index
- Index Name: observable_catalog
- Max Size: 500MB
```

### Run Test Search

```spl
index=main earliest=-24h
| eval indicator_type=case(
    isnotnull(src_ip), "ip",
    isnotnull(email), "email",
    isnotnull(hash), "md5",
    1=1, "other"
  )
| eval indicator=case(
    indicator_type="ip", src_ip,
    indicator_type="email", email,
    indicator_type="md5", hash,
    true(), null()
  )
| where isnotnull(indicator)
| stats earliest(_time) as first_seen
        latest(_time) as last_seen
        count as hit_count
  by indicator indicator_type
| eval first_seen=strftime(first_seen,"%Y-%m-%dT%H:%M:%SZ"),
      last_seen=strftime(last_seen,"%Y-%m-%dT%H:%M:%SZ")
```

## Option 4: Full Integration Test

Test the complete pipeline end-to-end.

### Setup Script

Create `test_full_pipeline.sh`:

```bash
#!/bin/bash

set -e

echo "=== Splunk Observable Catalog - Full Integration Test ==="
echo ""

# Configuration
SPLUNK_HOST="${SPLUNK_HOST:-localhost}"
SPLUNK_PORT="${SPLUNK_PORT:-8089}"
SPLUNK_USERNAME="${SPLUNK_USERNAME:-admin}"
SPLUNK_PASSWORD="${SPLUNK_PASSWORD:-Changeme123!}"
AWS_REGION="${AWS_REGION:-us-east-1}"
DYNAMODB_TABLE="${DYNAMODB_TABLE:-observable_catalog}"
S3_BUCKET="${S3_BUCKET:-test-observables-$(date +%s)}"

echo "1. Creating AWS resources..."

# Create S3 bucket
aws s3 mb s3://${S3_BUCKET} --region ${AWS_REGION} || true

# Create DynamoDB table
python create_dynamodb_table.py --region ${AWS_REGION} || echo "Table may already exist"

echo "✓ AWS resources ready"
echo ""

echo "2. Testing Splunk connection..."
curl -k -u ${SPLUNK_USERNAME}:${SPLUNK_PASSWORD} \
  https://${SPLUNK_HOST}:${SPLUNK_PORT}/services/auth/login \
  -d username=${SPLUNK_USERNAME} \
  -d password=${SPLUNK_PASSWORD} > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✓ Splunk connection successful"
else
    echo "✗ Splunk connection failed"
    exit 1
fi
echo ""

echo "3. Creating test config..."
cat > test_config.json << EOF
{
  "splunk": {
    "host": "${SPLUNK_HOST}",
    "port": ${SPLUNK_PORT},
    "username": "${SPLUNK_USERNAME}",
    "password": "${SPLUNK_PASSWORD}",
    "scheme": "https"
  },
  "aws": {
    "region": "${AWS_REGION}",
    "s3_bucket": "${S3_BUCKET}",
    "s3_prefix": "test-observables",
    "dynamodb_table": "${DYNAMODB_TABLE}"
  }
}
EOF
echo "✓ Config created"
echo ""

echo "4. Running export..."
python export_to_aws.py \
  --config test_config.json \
  --format all \
  --lookback 7

if [ $? -eq 0 ]; then
    echo "✓ Export completed successfully"
else
    echo "✗ Export failed"
    exit 1
fi
echo ""

echo "5. Verifying DynamoDB..."
ITEM_COUNT=$(aws dynamodb scan \
  --table-name ${DYNAMODB_TABLE} \
  --select COUNT \
  --region ${AWS_REGION} \
  --output json | jq '.Count')

echo "   Found ${ITEM_COUNT} items in DynamoDB"

if [ ${ITEM_COUNT} -gt 0 ]; then
    echo "✓ DynamoDB populated"
else
    echo "⚠ DynamoDB empty (may be expected if no Splunk data)"
fi
echo ""

echo "6. Verifying S3..."
OBJECT_COUNT=$(aws s3 ls s3://${S3_BUCKET}/test-observables/ --recursive | wc -l)

echo "   Found ${OBJECT_COUNT} objects in S3"

if [ ${OBJECT_COUNT} -gt 0 ]; then
    echo "✓ S3 populated"
    aws s3 ls s3://${S3_BUCKET}/test-observables/ --recursive --human-readable
else
    echo "⚠ S3 empty (may be expected if no Splunk data)"
fi
echo ""

echo "=== Integration Test Complete ==="
echo ""
echo "Cleanup commands:"
echo "  aws dynamodb delete-table --table-name ${DYNAMODB_TABLE} --region ${AWS_REGION}"
echo "  aws s3 rb s3://${S3_BUCKET} --force --region ${AWS_REGION}"
echo "  rm test_config.json"
```

Make executable and run:
```bash
chmod +x test_full_pipeline.sh
./test_full_pipeline.sh
```

## Testing Checklist

### Pre-Deployment Testing

- [ ] Unit tests pass (`python test_mock_export.py`)
- [ ] AWS credentials configured
- [ ] DynamoDB table created successfully
- [ ] S3 bucket created successfully
- [ ] Sample data populates correctly
- [ ] Queries return expected results

### Splunk Testing

- [ ] Splunk instance accessible
- [ ] Summary index created
- [ ] Test data indexed
- [ ] Summary search runs successfully
- [ ] API credentials work

### Lambda Testing (Local)

```bash
# Test Lambda handler locally
python -c "
import lambda_function
import os
os.environ['SPLUNK_SECRET_NAME'] = 'splunk/test-credentials'
os.environ['S3_BUCKET'] = 'test-bucket'
os.environ['DYNAMODB_TABLE'] = 'observable_catalog'
result = lambda_function.lambda_handler({}, None)
print(result)
"
```

### Lambda Testing (AWS)

```bash
# Deploy and test
cd terraform
terraform apply

# Invoke manually
aws lambda invoke \
  --function-name splunk-observable-exporter \
  --payload '{}' \
  --region us-east-1 \
  response.json

cat response.json

# Check logs
aws logs tail /aws/lambda/splunk-observable-exporter --follow
```

## Troubleshooting Tests

### Splunk Connection Fails

```bash
# Test Splunk API directly
curl -k -u admin:password \
  https://localhost:8089/services/auth/login \
  -d username=admin \
  -d password=password
```

### DynamoDB Access Denied

```bash
# Check AWS credentials
aws sts get-caller-identity

# Test DynamoDB access
aws dynamodb list-tables --region us-east-1
```

### S3 Upload Fails

```bash
# Test S3 write access
echo "test" > test.txt
aws s3 cp test.txt s3://your-bucket/test.txt
aws s3 rm s3://your-bucket/test.txt
rm test.txt
```

### No Data in Results

Check Splunk has data:
```spl
index=* earliest=-24h | stats count
```

Check summary index:
```spl
index=observable_catalog | head 10
```

## Cleanup After Testing

```bash
# Delete DynamoDB table
aws dynamodb delete-table --table-name observable_catalog --region us-east-1

# Delete S3 bucket
aws s3 rb s3://test-observables-bucket --force --region us-east-1

# Delete Secrets Manager secret
aws secretsmanager delete-secret \
  --secret-id splunk/test-credentials \
  --force-delete-without-recovery \
  --region us-east-1

# Stop Splunk Docker container
docker stop splunk
docker rm splunk

# Delete Terraform resources
cd terraform
terraform destroy
```

## Recommended Testing Sequence

1. **Day 1**: Mock data testing (Option 1)
2. **Day 2**: AWS Free Tier setup (Option 2)
3. **Day 3**: Splunk Docker setup (Option 3)
4. **Day 4**: Full integration test (Option 4)
5. **Day 5**: Lambda deployment and testing

## Cost Estimate for Testing

- **AWS Free Tier**: $0 (within limits)
- **Splunk Free**: $0 (500MB/day)
- **Total**: $0 for testing phase

After free tier:
- Minimal testing: ~$1-5/month
- Active testing: ~$10-20/month

