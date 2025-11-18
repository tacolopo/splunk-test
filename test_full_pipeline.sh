#!/bin/bash

set -e

echo "=== Splunk Observable Catalog - Full Integration Test ==="
echo ""

SPLUNK_HOST="${SPLUNK_HOST:-localhost}"
SPLUNK_PORT="${SPLUNK_PORT:-8089}"
SPLUNK_USERNAME="${SPLUNK_USERNAME:-admin}"
SPLUNK_PASSWORD="${SPLUNK_PASSWORD:-Changeme123!}"
AWS_REGION="${AWS_REGION:-us-east-1}"
DYNAMODB_TABLE="${DYNAMODB_TABLE:-observable_catalog}"
S3_BUCKET="${S3_BUCKET:-test-observables-$(date +%s)}"

echo "Configuration:"
echo "  Splunk: ${SPLUNK_HOST}:${SPLUNK_PORT}"
echo "  AWS Region: ${AWS_REGION}"
echo "  DynamoDB Table: ${DYNAMODB_TABLE}"
echo "  S3 Bucket: ${S3_BUCKET}"
echo ""

echo "1. Creating AWS resources..."

aws s3 mb s3://${S3_BUCKET} --region ${AWS_REGION} 2>&1 | grep -v "BucketAlreadyOwnedByYou" || true

python create_dynamodb_table.py --region ${AWS_REGION} 2>&1 | grep -v "already exists" || true

echo "✓ AWS resources ready"
echo ""

echo "2. Testing Splunk connection..."
SPLUNK_TEST=$(curl -k -s -o /dev/null -w "%{http_code}" \
  -u ${SPLUNK_USERNAME}:${SPLUNK_PASSWORD} \
  https://${SPLUNK_HOST}:${SPLUNK_PORT}/services/auth/login \
  -d username=${SPLUNK_USERNAME} \
  -d password=${SPLUNK_PASSWORD})

if [ "$SPLUNK_TEST" = "200" ]; then
    echo "✓ Splunk connection successful"
else
    echo "✗ Splunk connection failed (HTTP ${SPLUNK_TEST})"
    echo "  Make sure Splunk is running:"
    echo "  docker run -d -p 8000:8000 -p 8089:8089 -e SPLUNK_GENERAL_TERMS='--accept-sgt-current-at-splunk-com' -e SPLUNK_START_ARGS='--accept-license' -e SPLUNK_PASSWORD='Changeme123!' splunk/splunk:latest"
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
echo "✓ Config created: test_config.json"
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
  --output json 2>/dev/null | jq '.Count' 2>/dev/null || echo "0")

echo "   Found ${ITEM_COUNT} items in DynamoDB"

if [ ${ITEM_COUNT} -gt 0 ]; then
    echo "✓ DynamoDB populated"
    
    echo ""
    echo "   Sample items:"
    aws dynamodb scan \
      --table-name ${DYNAMODB_TABLE} \
      --limit 3 \
      --region ${AWS_REGION} \
      --output json 2>/dev/null | \
      jq -r '.Items[] | "   - \(.indicator.S) (\(.indicator_type.S)): \(.total_hits.N) hits"' 2>/dev/null || echo "   (unable to display sample)"
else
    echo "⚠ DynamoDB empty"
    echo "   This is expected if Splunk has no data yet"
    echo "   Run: python test_with_sample_data.py"
fi
echo ""

echo "6. Verifying S3..."
OBJECT_COUNT=$(aws s3 ls s3://${S3_BUCKET}/test-observables/ --recursive 2>/dev/null | wc -l)

echo "   Found ${OBJECT_COUNT} objects in S3"

if [ ${OBJECT_COUNT} -gt 0 ]; then
    echo "✓ S3 populated"
    echo ""
    echo "   Files:"
    aws s3 ls s3://${S3_BUCKET}/test-observables/ --recursive --human-readable | \
      awk '{print "   - " $NF " (" $3 ")"}'
else
    echo "⚠ S3 empty"
    echo "   This is expected if no data was exported"
fi
echo ""

echo "=== Integration Test Complete ==="
echo ""
echo "Next steps:"
echo "  1. Populate test data: python test_with_sample_data.py"
echo "  2. Query DynamoDB: python test_ip_address.py"
echo "  3. View CloudWatch logs if using Lambda"
echo ""
echo "Cleanup commands:"
echo "  python test_with_sample_data.py --cleanup"
echo "  aws dynamodb delete-table --table-name ${DYNAMODB_TABLE} --region ${AWS_REGION}"
echo "  aws s3 rb s3://${S3_BUCKET} --force --region ${AWS_REGION}"
echo "  rm test_config.json"
echo ""

