output "s3_bucket_name" {
  description = "Name of the S3 bucket for observables"
  value       = aws_s3_bucket.observables.id
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.observable_catalog.name
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.observable_exporter.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.observable_exporter.arn
}

output "secrets_manager_secret_arn" {
  description = "ARN of the Secrets Manager secret for Splunk credentials"
  value       = aws_secretsmanager_secret.splunk_credentials.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group for Lambda"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

