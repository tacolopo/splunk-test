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
echo ""
echo "✅ Deployment packages created successfully!"
echo ""
echo "Next steps:"
echo ""
echo "1. Move packages to terraform directory:"
echo "   mv lambda_layer.zip terraform/"
echo "   mv lambda_function.zip terraform/"
echo ""
echo "2. Store Splunk credentials in AWS Secrets Manager:"
echo "   aws secretsmanager create-secret \\"
echo "     --name splunk/credentials \\"
echo "     --secret-string '{\"host\":\"splunk.example.com\",\"port\":\"8089\",\"username\":\"user\",\"password\":\"pass\",\"scheme\":\"https\"}' \\"
echo "     --region us-east-1"
echo ""
echo "3. Configure Terraform variables:"
echo "   cd terraform"
echo "   cp terraform.tfvars.example terraform.tfvars"
echo "   # Edit terraform.tfvars with your values"
echo ""
echo "4. Deploy infrastructure:"
echo "   terraform init"
echo "   terraform plan"
echo "   terraform apply"
echo ""
echo "See terraform/DEPLOYMENT.md for detailed instructions."

