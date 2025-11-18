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

try:
    import splunklib.client as client
    import splunklib.results as results
except ImportError:
    print("Error: splunk-sdk not installed. Run: pip install splunk-sdk")
    sys.exit(1)

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
        
        logger.info(f"Executing Splunk search (lookback: {lookback_days} days)")
        
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
    
    def export_to_s3(self, data: List[Dict], date_prefix: str):
        if not self.s3_client:
            logger.warning("S3 client not configured, skipping S3 export")
            return
        
        bucket = self.config['aws']['s3_bucket']
        s3_prefix = self.config['aws'].get('s3_prefix', 'observables')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        csv_key = f"{s3_prefix}/date={date_prefix}/observables_{timestamp}.csv"
        json_key = f"{s3_prefix}/date={date_prefix}/observables_{timestamp}.json"
        
        temp_csv = Path('/tmp') / f"observables_{timestamp}.csv"
        temp_json = Path('/tmp') / f"observables_{timestamp}.json"
        
        try:
            if data:
                fieldnames = set()
                for row in data:
                    fieldnames.update(row.keys())
                fieldnames = sorted(list(fieldnames))
                
                with open(temp_csv, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    for row in data:
                        cleaned_row = {}
                        for k, v in row.items():
                            if isinstance(v, list):
                                cleaned_row[k] = '|'.join(str(x) for x in v)
                            else:
                                cleaned_row[k] = v
                        writer.writerow(cleaned_row)
                
                with open(temp_json, 'w', encoding='utf-8') as jsonfile:
                    json.dump(data, jsonfile, indent=2, ensure_ascii=False)
                
                self.s3_client.upload_file(str(temp_csv), bucket, csv_key)
                logger.info(f"Uploaded CSV to s3://{bucket}/{csv_key}")
                
                self.s3_client.upload_file(str(temp_json), bucket, json_key)
                logger.info(f"Uploaded JSON to s3://{bucket}/{json_key}")
            else:
                logger.warning("No data to export to S3")
                
        except Exception as e:
            logger.error(f"Error exporting to S3: {e}")
            raise
        finally:
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
                
                update_parts = []
                expression_attribute_names = {}
                expression_attribute_values = {}
                
                update_parts.append("first_seen = :fs")
                expression_attribute_values[':fs'] = convert_to_dynamodb_value(item.get('first_seen', ''))
                
                update_parts.append("last_seen = :ls")
                expression_attribute_values[':ls'] = convert_to_dynamodb_value(item.get('last_seen', ''))
                
                update_parts.append("total_hits = :th")
                expression_attribute_values[':th'] = convert_to_dynamodb_value(int(item.get('total_hits', 0)))
                
                if 'types' in item and item['types']:
                    update_parts.append("#ts = :ts")
                    expression_attribute_names['#ts'] = 'types'
                    expression_attribute_values[':ts'] = convert_to_dynamodb_value(item.get('types', []))
                
                if 'src_ips' in item and item['src_ips']:
                    update_parts.append("src_ips = :sip")
                    expression_attribute_values[':sip'] = convert_to_dynamodb_value(item.get('src_ips', []))
                
                if 'dest_ips' in item and item['dest_ips']:
                    update_parts.append("dest_ips = :dip")
                    expression_attribute_values[':dip'] = convert_to_dynamodb_value(item.get('dest_ips', []))
                
                if 'users' in item and item['users']:
                    update_parts.append("users = :usr")
                    expression_attribute_values[':usr'] = convert_to_dynamodb_value(item.get('users', []))
                
                if 'days_seen' in item and item.get('days_seen') is not None:
                    update_parts.append("days_seen = :ds")
                    expression_attribute_values[':ds'] = convert_to_dynamodb_value(float(item.get('days_seen', 0)))
                
                update_parts.append("export_timestamp = :et")
                expression_attribute_values[':et'] = convert_to_dynamodb_value(datetime.now().isoformat() + 'Z')
                
                ttl_days = int(os.getenv('DYNAMODB_TTL_DAYS', '90'))
                ttl_timestamp = int((datetime.now().timestamp() + (ttl_days * 86400)))
                update_parts.append("ttl = :ttl")
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
            
            if export_format in ['all', 's3']:
                self.export_to_s3(data, date_prefix)
            
            if export_format in ['all', 'dynamodb']:
                self.export_to_dynamodb(data)
            
            if export_format in ['all', 'rds']:
                self.export_to_rds_postgres(data)
            
            logger.info("Export completed successfully")
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise


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

