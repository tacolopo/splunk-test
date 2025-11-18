# Quick Reference Cheat Sheet

## One-Line Commands (Copy/Paste)

### Setup

```bash
# Clone repo
git clone https://github.com/tacolopo/splunk-test.git && cd splunk-test && pip install -r requirements.txt

# Start Splunk Docker
docker run -d -p 8000:8000 -p 8089:8089 \
  -e SPLUNK_GENERAL_TERMS='--accept-sgt-current-at-splunk-com' \
  -e SPLUNK_START_ARGS='--accept-license' \
  -e SPLUNK_PASSWORD='Changeme123!' \
  --name splunk splunk/splunk:latest

# Create AWS resources
python create_dynamodb_table.py --region us-east-1 && aws s3 mb s3://splunk-obs-$(date +%s) --region us-east-1
```

### Generate Sample Data

```bash
cat > sample_logs.json << 'EOF'
{"_time": "2024-01-15T10:00:00", "src_ip": "1.2.3.4", "dest_ip": "10.0.0.1", "action": "blocked"}
{"_time": "2024-01-15T10:05:00", "src_ip": "8.8.8.8", "dest_ip": "10.0.0.2", "action": "allowed"}
{"_time": "2024-01-15T10:10:00", "email": "user@example.com", "action": "login"}
{"_time": "2024-01-15T10:15:00", "hash": "5d41402abc4b2a76b9719d911017c592", "action": "detected"}
EOF

docker cp sample_logs.json splunk:/opt/splunk/sample_logs.json && \
docker exec splunk /opt/splunk/bin/splunk add oneshot /opt/splunk/sample_logs.json -sourcetype _json -index main -auth admin:Changeme123!
```

### Test

```bash
# Quick test with sample data (no Splunk needed)
python test_with_sample_data.py

# Full pipeline test
./test_full_pipeline.sh
```

### Query

```bash
# Query DynamoDB for specific IP
aws dynamodb get-item --table-name observable_catalog --key '{"indicator_key": {"S": "ip#1.2.3.4"}}'

# List all observables
aws dynamodb scan --table-name observable_catalog --max-items 10
```

### Cleanup

```bash
docker stop splunk && docker rm splunk && \
aws dynamodb delete-table --table-name observable_catalog --region us-east-1 && \
aws s3 rb s3://$(aws s3 ls | grep splunk-obs | awk '{print $3}') --force
```

---

## Essential URLs

- **Splunk Web UI**: http://localhost:8000 (admin/Changeme123!)
- **GitHub Repo**: https://github.com/tacolopo/splunk-test
- **Splunk API**: https://localhost:8089

---

## Key Files

| File | Purpose |
|------|---------|
| `QUICKSTART.md` | **Full step-by-step guide** |
| `export_to_aws.py` | Main export script |
| `config.json.example` | Configuration template |
| `test_with_sample_data.py` | Populate DynamoDB with test data |
| `test_full_pipeline.sh` | End-to-end integration test |
| `TESTING.md` | All testing scenarios |

---

## Splunk Searches

**View raw data:**
```spl
index=main earliest=-24h | head 10
```

**View summary index:**
```spl
index=observable_catalog | head 10
```

**Query specific IP:**
```spl
index=observable_catalog indicator="1.2.3.4"
| stats sum(hit_count) as total_hits
```

---

## AWS Resource Names

- **DynamoDB Table**: `observable_catalog`
- **S3 Bucket**: `splunk-observables-<timestamp>` (you create this)
- **Secrets Manager**: `splunk/credentials`
- **Lambda Function**: `splunk-observable-exporter` (if deployed)

---

## Environment Variables

```bash
export SPLUNK_HOST="localhost"
export SPLUNK_USERNAME="admin"
export SPLUNK_PASSWORD="Changeme123!"
export S3_BUCKET="your-bucket-name"
export AWS_REGION="us-east-1"
```

---

## Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Splunk not starting | `docker logs splunk` (wait 2-3 min) |
| Can't connect to Splunk | `curl -k https://localhost:8089` |
| DynamoDB access denied | `aws sts get-caller-identity` |
| No data in export | Check `index=observable_catalog` has data |
| S3 upload fails | Verify bucket name is correct |

---

## Testing Checklist

```
□ Splunk running (docker ps | grep splunk)
□ Sample data indexed (index=main | stats count)
□ Summary index created (Settings → Indexes)
□ AWS CLI configured (aws sts get-caller-identity)
□ DynamoDB table exists (aws dynamodb list-tables)
□ S3 bucket exists (aws s3 ls)
□ Export runs successfully (python export_to_aws.py)
□ Data in DynamoDB (python test_ip_address.py)
□ Data in S3 (aws s3 ls s3://your-bucket/observables/)
```

