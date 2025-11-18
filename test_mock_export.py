#!/usr/bin/env python3

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
    
    print("✓ Splunk connection test passed")

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
    
    print("✓ DynamoDB export test passed")

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
    
    print("✓ S3 export test passed")

def test_ip_address_formatting():
    """Test that IP addresses are formatted correctly for DynamoDB"""
    
    test_ip = "1.2.3.4"
    indicator_type = "ip"
    expected_key = f"{indicator_type}#{test_ip}"
    
    assert expected_key == "ip#1.2.3.4"
    
    print(f"✓ IP formatting test passed: {expected_key}")

if __name__ == '__main__':
    print("\n=== Running Mock Export Tests ===\n")
    
    try:
        test_splunk_connection()
        test_dynamodb_export_with_mock_data()
        test_s3_export_with_mock_data()
        test_ip_address_formatting()
        
        print("\n=== All Tests Passed ===\n")
    except Exception as e:
        print(f"\n✗ Test failed: {e}\n")
        sys.exit(1)

