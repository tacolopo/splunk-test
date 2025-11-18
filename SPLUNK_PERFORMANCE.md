# Splunk Performance Considerations

This document outlines best practices for running the observable catalog solution without impacting Splunk performance.

## Summary Indexing Performance

### 1. Schedule During Off-Peak Hours

Schedule searches when Splunk usage is lowest:

```
0 2-6 * * *  # Run between 2 AM and 6 AM
```

Or stagger searches throughout the day:

```
0 */2 * * *  # Run every 2 hours at minute 0
```

### 2. Use Appropriate Time Windows

**Recommended:** Hourly searches with 1-hour windows
```spl
earliest=-1h@h latest=@h
```

**Benefits:**
- Smaller data volumes per search
- Faster completion times
- Less memory usage
- Better for real-time alerting

**For High-Volume Environments:** Use shorter windows
```spl
earliest=-15m@m latest=@m  # Every 15 minutes
```

**For Low-Volume Environments:** Consolidate to daily
```spl
earliest=-1d@d latest=@d  # Daily at midnight
```

### 3. Set Search Priority

For scheduled searches, set priority to avoid impacting interactive searches:

- Settings → Searches, reports, and alerts → Edit → Priority
- Set to "Low" or "Default" (avoid "High")

### 4. Enable Search Acceleration

Accelerate the summary index for faster queries:

```
Settings → Indexes → observable_catalog → Edit → Enable acceleration
```

### 5. Limit Data Sources

Only search indexes that contain observables:

```spl
index=proxy OR index=email OR index=edr
```

**Don't use:**
```spl
index=*  # Searches ALL indexes - very expensive
```

### 6. Use Index-Time Extractions

If possible, extract key fields at index time:
- `src_ip`, `dest_ip` for network data
- `email` for email data
- `hash` for malware/file data

This reduces search-time field extraction overhead.

## Search Optimization Techniques

### 1. Filter Early in the Pipeline

Put the most selective filters first:

```spl
index=proxy earliest=-1h@h latest=@h
| where isnotnull(dest_ip)
| eval indicator_type="ip"
...
```

### 2. Use tstats for Better Performance

If your data is in data models, use `tstats` instead of `stats`:

```spl
| tstats count earliest(_time) as first_seen latest(_time) as last_seen
  WHERE index=proxy by dest_ip
```

**Performance:** `tstats` is 50-100x faster than regular searches.

### 3. Limit Field Extractions

Only extract fields you need:

```spl
| fields src_ip, dest_ip, user_agent, hash
```

### 4. Use Summary Ranges

For initial backfill, break it into chunks:

```
Day 1: earliest=-7d@d latest=-6d@d
Day 2: earliest=-6d@d latest=-5d@d
...
```

## Resource Management

### 1. Configure Search Limits

In `limits.conf`, set appropriate limits:

```ini
[search]
max_mem_usage_mb = 2000
max_bucket_bytes = 104857600
max_rawsize_perchunk = 104857600
```

### 2. Monitor Search Performance

Create alerts for long-running searches:

```spl
index=_audit action=search
| where search_type="scheduled"
| where total_run_time > 300
| stats count by user savedsearch_name total_run_time
```

### 3. Use Search Concurrency Limits

Limit concurrent scheduled searches in `limits.conf`:

```ini
[scheduler]
max_searches_per_cpu = 1
auto_summary_perc = 50
```

## DynamoDB/S3 Export Impact

### Lambda Execution Timing

**Best Practice:** Run Lambda export 5-10 minutes after Splunk scheduled search completes.

Example schedule:
- Splunk summary search: `0 * * * *` (top of hour)
- Lambda export: `10 * * * *` (10 minutes past hour)

This ensures:
- Summary data is fully indexed
- No overlap between searches
- Complete data export

### Lookback Period

**Recommendation:** Use 1-day lookback for Lambda
```python
LOOKBACK_DAYS = 1
```

**Why:**
- Ensures no missed data if Lambda fails
- Handles Splunk indexing delays
- DynamoDB/S3 handle duplicates via upsert

### Rate Limiting

For large datasets, implement batching:

```python
BATCH_SIZE = 1000
MAX_ITEMS_PER_RUN = 10000
```

This prevents:
- Lambda timeout
- DynamoDB throttling
- Splunk API overload

## Monitoring and Alerting

### 1. Splunk Search Monitoring

Monitor summary search health:

```spl
index=_audit action=search savedsearch_name="Observable Catalog*"
| stats avg(total_run_time) as avg_time max(total_run_time) as max_time
        count(eval(result_count=0)) as empty_results
  by savedsearch_name
| where avg_time > 300 OR empty_results > 5
```

### 2. Lambda Execution Monitoring

CloudWatch metrics to monitor:
- **Duration:** Should be < 5 minutes
- **Errors:** Should be 0
- **Throttles:** Should be 0
- **Concurrent Executions:** Should be 1

### 3. DynamoDB Monitoring

Monitor for throttling:
```
ConsumedReadCapacityUnits
ConsumedWriteCapacityUnits
UserErrors (for throttling)
```

## Scaling Recommendations

### Small Environment (<100GB/day)

- **Splunk:** Hourly summaries, 1-hour window
- **Lambda:** Hourly execution, 1-day lookback
- **DynamoDB:** On-demand pricing
- **Expected Cost:** ~$50-100/month

### Medium Environment (100GB-1TB/day)

- **Splunk:** 30-minute summaries
- **Lambda:** Every 30 minutes, 2-day lookback
- **DynamoDB:** On-demand or provisioned (50 WCU/RCU)
- **Expected Cost:** ~$200-500/month

### Large Environment (>1TB/day)

- **Splunk:** 15-minute summaries, distributed across search heads
- **Lambda:** Every 15 minutes with batching
- **DynamoDB:** Provisioned capacity with auto-scaling
- **S3:** Enable Intelligent-Tiering
- **Consider:** Kinesis Firehose for real-time streaming
- **Expected Cost:** ~$1,000-3,000/month

## Troubleshooting Performance Issues

### Search Takes Too Long

1. Check search job inspector: `Search → Job → Inspect Job`
2. Look for:
   - High `scan_count` → Add more filters
   - High `field_count` → Reduce extracted fields
   - High `result_count` → Verify time window

### Lambda Timeouts

1. Increase Lambda timeout (max 15 minutes)
2. Reduce lookback period
3. Implement pagination for large result sets
4. Consider Step Functions for orchestration

### DynamoDB Throttling

1. Switch to on-demand billing mode
2. Enable DynamoDB auto-scaling
3. Implement exponential backoff in Lambda
4. Batch writes using `batch_write_item`

## Best Practice Architecture

```
┌─────────────┐
│   Splunk    │
│   Indexers  │
└─────┬───────┘
      │ (Off-peak hours: 2-6 AM)
      ▼
┌─────────────┐
│  Summary    │
│  Index      │ (observable_catalog)
└─────┬───────┘
      │ (5-10 min delay)
      ▼
┌─────────────┐
│   Lambda    │ (Hourly: xx:10)
│  Exporter   │
└─────┬───────┘
      │
      ├────────────────┐
      ▼                ▼
┌──────────┐    ┌──────────┐
│ DynamoDB │    │    S3    │
│ (Recent) │    │ (Archive)│
│ 90 days  │    │  Forever │
└──────────┘    └──────────┘
```

**Key Points:**
1. Splunk searches run during off-peak
2. Lambda waits for search completion
3. DynamoDB stores recent/hot data (90 days)
4. S3 archives all historical data
5. Lifecycle policies move old S3 data to Glacier

