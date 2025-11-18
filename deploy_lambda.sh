#!/bin/bash

set -e

echo "Building Lambda deployment package..."

rm -rf build/
mkdir -p build/lambda_layer/python
mkdir -p build/lambda_function

echo "Installing dependencies to Lambda layer..."
pip install -r requirements.txt -t build/lambda_layer/python/

echo "Copying application code to Lambda function..."
cp export_to_aws.py build/lambda_function/
cp lambda_function.py build/lambda_function/
cp -r splunk_queries build/lambda_function/

echo "Creating Lambda layer zip..."
cd build/lambda_layer
zip -r ../../lambda_layer.zip python/
cd ../..

echo "Creating Lambda function zip..."
cd build/lambda_function
zip -r ../../lambda_function.zip .
cd ../..

echo "Deployment packages created:"
echo "  - lambda_layer.zip (dependencies)"
echo "  - lambda_function.zip (application code)"

echo ""
echo "Next steps:"
echo "1. Store Splunk credentials in AWS Secrets Manager:"
echo "   aws secretsmanager put-secret-value \\"
echo "     --secret-id splunk/credentials \\"
echo "     --secret-string '{\"host\":\"splunk.example.com\",\"port\":\"8089\",\"username\":\"user\",\"password\":\"pass\",\"scheme\":\"https\"}'"
echo ""
echo "2. Deploy infrastructure with Terraform:"
echo "   cd terraform"
echo "   terraform init"
echo "   terraform plan"
echo "   terraform apply"
echo ""
echo "3. Or deploy Lambda manually:"
echo "   aws lambda create-function \\"
echo "     --function-name splunk-observable-exporter \\"
echo "     --runtime python3.11 \\"
echo "     --role <IAM_ROLE_ARN> \\"
echo "     --handler lambda_function.lambda_handler \\"
echo "     --zip-file fileb://lambda_function.zip \\"
echo "     --timeout 900 \\"
echo "     --memory-size 512"

