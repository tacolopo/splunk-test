variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "s3_bucket_name" {
  description = "S3 bucket name for observable storage"
  type        = string
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for observable catalog"
  type        = string
  default     = "observable_catalog"
}

variable "lookback_days" {
  description = "Number of days to look back in Splunk"
  type        = number
  default     = 1
}

variable "schedule_expression" {
  description = "EventBridge schedule expression for Lambda"
  type        = string
  default     = "rate(1 hour)"
}

