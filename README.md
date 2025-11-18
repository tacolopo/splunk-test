# Splunk to AWS Observable Exporter

Automated export of Splunk observables to AWS (DynamoDB and S3).

## Quick Start

1. Build Lambda package:
   ```bash
   ./deploy_lambda.sh
   ```

2. Configure Terraform:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your values
   ```

3. Deploy:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

4. Add Splunk credentials:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id splunk/credentials \
     --secret-string '{"host":"YOUR_HOST","port":"8089","username":"USER","password":"PASS","scheme":"https"}' \
     --region us-east-1
   ```

## Files

- `export_to_aws.py` - Main export logic
- `lambda_function.py` - Lambda handler
- `splunk_queries/` - Splunk query files
- `deploy_lambda.sh` - Build script for Lambda package
- `terraform/` - Infrastructure as Code

See `terraform/terraform.tfvars.example` for configuration options.
