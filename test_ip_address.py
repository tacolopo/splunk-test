#!/usr/bin/env python3

import json
import boto3
from datetime import datetime

def test_dynamodb_ip_storage():
    print("Testing DynamoDB IP address storage...")
    print("=" * 60)
    
    dynamodb = boto3.client('dynamodb', region_name='us-east-1')
    table_name = 'observable_catalog'
    
    test_ip = "1.2.3.4"
    indicator_type = "ip"
    composite_key = f"{indicator_type}#{test_ip}"
    
    print(f"Test IP Address: {test_ip}")
    print(f"Indicator Type: {indicator_type}")
    print(f"Composite Key: {composite_key}")
    print()
    
    test_item = {
        'indicator_key': {'S': composite_key},
        'indicator': {'S': test_ip},
        'indicator_type': {'S': indicator_type},
        'first_seen': {'S': '2024-01-15T10:00:00Z'},
        'last_seen': {'S': '2024-01-20T15:30:00Z'},
        'total_hits': {'N': '42'},
        'days_seen': {'N': '5.2'},
        'src_ips': {'SS': ['10.0.0.1', '10.0.0.2']},
        'dest_ips': {'SS': ['192.168.1.1']},
        'users': {'SS': ['user1', 'user2']},
        'export_timestamp': {'S': datetime.now().isoformat() + 'Z'}
    }
    
    try:
        print("Attempting to write test item to DynamoDB...")
        dynamodb.put_item(
            TableName=table_name,
            Item=test_item
        )
        print("✓ Successfully wrote IP address to DynamoDB!")
        print()
        
        print("Retrieving the item back...")
        response = dynamodb.get_item(
            TableName=table_name,
            Key={'indicator_key': {'S': composite_key}}
        )
        
        if 'Item' in response:
            item = response['Item']
            print("✓ Successfully retrieved IP address from DynamoDB!")
            print()
            print("Retrieved data:")
            print(f"  Indicator: {item.get('indicator', {}).get('S', 'N/A')}")
            print(f"  Type: {item.get('indicator_type', {}).get('S', 'N/A')}")
            print(f"  First Seen: {item.get('first_seen', {}).get('S', 'N/A')}")
            print(f"  Last Seen: {item.get('last_seen', {}).get('S', 'N/A')}")
            print(f"  Total Hits: {item.get('total_hits', {}).get('N', 'N/A')}")
            print(f"  Source IPs: {item.get('src_ips', {}).get('SS', [])}")
        else:
            print("✗ Item not found in DynamoDB")
            
    except dynamodb.exceptions.ResourceNotFoundException:
        print(f"✗ Table '{table_name}' does not exist. Create it first using:")
        print(f"  python create_dynamodb_table.py")
    except Exception as e:
        print(f"✗ Error: {e}")
        print()
        print("Make sure:")
        print("  1. DynamoDB table exists (run create_dynamodb_table.py)")
        print("  2. AWS credentials are configured")
        print("  3. You have write permissions to the table")

if __name__ == '__main__':
    test_dynamodb_ip_storage()

