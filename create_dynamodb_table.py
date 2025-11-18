#!/usr/bin/env python3

import json
import boto3
import argparse
import sys

def create_table(dynamodb_client, schema_file):
    with open(schema_file, 'r') as f:
        schema = json.load(f)
    
    table_name = schema['TableName']
    
    try:
        table = dynamodb_client.create_table(**schema)
        print(f"Creating table {table_name}...")
        table.wait_until_exists()
        print(f"Table {table_name} created successfully!")
    except dynamodb_client.exceptions.ResourceInUseException:
        print(f"Table {table_name} already exists")
    except Exception as e:
        print(f"Error creating table: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Create DynamoDB table for observable catalog')
    parser.add_argument('--schema', '-s', default='dynamodb_schema.json',
                       help='Path to DynamoDB schema file')
    parser.add_argument('--region', '-r', default='us-east-1',
                       help='AWS region')
    parser.add_argument('--profile', '-p', help='AWS profile name')
    
    args = parser.parse_args()
    
    session_kwargs = {'region_name': args.region}
    if args.profile:
        session_kwargs['profile_name'] = args.profile
    
    session = boto3.Session(**session_kwargs)
    dynamodb = session.client('dynamodb')
    
    create_table(dynamodb, args.schema)

if __name__ == '__main__':
    main()

