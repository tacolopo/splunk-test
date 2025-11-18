# Example Splunk Queries

## Query a Specific IP Address

Use `query_catalog.spl` with the indicator variable:

```
index=observable_catalog indicator="1.2.3.4"
| stats min(strptime(first_seen,"%Y-%m-%dT%H:%M:%SZ")) as first_seen_epoch
        max(strptime(last_seen,"%Y-%m-%dT%H:%M:%SZ")) as last_seen_epoch
        sum(hit_count) as total_hits
        values(indicator_type) as types
        values(src_ips) as src_ips
        values(dest_ips) as dest_ips
        values(users) as users
| eval first_seen=strftime(first_seen_epoch,"%Y-%m-%dT%H:%M:%SZ"),
      last_seen=strftime(last_seen_epoch,"%Y-%m-%dT%H:%M:%SZ")
| fields - first_seen_epoch last_seen_epoch
```

## Find All IPs Seen in Last 7 Days

```
index=observable_catalog indicator_type="ip" earliest=-7d@d
| stats max(strptime(last_seen,"%Y-%m-%dT%H:%M:%SZ")) as last_seen_epoch
        sum(hit_count) as total_hits
        by indicator
| eval last_seen=strftime(last_seen_epoch,"%Y-%m-%dT%H:%M:%SZ")
| sort -total_hits
| head 100
```

## Find Suspicious Email Addresses (High Hit Count)

```
index=observable_catalog indicator_type="email"
| stats sum(hit_count) as total_hits
        max(strptime(last_seen,"%Y-%m-%dT%H:%M:%SZ")) as last_seen_epoch
        by indicator
| eval last_seen=strftime(last_seen_epoch,"%Y-%m-%dT%H:%M:%SZ")
| where total_hits > 100
| sort -total_hits
```

## Find Hashes Seen Multiple Times

```
index=observable_catalog indicator_type IN ("md5", "sha1", "sha256")
| stats sum(hit_count) as total_hits
        values(indicator_type) as hash_types
        by indicator
| where total_hits > 1
| sort -total_hits
```

## Find User Agents Seen Recently

```
index=observable_catalog indicator_type="ua" earliest=-24h
| stats sum(hit_count) as total_hits
        max(strptime(last_seen,"%Y-%m-%dT%H:%M:%SZ")) as last_seen_epoch
        by indicator
| eval last_seen=strftime(last_seen_epoch,"%Y-%m-%dT%H:%M:%SZ")
| sort -last_seen_epoch
| head 50
```

## Find Indicators by Type and Date Range

```
index=observable_catalog indicator_type="ip" earliest=-30d@d latest=-1d@d
| stats sum(hit_count) as total_hits
        min(strptime(first_seen,"%Y-%m-%dT%H:%M:%SZ")) as first_seen_epoch
        max(strptime(last_seen,"%Y-%m-%dT%H:%M:%SZ")) as last_seen_epoch
        by indicator
| eval first_seen=strftime(first_seen_epoch,"%Y-%m-%dT%H:%M:%SZ"),
      last_seen=strftime(last_seen_epoch,"%Y-%m-%dT%H:%M:%SZ"),
      days_active=round((last_seen_epoch-first_seen_epoch)/86400, 1)
| where days_active > 7
| sort -total_hits
```

