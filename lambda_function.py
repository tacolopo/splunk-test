import os
import sys
import json
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sys.path.insert(0, '/opt/python')

from export_to_aws import SplunkObservableExporter

def lambda_handler(event, context):
    logger.info("Starting Splunk observable export")
    
    lookback_days = int(os.environ.get('LOOKBACK_DAYS', '1'))
    export_format = os.environ.get('EXPORT_FORMAT', 'all')
    
    config = {
        'splunk': {
            'use_secrets_manager': True,
            'secrets_manager_secret_name': os.environ.get('SPLUNK_SECRET_NAME', 'splunk/credentials')
        },
        'aws': {
            'region': os.environ.get('AWS_REGION', 'us-east-1'),
            's3_bucket': os.environ.get('S3_BUCKET'),
            's3_prefix': os.environ.get('S3_PREFIX', 'observables'),
            'dynamodb_table': os.environ.get('DYNAMODB_TABLE', 'observable_catalog')
        }
    }
    
    try:
        exporter = SplunkObservableExporter(config)
        exporter.run_export(lookback_days=lookback_days, export_format=export_format)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Export completed successfully',
                'lookback_days': lookback_days,
                'export_format': export_format,
                'timestamp': datetime.now().isoformat()
            })
        }
    except Exception as e:
        logger.error(f"Export failed: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        }

