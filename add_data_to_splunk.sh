#!/bin/bash

# Script to add sample data to Splunk via REST API

SPLUNK_HOST="localhost"
SPLUNK_PORT="8089"
SPLUNK_USER="admin"
SPLUNK_PASS="Changeme123!"
FILE="sample_logs.json"

echo "Adding data to Splunk..."

# Copy file to container
docker cp ${FILE} splunk:/tmp/${FILE}

# Method 1: Try oneshot endpoint
echo "Attempting oneshot method..."
RESPONSE=$(curl -k -s -u ${SPLUNK_USER}:${SPLUNK_PASS} \
  https://${SPLUNK_HOST}:${SPLUNK_PORT}/services/data/inputs/oneshot \
  -d name=/tmp/${FILE} \
  -d sourcetype=_json \
  -d index=main)

# Check if bytes indexed > 0
BYTES_INDEXED=$(echo "$RESPONSE" | grep -oP '(?<=<s:key name="Bytes Indexed">)[0-9]+' || echo "0")

if [ "$BYTES_INDEXED" != "0" ] && [ "$BYTES_INDEXED" != "" ]; then
    echo "✓ Successfully indexed $BYTES_INDEXED bytes via oneshot"
    exit 0
fi

echo "Oneshot method didn't index data. Trying alternative method..."

# Method 2: Send each line as an event via simple receiver
echo "Sending events line by line..."
COUNT=0
while IFS= read -r line; do
    if [ -n "$line" ]; then
        curl -k -s -u ${SPLUNK_USER}:${SPLUNK_PASS} \
          https://${SPLUNK_HOST}:${SPLUNK_PORT}/services/receivers/simple \
          -d "sourcetype=_json" \
          -d "index=main" \
          --data-urlencode "event=$line" > /dev/null
        COUNT=$((COUNT + 1))
    fi
done < ${FILE}

echo "✓ Sent $COUNT events to Splunk"
echo ""
echo "Verify data with: index=main | head 10"

