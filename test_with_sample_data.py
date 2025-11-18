#!/usr/bin/env python3

import boto3
import json
from datetime import datetime
import sys

def populate_test_data():
    """Populate DynamoDB with test IP addresses"""
    
    dynamodb = boto3.client('dynamodb', region_name='us-east-1')
    table_name = 'observable_catalog'
    
    test_observables = [
        {'type': 'ip', 'value': '1.2.3.4', 'hits': 100, 'description': 'External suspicious IP'},
        {'type': 'ip', 'value': '8.8.8.8', 'hits': 50, 'description': 'Google DNS'},
        {'type': 'ip', 'value': '10.0.0.1', 'hits': 200, 'description': 'Internal gateway'},
        {'type': 'ip', 'value': '192.168.1.1', 'hits': 150, 'description': 'Local router'},
        {'type': 'ip', 'value': '203.0.113.5', 'hits': 75, 'description': 'Test network IP'},
        {'type': 'email', 'value': 'user@example.com', 'hits': 30, 'description': 'Test email'},
        {'type': 'md5', 'value': '5d41402abc4b2a76b9719d911017c592', 'hits': 5, 'description': 'Sample hash'},
    ]
    
    print("\n=== Populating Test Data ===\n")
    
    success_count = 0
    fail_count = 0
    
    for obs in test_observables:
        composite_key = f"{obs['type']}#{obs['value']}"
        
        item = {
            'indicator_key': {'S': composite_key},
            'indicator': {'S': obs['value']},
            'indicator_type': {'S': obs['type']},
            'first_seen': {'S': '2024-01-01T00:00:00Z'},
            'last_seen': {'S': datetime.now().isoformat() + 'Z'},
            'total_hits': {'N': str(obs['hits'])},
            'export_timestamp': {'S': datetime.now().isoformat() + 'Z'}
        }
        
        try:
            dynamodb.put_item(TableName=table_name, Item=item)
            print(f"✓ Added {obs['type']:5} {obs['value']:40} ({obs['hits']:3} hits) - {obs['description']}")
            success_count += 1
        except Exception as e:
            print(f"✗ Failed to add {obs['value']}: {e}")
            fail_count += 1
    
    print(f"\n{success_count} items added, {fail_count} failed\n")
    
    print("=== Querying Test Data ===\n")
    
    test_queries = [
        ('ip', '1.2.3.4'),
        ('ip', '8.8.8.8'),
        ('email', 'user@example.com')
    ]
    
    for indicator_type, indicator in test_queries:
        composite_key = f"{indicator_type}#{indicator}"
        
        try:
            response = dynamodb.get_item(
                TableName=table_name,
                Key={'indicator_key': {'S': composite_key}}
            )
            
            if 'Item' in response:
                item = response['Item']
                print(f"✓ Retrieved {indicator_type}: {indicator}")
                print(f"  First seen: {item.get('first_seen', {}).get('S', 'N/A')}")
                print(f"  Last seen:  {item.get('last_seen', {}).get('S', 'N/A')}")
                print(f"  Total hits: {item.get('total_hits', {}).get('N', 'N/A')}")
                print()
            else:
                print(f"✗ Not found: {indicator}")
                print()
        except Exception as e:
            print(f"✗ Query failed for {indicator}: {e}\n")
    
    print("=== Querying by Type (using GSI) ===\n")
    
    try:
        response = dynamodb.query(
            TableName=table_name,
            IndexName='indicator-type-index',
            KeyConditionExpression='indicator_type = :type',
            ExpressionAttributeValues={
                ':type': {'S': 'ip'}
            },
            Limit=10
        )
        
        print(f"Found {response['Count']} IP addresses:")
        for item in response['Items']:
            print(f"  - {item['indicator']['S']} ({item.get('total_hits', {}).get('N', 'N/A')} hits)")
        print()
    except Exception as e:
        print(f"✗ GSI query failed: {e}\n")
    
    print("=== Test Data Summary ===\n")
    
    try:
        response = dynamodb.scan(
            TableName=table_name,
            Select='COUNT'
        )
        print(f"Total items in table: {response['Count']}")
    except Exception as e:
        print(f"✗ Count failed: {e}")

def cleanup_test_data():
    """Remove test data from DynamoDB"""
    
    dynamodb = boto3.client('dynamodb', region_name='us-east-1')
    table_name = 'observable_catalog'
    
    print("\n=== Cleaning Up Test Data ===\n")
    
    try:
        response = dynamodb.scan(TableName=table_name)
        
        for item in response['Items']:
            key = {'indicator_key': item['indicator_key']}
            dynamodb.delete_item(TableName=table_name, Key=key)
            print(f"✓ Deleted {item['indicator']['S']}")
        
        print(f"\n{len(response['Items'])} items deleted\n")
    except Exception as e:
        print(f"✗ Cleanup failed: {e}\n")

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1 and sys.argv[1] == '--cleanup':
            cleanup_test_data()
        else:
            populate_test_data()
            print("\nTo cleanup test data, run:")
            print("  python test_with_sample_data.py --cleanup\n")
    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        sys.exit(1)

