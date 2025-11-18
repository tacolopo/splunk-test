#!/usr/bin/env python3

import os
import sys
import json
import csv
import boto3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import argparse

PARQUET_AVAILABLE = False

try:
    import splunklib.client as client
    import splunklib.results as results
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logger.error("Error: splunk-sdk not installed. Run: pip install splunk-sdk")
    raise

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SplunkObservableExporter:
    def __init__(self, config: Dict):
        self.config = config
        self.splunk_client = None
        self.s3_client = None
        self.dynamodb_client = None
        
    def get_secret_from_aws_secrets_manager(self, secret_name: str, region: str = None) -> Dict:
        try:
            session = boto3.Session(region_name=region or self.config.get('aws', {}).get('region', 'us-east-1'))
            secrets_client = session.client('secretsmanager')
            response = secrets_client.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except Exception as e:
            logger.error(f"Failed to retrieve secret from AWS Secrets Manager: {e}")
            raise
    
    def get_splunk_credentials(self) -> Dict:
        splunk_config = self.config.get('splunk', {})
        
        if splunk_config.get('use_secrets_manager'):
            secret_name = splunk_config.get('secrets_manager_secret_name')
            if not secret_name:
                raise ValueError("secrets_manager_secret_name required when use_secrets_manager is true")
            secrets = self.get_secret_from_aws_secrets_manager(secret_name)
            return {
                'host': secrets.get('host') or os.getenv('SPLUNK_HOST') or splunk_config.get('host'),
                'port': int(secrets.get('port') or os.getenv('SPLUNK_PORT', '8089') or splunk_config.get('port', 8089)),
                'username': secrets.get('username') or os.getenv('SPLUNK_USERNAME') or splunk_config.get('username'),
                'password': secrets.get('password') or os.getenv('SPLUNK_PASSWORD') or splunk_config.get('password'),
                'scheme': secrets.get('scheme') or os.getenv('SPLUNK_SCHEME', 'https') or splunk_config.get('scheme', 'https')
            }
        else:
            return {
                'host': os.getenv('SPLUNK_HOST') or splunk_config.get('host'),
                'port': int(os.getenv('SPLUNK_PORT', '8089') or splunk_config.get('port', 8089)),
                'username': os.getenv('SPLUNK_USERNAME') or splunk_config.get('username'),
                'password': os.getenv('SPLUNK_PASSWORD') or splunk_config.get('password'),
                'scheme': os.getenv('SPLUNK_SCHEME', 'https') or splunk_config.get('scheme', 'https')
            }
        
    def connect_splunk(self):
        try:
            creds = self.get_splunk_credentials()
            
            if not all([creds.get('host'), creds.get('username'), creds.get('password')]):
                raise ValueError("Splunk credentials incomplete. Set environment variables or use AWS Secrets Manager.")
            
            self.splunk_client = client.connect(
                host=creds['host'],
                port=creds['port'],
                username=creds['username'],
                password=creds['password'],
                scheme=creds['scheme']
            )
            logger.info("Connected to Splunk successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Splunk: {e}")
            raise
    
    def connect_aws(self):
        aws_config = self.config.get('aws', {})
        aws_profile = aws_config.get('profile')
        aws_region = aws_config.get('region', 'us-east-1')
        
        session_kwargs = {'region_name': aws_region}
        if aws_profile:
            session_kwargs['profile_name'] = aws_profile
        
        session = boto3.Session(**session_kwargs)
        
        if aws_config.get('s3_bucket'):
            self.s3_client = session.client('s3')
            logger.info("S3 client initialized")
        
        if aws_config.get('dynamodb_table'):
            self.dynamodb_client = session.client('dynamodb', region_name=aws_region)
            logger.info("DynamoDB client initialized")
    
    def load_spl_query(self, query_file: str) -> str:
        query_path = Path(__file__).parent / 'splunk_queries' / query_file
        if not query_path.exists():
            raise FileNotFoundError(f"Query file not found: {query_path}")
        
        with open(query_path, 'r') as f:
            query = f.read().strip()
        
        return query
    
    def execute_splunk_search(self, query: str, lookback_days: int = 1) -> List[Dict]:
        query = query.replace('$lookback$', str(lookback_days))
        # Clean up query - remove any leading/trailing whitespace and ensure proper formatting
        query = query.strip()
        # Normalize whitespace - replace multiple spaces/newlines with single space, but preserve pipe separators
        import re
        # Replace newlines with spaces, but keep pipes at start of lines
        query = re.sub(r'\n\s*\|', ' |', query)  # Handle pipes at start of lines
        query = re.sub(r'\s+', ' ', query)  # Replace multiple spaces with single space
        query = query.strip()
        
        # Splunk REST API requires 'search' command prefix for some queries
        if not query.lower().startswith('search '):
            query = f'search {query}'
        
        logger.info(f"Executing Splunk search (lookback: {lookback_days} days)")
        logger.info(f"Query (first 500 chars): {query[:500]}")
        logger.info(f"Query length: {len(query)}")
        
        try:
            job = self.splunk_client.jobs.create(query, **{
                'exec_mode': 'normal',
                'output_mode': 'json'
            })
            
            while not job.is_done():
                job.refresh()
            
            reader = results.ResultsReader(job.results())
            results_list = []
            
            for result in reader:
                if isinstance(result, dict):
                    results_list.append(result)
            
            logger.info(f"Retrieved {len(results_list)} observables from Splunk")
            return results_list
            
        except Exception as e:
            logger.error(f"Error executing Splunk search: {e}")
            raise
    
    def export_to_s3(self, data: List[Dict], date_prefix: str = None, master_file: bool = True):
        if not self.s3_client:
            logger.warning("S3 client not configured, skipping S3 export")
            return
        
        bucket = self.config['aws']['s3_bucket']
        s3_prefix = self.config['aws'].get('s3_prefix', 'observables')
        
        if master_file:
            parquet_key = f"{s3_prefix}/master.parquet"
            csv_key = f"{s3_prefix}/master.csv"
            json_key = f"{s3_prefix}/master.json"
            
            temp_parquet = Path('/tmp') / "observables_master.parquet"
            temp_csv = Path('/tmp') / "observables_master.csv"
            temp_json = Path('/tmp') / "observables_master.json"
            
            existing_master_data = self._load_existing_master_file(bucket, parquet_key)
            if existing_master_data:
                logger.info(f"Found existing master file with {len(existing_master_data)} records, merging...")
                data = self._merge_master_data(existing_master_data, data)
                logger.info(f"After merge: {len(data)} total records")
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            date_prefix = date_prefix or datetime.now().strftime('%Y-%m-%d')
            
            parquet_key = f"{s3_prefix}/date={date_prefix}/observables_{timestamp}.parquet"
            csv_key = f"{s3_prefix}/date={date_prefix}/observables_{timestamp}.csv"
            json_key = f"{s3_prefix}/date={date_prefix}/observables_{timestamp}.json"
            
            temp_parquet = Path('/tmp') / f"observables_{timestamp}.parquet"
            temp_csv = Path('/tmp') / f"observables_{timestamp}.csv"
            temp_json = Path('/tmp') / f"observables_{timestamp}.json"
        
        try:
            if data:
                fieldnames = set()
                for row in data:
                    fieldnames.update(row.keys())
                fieldnames = sorted(list(fieldnames))
                
                logger.info("Parquet export disabled, using CSV/JSON only")
                
                with open(temp_csv, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(
                        csvfile, 
                        fieldnames=fieldnames, 
                        extrasaction='ignore',
                        quoting=csv.QUOTE_ALL,
                        escapechar='\\'
                    )
                    writer.writeheader()
                    for row in data:
                        cleaned_row = {}
                        for k, v in row.items():
                            if v is None:
                                cleaned_row[k] = ''
                            elif isinstance(v, list):
                                cleaned_row[k] = '|'.join(str(x) for x in v if x is not None)
                            else:
                                cleaned_row[k] = str(v) if v is not None else ''
                        writer.writerow(cleaned_row)
                
                self.s3_client.upload_file(str(temp_csv), bucket, csv_key)
                if master_file:
                    logger.info(f"Uploaded master CSV file to s3://{bucket}/{csv_key}")
                else:
                    logger.info(f"Uploaded CSV to s3://{bucket}/{csv_key}")
                
                with open(temp_json, 'w', encoding='utf-8') as jsonfile:
                    json.dump(data, jsonfile, indent=2, ensure_ascii=False)
                
                self.s3_client.upload_file(str(temp_json), bucket, json_key)
                if master_file:
                    logger.info(f"Uploaded master JSON file to s3://{bucket}/{json_key}")
                else:
                    logger.info(f"Uploaded JSON to s3://{bucket}/{json_key}")
            else:
                logger.warning("No data to export to S3")
                
        except Exception as e:
            logger.error(f"Error exporting to S3: {e}")
            raise
        finally:
            if temp_parquet.exists():
                temp_parquet.unlink()
            if temp_csv.exists():
                temp_csv.unlink()
            if temp_json.exists():
                temp_json.unlink()
    
    def export_to_dynamodb(self, data: List[Dict]):
        if not self.dynamodb_client:
            logger.warning("DynamoDB client not configured, skipping DynamoDB export")
            return
        
        table_name = self.config['aws']['dynamodb_table']
        
        logger.info(f"Exporting {len(data)} items to DynamoDB table: {table_name}")
        
        try:
            for item in data:
                indicator = item.get('indicator', '')
                indicator_type = item.get('indicator_type', '')
                
                if not indicator or not indicator_type:
                    continue
                
                composite_key = f"{indicator_type}#{indicator}"
                
                def convert_to_dynamodb_value(value):
                    if isinstance(value, str):
                        return {'S': value}
                    elif isinstance(value, (int, float)):
                        return {'N': str(value)}
                    elif isinstance(value, list):
                        return {'SS': [str(x) for x in value]}
                    elif value is None:
                        return {'NULL': True}
                    else:
                        return {'S': str(value)}
                
                def parse_iso_timestamp(ts_str):
                    try:
                        if ts_str and ts_str != '':
                            return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    except:
                        pass
                    return None
                
                existing_item = None
                try:
                    response = self.dynamodb_client.get_item(
                        TableName=table_name,
                        Key={'indicator_key': {'S': composite_key}}
                    )
                    if 'Item' in response:
                        existing_item = response['Item']
                except Exception as e:
                    logger.warning(f"Could not read existing item {composite_key}: {e}")
                
                new_first_seen = item.get('first_seen', '')
                new_last_seen = item.get('last_seen', '')
                new_total_hits = int(item.get('total_hits', 0))
                
                if existing_item:
                    existing_first_seen = existing_item.get('first_seen', {}).get('S', '')
                    existing_last_seen = existing_item.get('last_seen', {}).get('S', '')
                    existing_total_hits = int(existing_item.get('total_hits', {}).get('N', '0'))
                    
                    existing_first_ts = parse_iso_timestamp(existing_first_seen)
                    existing_last_ts = parse_iso_timestamp(existing_last_seen)
                    new_first_ts = parse_iso_timestamp(new_first_seen)
                    new_last_ts = parse_iso_timestamp(new_last_seen)
                    
                    if existing_first_ts and new_first_ts:
                        final_first_seen = min(existing_first_ts, new_first_ts).isoformat().replace('+00:00', 'Z')
                    elif existing_first_ts:
                        final_first_seen = existing_first_seen
                    elif new_first_ts:
                        final_first_seen = new_first_seen
                    else:
                        final_first_seen = datetime.now().isoformat() + 'Z'
                    
                    if existing_last_ts and new_last_ts:
                        final_last_seen = max(existing_last_ts, new_last_ts).isoformat().replace('+00:00', 'Z')
                    elif existing_last_ts:
                        final_last_seen = existing_last_seen
                    elif new_last_ts:
                        final_last_seen = new_last_seen
                    else:
                        final_last_seen = datetime.now().isoformat() + 'Z'
                    
                    final_total_hits = existing_total_hits + new_total_hits
                    
                    final_first_ts = parse_iso_timestamp(final_first_seen)
                    final_last_ts = parse_iso_timestamp(final_last_seen)
                    if final_first_ts and final_last_ts:
                        days_seen = round((final_last_ts - final_first_ts).total_seconds() / 86400, 2)
                    else:
                        days_seen = 0
                else:
                    final_first_seen = new_first_seen if new_first_seen else datetime.now().isoformat() + 'Z'
                    final_last_seen = new_last_seen if new_last_seen else datetime.now().isoformat() + 'Z'
                    final_total_hits = new_total_hits
                    
                    final_first_ts = parse_iso_timestamp(final_first_seen)
                    final_last_ts = parse_iso_timestamp(final_last_seen)
                    if final_first_ts and final_last_ts:
                        days_seen = round((final_last_ts - final_first_ts).total_seconds() / 86400, 2)
                    else:
                        days_seen = item.get('days_seen', 0)
                
                update_parts = []
                expression_attribute_names = {}
                expression_attribute_values = {}
                
                update_parts.append("#ind = :ind")
                expression_attribute_names['#ind'] = 'indicator'
                expression_attribute_values[':ind'] = convert_to_dynamodb_value(indicator)
                
                update_parts.append("#it = :it")
                expression_attribute_names['#it'] = 'indicator_type'
                expression_attribute_values[':it'] = convert_to_dynamodb_value(indicator_type)
                
                update_parts.append("first_seen = :fs")
                expression_attribute_values[':fs'] = convert_to_dynamodb_value(final_first_seen)
                
                update_parts.append("last_seen = :ls")
                expression_attribute_values[':ls'] = convert_to_dynamodb_value(final_last_seen)
                
                update_parts.append("total_hits = :th")
                expression_attribute_values[':th'] = convert_to_dynamodb_value(final_total_hits)
                
                update_parts.append("days_seen = :ds")
                expression_attribute_values[':ds'] = convert_to_dynamodb_value(float(days_seen))
                
                if 'types' in item and item['types']:
                    ts_val = convert_to_dynamodb_value(item.get('types', []))
                    if ts_val:
                        update_parts.append("#ts = :ts")
                        expression_attribute_names['#ts'] = 'types'
                        expression_attribute_values[':ts'] = ts_val
                
                if 'src_ips' in item and item['src_ips']:
                    sip_val = convert_to_dynamodb_value(item.get('src_ips', []))
                    if sip_val:
                        update_parts.append("src_ips = :sip")
                        expression_attribute_values[':sip'] = sip_val
                
                if 'dest_ips' in item and item['dest_ips']:
                    dip_val = convert_to_dynamodb_value(item.get('dest_ips', []))
                    if dip_val:
                        update_parts.append("dest_ips = :dip")
                        expression_attribute_values[':dip'] = dip_val
                
                if 'users' in item and item['users']:
                    usr_val = convert_to_dynamodb_value(item.get('users', []))
                    if usr_val:
                        update_parts.append("#usrs = :usr")
                        expression_attribute_names['#usrs'] = 'users'
                        expression_attribute_values[':usr'] = usr_val
                
                if 'sourcetypes' in item and item['sourcetypes']:
                    st_val = convert_to_dynamodb_value(item.get('sourcetypes', []))
                    if st_val:
                        update_parts.append("#st = :st")
                        expression_attribute_names['#st'] = 'sourcetypes'
                        expression_attribute_values[':st'] = st_val
                
                if 'actions' in item and item['actions']:
                    acts_val = convert_to_dynamodb_value(item.get('actions', []))
                    if acts_val:
                        update_parts.append("#acts = :acts")
                        expression_attribute_names['#acts'] = 'actions'
                        expression_attribute_values[':acts'] = acts_val
                
                
                update_parts.append("export_timestamp = :et")
                expression_attribute_values[':et'] = convert_to_dynamodb_value(datetime.now().isoformat() + 'Z')
                
                ttl_days = int(os.getenv('DYNAMODB_TTL_DAYS', '90'))
                ttl_timestamp = int((datetime.now().timestamp() + (ttl_days * 86400)))
                update_parts.append("#ttl = :ttl")
                expression_attribute_names['#ttl'] = 'ttl'
                expression_attribute_values[':ttl'] = convert_to_dynamodb_value(ttl_timestamp)
                
                update_expression = "SET " + ", ".join(update_parts)
                
                update_kwargs = {
                    'TableName': table_name,
                    'Key': {
                        'indicator_key': {'S': composite_key}
                    },
                    'UpdateExpression': update_expression,
                    'ExpressionAttributeValues': expression_attribute_values
                }
                
                if expression_attribute_names:
                    update_kwargs['ExpressionAttributeNames'] = expression_attribute_names
                
                self.dynamodb_client.update_item(**update_kwargs)
            
            logger.info("Successfully exported to DynamoDB")
            
        except Exception as e:
            logger.error(f"Error exporting to DynamoDB: {e}")
            raise
    
    def export_to_rds_postgres(self, data: List[Dict]):
        try:
            import psycopg2
        except ImportError:
            logger.warning("psycopg2 not installed, skipping RDS export")
            return
        
        rds_config = self.config.get('aws', {}).get('rds', {})
        if not rds_config:
            logger.warning("RDS configuration not found, skipping RDS export")
            return
        
        try:
            rds_host = os.getenv('RDS_HOST') or rds_config.get('host')
            rds_port = int(os.getenv('RDS_PORT', '5432') or rds_config.get('port', 5432))
            rds_database = os.getenv('RDS_DATABASE') or rds_config.get('database')
            rds_user = os.getenv('RDS_USER') or rds_config.get('user')
            rds_password = os.getenv('RDS_PASSWORD') or rds_config.get('password')
            
            if rds_config.get('use_secrets_manager'):
                secret_name = rds_config.get('secrets_manager_secret_name')
                if secret_name:
                    secrets = self.get_secret_from_aws_secrets_manager(secret_name)
                    rds_host = secrets.get('host') or rds_host
                    rds_port = int(secrets.get('port', rds_port) or rds_port)
                    rds_database = secrets.get('database') or rds_database
                    rds_user = secrets.get('user') or secrets.get('username') or rds_user
                    rds_password = secrets.get('password') or rds_password
            
            if not all([rds_host, rds_database, rds_user, rds_password]):
                raise ValueError("RDS credentials incomplete. Set environment variables or use AWS Secrets Manager.")
            
            conn = psycopg2.connect(
                host=rds_host,
                port=rds_port,
                database=rds_database,
                user=rds_user,
                password=rds_password
            )
            
            cur = conn.cursor()
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS observable_catalog (
                    indicator_key VARCHAR(512) PRIMARY KEY,
                    indicator VARCHAR(512) NOT NULL,
                    indicator_type VARCHAR(50) NOT NULL,
                    first_seen TIMESTAMP,
                    last_seen TIMESTAMP,
                    total_hits BIGINT,
                    days_seen FLOAT,
                    src_ips TEXT[],
                    dest_ips TEXT[],
                    users TEXT[],
                    sourcetypes TEXT[],
                    actions TEXT[],
                    unique_src_ips INTEGER,
                    unique_dest_ips INTEGER,
                    export_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(indicator, indicator_type)
                )
            """)
            
            for item in data:
                indicator = item.get('indicator', '')
                indicator_type = item.get('indicator_type', '')
                
                if not indicator or not indicator_type:
                    continue
                
                composite_key = f"{indicator_type}#{indicator}"
                
                def parse_multivalue(value):
                    if isinstance(value, list):
                        return value
                    if isinstance(value, str) and '|' in value:
                        return [x.strip() for x in value.split('|') if x.strip()]
                    return [value] if value else []
                
                cur.execute("""
                    INSERT INTO observable_catalog (
                        indicator_key, indicator, indicator_type, first_seen, last_seen,
                        total_hits, days_seen, src_ips, dest_ips, users, sourcetypes,
                        actions, unique_src_ips, unique_dest_ips, export_timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (indicator_key) DO UPDATE SET
                        first_seen = LEAST(observable_catalog.first_seen, EXCLUDED.first_seen),
                        last_seen = GREATEST(observable_catalog.last_seen, EXCLUDED.last_seen),
                        total_hits = observable_catalog.total_hits + EXCLUDED.total_hits,
                        days_seen = EXCLUDED.days_seen,
                        src_ips = (SELECT array_agg(DISTINCT elem) FROM unnest(observable_catalog.src_ips || EXCLUDED.src_ips) elem),
                        dest_ips = (SELECT array_agg(DISTINCT elem) FROM unnest(observable_catalog.dest_ips || EXCLUDED.dest_ips) elem),
                        users = (SELECT array_agg(DISTINCT elem) FROM unnest(observable_catalog.users || EXCLUDED.users) elem),
                        sourcetypes = (SELECT array_agg(DISTINCT elem) FROM unnest(observable_catalog.sourcetypes || EXCLUDED.sourcetypes) elem),
                        actions = (SELECT array_agg(DISTINCT elem) FROM unnest(observable_catalog.actions || EXCLUDED.actions) elem),
                        unique_src_ips = GREATEST(COALESCE(observable_catalog.unique_src_ips, 0), COALESCE(EXCLUDED.unique_src_ips, 0)),
                        unique_dest_ips = GREATEST(COALESCE(observable_catalog.unique_dest_ips, 0), COALESCE(EXCLUDED.unique_dest_ips, 0)),
                        export_timestamp = EXCLUDED.export_timestamp
                """, (
                    composite_key,
                    indicator,
                    indicator_type,
                    datetime.fromisoformat(item.get('first_seen', '').replace('Z', '+00:00')) if item.get('first_seen') else None,
                    datetime.fromisoformat(item.get('last_seen', '').replace('Z', '+00:00')) if item.get('last_seen') else None,
                    int(item.get('total_hits', 0)),
                    float(item.get('days_seen', 0)) if item.get('days_seen') else None,
                    parse_multivalue(item.get('src_ips')),
                    parse_multivalue(item.get('dest_ips')),
                    parse_multivalue(item.get('users')),
                    parse_multivalue(item.get('sourcetypes')),
                    parse_multivalue(item.get('actions')),
                    int(item.get('unique_src_ips', 0)) if item.get('unique_src_ips') else None,
                    int(item.get('unique_dest_ips', 0)) if item.get('unique_dest_ips') else None,
                    datetime.now()
                ))
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info(f"Successfully exported {len(data)} items to RDS PostgreSQL")
            
        except Exception as e:
            logger.error(f"Error exporting to RDS: {e}")
            raise
    
    def run_export(self, lookback_days: int = 1, export_format: str = 'all'):
        try:
            self.connect_splunk()
            self.connect_aws()
            
            query = self.load_spl_query('export_all_observables.spl')
            data = self.execute_splunk_search(query, lookback_days)
            
            if not data:
                logger.warning("No data to export")
                return
            
            date_prefix = datetime.now().strftime('%Y-%m-%d')
            
            if export_format in ['all', 'dynamodb']:
                self.export_to_dynamodb(data)
            
            if export_format in ['all', 's3']:
                if export_format == 'all':
                    should_update_s3 = self._should_update_s3_master_file()
                    if should_update_s3:
                        s3_data = self.get_merged_data_from_dynamodb()
                        if s3_data:
                            self.export_to_s3(s3_data, master_file=True)
                            logger.info("S3 master file updated with merged DynamoDB data")
                        else:
                            logger.warning("No DynamoDB data available for S3 master file")
                    else:
                        logger.info("S3 master file already updated today, skipping")
                else:
                    self.export_to_s3(data, date_prefix, master_file=False)
            
            if export_format in ['all', 'rds']:
                self.export_to_rds_postgres(data)
            
            logger.info("Export completed successfully")
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise
    
    def get_merged_data_from_dynamodb(self) -> List[Dict]:
        if not self.dynamodb_client:
            logger.warning("DynamoDB client not configured, using Splunk data for S3")
            return []
        
        table_name = self.config['aws']['dynamodb_table']
        logger.info("Reading all merged data from DynamoDB for S3 lifetime master file")
        
        try:
            merged_data = []
            last_evaluated_key = None
            total_scanned = 0
            
            while True:
                scan_kwargs = {
                    'TableName': table_name,
                    'Limit': 100
                }
                if last_evaluated_key:
                    scan_kwargs['ExclusiveStartKey'] = last_evaluated_key
                
                response = self.dynamodb_client.scan(**scan_kwargs)
                total_scanned += response.get('ScannedCount', 0)
                
                for item in response.get('Items', []):
                    indicator_key = item.get('indicator_key', {}).get('S', '')
                    indicator = item.get('indicator', {}).get('S', '')
                    indicator_type = item.get('indicator_type', {}).get('S', '')
                    first_seen = item.get('first_seen', {}).get('S', '')
                    last_seen = item.get('last_seen', {}).get('S', '')
                    total_hits = item.get('total_hits', {}).get('N', '0')
                    days_seen = item.get('days_seen', {}).get('N', '0')
                    
                    def get_string_set(key):
                        val = item.get(key, {})
                        if 'SS' in val:
                            return val['SS']
                        elif 'S' in val:
                            return [val['S']]
                        return []
                    
                    merged_item = {
                        'indicator': indicator,
                        'indicator_type': indicator_type,
                        'first_seen': first_seen,
                        'last_seen': last_seen,
                        'total_hits': int(total_hits),
                        'days_seen': float(days_seen) if days_seen else 0.0,
                        'src_ips': get_string_set('src_ips'),
                        'dest_ips': get_string_set('dest_ips'),
                        'users': get_string_set('users'),
                        'sourcetypes': get_string_set('sourcetypes'),
                        'actions': get_string_set('actions'),
                        'types': get_string_set('types'),
                        'unique_src_ips': int(item.get('unique_src_ips', {}).get('N', '0')),
                        'unique_dest_ips': int(item.get('unique_dest_ips', {}).get('N', '0')),
                        'export_timestamp': datetime.now().isoformat() + 'Z'
                    }
                    merged_data.append(merged_item)
                
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
            
            logger.info(f"Retrieved {len(merged_data)} lifetime records from DynamoDB (scanned {total_scanned} items)")
            return merged_data
            
        except Exception as e:
            logger.error(f"Error reading from DynamoDB for S3 export: {e}")
            logger.warning("Falling back to Splunk data for S3 export")
            return []
    
    def _should_update_s3_master_file(self) -> bool:
        if not self.s3_client:
            return False
        
        bucket = self.config['aws']['s3_bucket']
        s3_prefix = self.config['aws'].get('s3_prefix', 'observables')
        parquet_key = f"{s3_prefix}/master.parquet"
        
        try:
            response = self.s3_client.head_object(Bucket=bucket, Key=parquet_key)
            last_modified = response.get('LastModified')
            
            if last_modified:
                last_modified_date = last_modified.date()
                today = datetime.now().date()
                
                if last_modified_date == today:
                    logger.info(f"S3 master file was last updated today ({last_modified_date}), skipping update")
                    return False
                else:
                    logger.info(f"S3 master file last updated on {last_modified_date}, updating now")
                    return True
            else:
                return True
        except self.s3_client.exceptions.NoSuchKey:
            logger.info("S3 master file does not exist, will create it")
            return True
        except Exception as e:
            logger.warning(f"Could not check S3 master file status: {e}, will attempt update")
            return True
    
    def _load_existing_master_file(self, bucket: str, parquet_key: str) -> List[Dict]:
        try:
            temp_file = Path('/tmp') / 'existing_master.parquet'
            self.s3_client.download_file(bucket, parquet_key, str(temp_file))
            
            logger.warning("Parquet libraries not available, cannot load existing master file")
            temp_file.unlink()
            return []
        except self.s3_client.exceptions.NoSuchKey:
            logger.info("No existing master file found, creating new one")
            return []
        except Exception as e:
            logger.warning(f"Could not load existing master file: {e}, creating new one")
            return []
    
    def _merge_master_data(self, existing_data: List[Dict], new_data: List[Dict]) -> List[Dict]:
        def parse_iso_timestamp(ts_str):
            try:
                if ts_str and ts_str != '' and ts_str != 'None':
                    return datetime.fromisoformat(str(ts_str).replace('Z', '+00:00'))
            except:
                pass
            return None
        
        existing_dict = {}
        for item in existing_data:
            indicator = item.get('indicator', '')
            indicator_type = item.get('indicator_type', '')
            if indicator and indicator_type:
                key = f"{indicator_type}#{indicator}"
                existing_dict[key] = item
        
        merged_dict = existing_dict.copy()
        
        for new_item in new_data:
            indicator = new_item.get('indicator', '')
            indicator_type = new_item.get('indicator_type', '')
            if not indicator or not indicator_type:
                continue
            
            key = f"{indicator_type}#{indicator}"
            
            if key in merged_dict:
                existing = merged_dict[key]
                
                existing_first_seen = existing.get('first_seen', '')
                existing_last_seen = existing.get('last_seen', '')
                existing_total_hits = int(existing.get('total_hits', 0))
                
                new_first_seen = new_item.get('first_seen', '')
                new_last_seen = new_item.get('last_seen', '')
                new_total_hits = int(new_item.get('total_hits', 0))
                
                existing_first_ts = parse_iso_timestamp(existing_first_seen)
                existing_last_ts = parse_iso_timestamp(existing_last_seen)
                new_first_ts = parse_iso_timestamp(new_first_seen)
                new_last_ts = parse_iso_timestamp(new_last_seen)
                
                if existing_first_ts and new_first_ts:
                    final_first_seen = min(existing_first_ts, new_first_ts).isoformat().replace('+00:00', 'Z')
                elif existing_first_ts:
                    final_first_seen = existing_first_seen
                elif new_first_ts:
                    final_first_seen = new_first_seen
                else:
                    final_first_seen = datetime.now().isoformat() + 'Z'
                
                if existing_last_ts and new_last_ts:
                    final_last_seen = max(existing_last_ts, new_last_ts).isoformat().replace('+00:00', 'Z')
                elif existing_last_ts:
                    final_last_seen = existing_last_seen
                elif new_last_ts:
                    final_last_seen = new_last_seen
                else:
                    final_last_seen = datetime.now().isoformat() + 'Z'
                
                final_total_hits = existing_total_hits + new_total_hits
                
                final_first_ts = parse_iso_timestamp(final_first_seen)
                final_last_ts = parse_iso_timestamp(final_last_seen)
                if final_first_ts and final_last_ts:
                    days_seen = round((final_last_ts - final_first_ts).total_seconds() / 86400, 2)
                else:
                    days_seen = existing.get('days_seen', 0)
                
                def merge_lists(existing_val, new_val):
                    existing_list = existing_val if isinstance(existing_val, list) else ([existing_val] if existing_val else [])
                    new_list = new_val if isinstance(new_val, list) else ([new_val] if new_val else [])
                    combined = list(set(existing_list + new_list))
                    return combined if combined else []
                
                merged_dict[key] = {
                    'indicator': indicator,
                    'indicator_type': indicator_type,
                    'first_seen': final_first_seen,
                    'last_seen': final_last_seen,
                    'total_hits': final_total_hits,
                    'days_seen': days_seen,
                    'src_ips': merge_lists(existing.get('src_ips', []), new_item.get('src_ips', [])),
                    'dest_ips': merge_lists(existing.get('dest_ips', []), new_item.get('dest_ips', [])),
                    'users': merge_lists(existing.get('users', []), new_item.get('users', [])),
                    'sourcetypes': merge_lists(existing.get('sourcetypes', []), new_item.get('sourcetypes', [])),
                    'actions': merge_lists(existing.get('actions', []), new_item.get('actions', [])),
                    'types': merge_lists(existing.get('types', []), new_item.get('types', [])),
                    'unique_src_ips': max(int(existing.get('unique_src_ips', 0)), int(new_item.get('unique_src_ips', 0))),
                    'unique_dest_ips': max(int(existing.get('unique_dest_ips', 0)), int(new_item.get('unique_dest_ips', 0))),
                    'export_timestamp': datetime.now().isoformat() + 'Z'
                }
            else:
                merged_dict[key] = new_item.copy()
                merged_dict[key]['export_timestamp'] = datetime.now().isoformat() + 'Z'
        
        return list(merged_dict.values())


def load_config(config_path: str) -> Dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Export Splunk observable catalog to AWS')
    parser.add_argument('--config', '-c', default='config.json',
                       help='Path to configuration file (default: config.json)')
    parser.add_argument('--lookback', '-l', type=int, default=1,
                       help='Number of days to look back (default: 1)')
    parser.add_argument('--format', '-f', choices=['all', 's3', 'dynamodb', 'rds'],
                       default='all', help='Export format (default: all)')
    
    args = parser.parse_args()
    
    try:
        config = load_config(args.config)
        exporter = SplunkObservableExporter(config)
        exporter.run_export(lookback_days=args.lookback, export_format=args.format)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

