# Solution Architecture

## Overview

Fully automated pipeline for cataloging security observables (IP addresses, emails, hashes, user agents) from Splunk to AWS.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          SPLUNK                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Raw Logs (proxy, email, edr, web, firewall)            │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
│                           │ Scheduled Search (Hourly)           │
│                           │ Time: 0 * * * * (top of hour)      │
│                           │ Window: earliest=-1h@h latest=@h    │
│                           │                                     │
│  ┌────────────────────────▼─────────────────────────────────┐  │
│  │  Summary Index: observable_catalog                       │  │
│  │  - Aggregates: first_seen, last_seen, count              │  │
│  │  - Groups by: indicator, indicator_type                  │  │
│  │  - Extracts: IPs, emails, hashes, user agents            │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ Splunk REST API
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      AWS LAMBDA                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Function: splunk-observable-exporter                    │  │
│  │  Trigger: EventBridge (Hourly at :10)                   │  │
│  │  Runtime: Python 3.11                                    │  │
│  │  Timeout: 15 minutes                                     │  │
│  │  Memory: 512MB                                           │  │
│  │                                                           │  │
│  │  Process:                                                │  │
│  │  1. Retrieve credentials from Secrets Manager           │  │
│  │  2. Query Splunk summary index (last 1 day)            │  │
│  │  3. Transform data                                       │  │
│  │  4. Export to DynamoDB + S3                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────┬───────────────────────┘
                      │                   │
        ┌─────────────▼──────┐   ┌────────▼──────────┐
        │                    │   │                    │
┌───────▼──────────┐  ┌──────▼─────────┐  ┌─────────▼──────────┐
│   DynamoDB       │  │  S3 Bucket     │  │ Secrets Manager    │
│   (Hot Data)     │  │  (Cold Data)   │  │                    │
│                  │  │                │  │ - Splunk Creds     │
│ - Recent IPs     │  │ - All History  │  └────────────────────┘
│ - 90-day TTL     │  │ - CSV + JSON   │
│ - Fast queries   │  │ - Partitioned  │
│ - On-demand      │  │ - Lifecycle    │
│                  │  │   policies     │
└──────────────────┘  └────────────────┘
        │                     │
        │                     │
        ▼                     ▼
┌──────────────────┐  ┌────────────────┐
│  Query Layer     │  │  Analytics     │
│                  │  │                │
│ - API calls      │  │ - Athena SQL   │
│ - Dashboard      │  │ - QuickSight   │
│ - Incident       │  │ - Reports      │
│   Response       │  │                │
└──────────────────┘  └────────────────┘
```

## Data Flow

### 1. Splunk Aggregation (Continuous)

```
Every hour at :00:
- Search indexes: proxy, email, edr, web, firewall
- Extract observables: src_ip, dest_ip, email, hash, user_agent
- Aggregate: earliest(_time), latest(_time), count()
- Write to: observable_catalog summary index
- Performance: ~30 seconds to 5 minutes
```

### 2. Lambda Export (Hourly)

```
Every hour at :10 (10-min delay after Splunk):
- Authenticate: Get credentials from Secrets Manager
- Query: Search observable_catalog for last 24 hours
- Transform: Convert to DynamoDB/S3 format
- Export: 
  - DynamoDB: Upsert records with 90-day TTL
  - S3: Append CSV/JSON files (date-partitioned)
- Performance: ~2-10 minutes
```

### 3. Data Storage

**DynamoDB (Operational)**
```
Purpose: Fast lookups for incident response
Retention: 90 days (automatic TTL)
Key: indicator_type#indicator (e.g., "ip#1.2.3.4")
Indexes: GSI on indicator_type + last_seen
Capacity: On-demand (auto-scales)
```

**S3 (Analytical)**
```
Purpose: Long-term historical analysis
Retention: Unlimited
Format: CSV + JSON
Partitioning: /observables/date=YYYY-MM-DD/
Lifecycle:
  - Day 0-90: S3 Standard
  - Day 90-365: Glacier Instant Retrieval
  - Day 365+: Glacier Deep Archive
```

## Timing and Scheduling

### Optimal Schedule

```
:00 - Splunk scheduled search starts
:02 - Splunk search completes (avg)
:05 - Data indexed in summary index
:10 - Lambda triggered
:12 - Lambda completes
```

**Why 10-minute delay?**
- Ensures Splunk search completion
- Accounts for indexing lag
- Prevents race conditions
- Allows for slow searches

### Alternative Schedules

**High Volume:**
```
Every 15 minutes:
- Splunk: :00, :15, :30, :45
- Lambda: :10, :25, :40, :55
```

**Low Volume:**
```
Daily at 2 AM:
- Splunk: 02:00 (off-peak)
- Lambda: 02:15
```

## Performance Characteristics

### Splunk Search

| Environment | Data Volume | Search Time | Recommended Window |
|-------------|-------------|-------------|-------------------|
| Small       | <100GB/day  | 30-60s      | 1 hour            |
| Medium      | 100GB-1TB   | 1-5 min     | 30 minutes        |
| Large       | >1TB/day    | 5-15 min    | 15 minutes        |

### Lambda Execution

| Observable Count | Execution Time | Memory Used | Cost/Run |
|------------------|----------------|-------------|----------|
| 1,000           | 30s            | 256MB       | $0.0001  |
| 10,000          | 2 min          | 512MB       | $0.001   |
| 100,000         | 10 min         | 1024MB      | $0.01    |
| 1,000,000       | 90 min*        | 2048MB      | $0.10    |

*May require batching or Step Functions

### DynamoDB

| Operation       | Latency | Cost (On-Demand) |
|-----------------|---------|------------------|
| Get single item | 1-5ms   | $0.00000025      |
| Query by type   | 10-50ms | $0.00000025/item |
| Batch write     | 50-100ms| $0.00000125/item |

### S3

| Operation    | Latency | Cost              |
|--------------|---------|-------------------|
| Put object   | 100ms   | $0.005 per 1,000  |
| Get object   | 100ms   | $0.0004 per 1,000 |
| Athena query | 1-30s   | $5 per TB scanned |

## Scalability

### Horizontal Scaling

**Multiple Lambda Functions:**
```
Lambda 1: Export IPs only
Lambda 2: Export emails only
Lambda 3: Export hashes only
Schedule: Staggered by 5 minutes
```

**Multiple Summary Indexes:**
```
observable_catalog_ips
observable_catalog_emails
observable_catalog_hashes
Benefit: Faster, targeted searches
```

### Vertical Scaling

**Lambda:**
- Memory: 256MB → 512MB → 1024MB → 3008MB
- Timeout: 900s → Step Functions for longer jobs
- Concurrency: Reserved concurrency = 1 (prevent parallel runs)

**DynamoDB:**
- Billing: Provisioned → On-Demand (easier scaling)
- Auto-scaling: Enable for provisioned mode
- Global tables: Multi-region for HA

## Disaster Recovery

### Backup Strategy

**DynamoDB:**
- Point-in-time recovery: Enabled
- Backup retention: 35 days
- Cross-region replication: Optional

**S3:**
- Versioning: Enabled
- Replication: Optional cross-region
- Backup: Not needed (S3 is 99.999999999% durable)

### Recovery Procedures

**Lambda failure:**
1. Check CloudWatch logs
2. Increase timeout/memory
3. Re-run manually: `aws lambda invoke`

**Data loss:**
1. DynamoDB: Restore from point-in-time backup
2. S3: Retrieve from versioned objects
3. Re-export from Splunk: Use longer lookback period

## Monitoring and Alerting

### Key Metrics

**Splunk:**
- `savedsearch_name="Observable Catalog*" | stats avg(run_time)`
- Alert if: `run_time > 300` (5 minutes)

**Lambda:**
- Duration: Alert if > 10 minutes
- Errors: Alert on any error
- Throttles: Alert on any throttle

**DynamoDB:**
- ConsumedWriteCapacity: Monitor for throttling
- UserErrors: Alert if > 0

**S3:**
- Bucket size: Track growth rate
- Number of objects: Monitor daily increase

### Dashboards

Create CloudWatch dashboard with:
1. Lambda invocation count and errors
2. DynamoDB consumed capacity
3. S3 bucket size and object count
4. Cost tracking

## Cost Analysis

### Monthly Cost Estimate (1M IPs, 1-hour schedule)

```
DynamoDB:
- Storage (90 days): 5GB × $0.25/GB = $1.25
- Writes: 720 runs × 1M items × $0.00000125 = $900
- Reads: 1,000 queries × $0.00000025 = $0.25
- Total: ~$901

S3:
- Storage: 365GB × $0.023/GB = $8.40
- PUT requests: 720 × $0.005/1000 = $0.004
- Lifecycle: 275GB × $0.004/GB (Glacier) = $1.10
- Total: ~$9.50

Lambda:
- Invocations: 720 × $0.20 per 1M = $0.0001
- Compute: 720 × 10min × 512MB = $6
- Total: ~$6

Secrets Manager:
- Secret storage: $0.40/month
- API calls: 720 × $0.05/10,000 = $0.004
- Total: ~$0.40

TOTAL: ~$917/month
```

**Cost optimization:**
- Reduce DynamoDB writes by increasing lookback window
- Use batch writes to reduce cost
- Decrease summary frequency (2-hour vs 1-hour)
- Optimized cost: ~$100-200/month

## Security Architecture

### Authentication Flow

```
Lambda → Secrets Manager → Retrieve Credentials
      → Splunk API → Authenticate
      → Query Data → Return Results
      → DynamoDB/S3 → Store Data
```

### Encryption

- **In Transit:** TLS 1.2+ everywhere
- **At Rest:**
  - DynamoDB: KMS encryption
  - S3: AES-256 (or KMS)
  - Secrets Manager: KMS encrypted

### IAM Permissions

**Lambda Role:**
```
- secretsmanager:GetSecretValue (Splunk creds)
- dynamodb:UpdateItem, PutItem
- s3:PutObject, PutObjectAcl
- logs:CreateLogGroup, CreateLogStream, PutLogEvents
```

**Principle:** Least privilege - only what's needed

## Future Enhancements

1. **Real-time Streaming:** Kinesis Firehose instead of batch
2. **Threat Intelligence:** Enrich with threat feeds
3. **Alerting:** SNS notifications for high-risk IPs
4. **API Gateway:** REST API for querying observables
5. **Machine Learning:** Anomaly detection with SageMaker
6. **Multi-region:** Deploy Lambda in multiple regions

