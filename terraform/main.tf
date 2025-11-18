terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "observables" {
  bucket = var.s3_bucket_name

  tags = {
    Name        = "Splunk Observables"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "observables" {
  bucket = aws_s3_bucket.observables.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "observables" {
  bucket = aws_s3_bucket.observables.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "observables" {
  bucket = aws_s3_bucket.observables.id

  rule {
    id     = "archive-old-observables"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

resource "aws_dynamodb_table" "observable_catalog" {
  name           = var.dynamodb_table_name
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "indicator_key"

  attribute {
    name = "indicator_key"
    type = "S"
  }

  attribute {
    name = "indicator_type"
    type = "S"
  }

  attribute {
    name = "last_seen"
    type = "S"
  }

  global_secondary_index {
    name            = "indicator-type-index"
    hash_key        = "indicator_type"
    range_key       = "last_seen"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name        = "Observable Catalog"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret" "splunk_credentials" {
  name        = "splunk/credentials"
  description = "Splunk API credentials for observable export"

  tags = {
    Name        = "Splunk Credentials"
    Environment = var.environment
  }
}

resource "aws_iam_role" "lambda_execution" {
  name = "splunk-observable-exporter-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "Lambda Execution Role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "splunk-observable-exporter-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${aws_s3_bucket.observables.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:UpdateItem",
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ]
        Resource = [
          aws_dynamodb_table.observable_catalog.arn,
          "${aws_dynamodb_table.observable_catalog.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.splunk_credentials.arn
      }
    ]
  })
}

resource "aws_lambda_layer_version" "dependencies" {
  filename            = "lambda_layer.zip"
  layer_name          = "splunk-exporter-dependencies"
  compatible_runtimes = ["python3.11"]
  source_code_hash    = filebase64sha256("lambda_layer.zip")

  description = "Dependencies for Splunk observable exporter"
}

resource "aws_lambda_function" "observable_exporter" {
  filename         = "lambda_function.zip"
  function_name    = "splunk-observable-exporter"
  role            = aws_iam_role.lambda_execution.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = filebase64sha256("lambda_function.zip")
  runtime         = "python3.11"
  timeout         = 900
  memory_size     = 512

  layers = [aws_lambda_layer_version.dependencies.arn]

  environment {
    variables = {
      SPLUNK_SECRET_NAME = aws_secretsmanager_secret.splunk_credentials.name
      S3_BUCKET         = aws_s3_bucket.observables.id
      S3_PREFIX         = "observables"
      DYNAMODB_TABLE    = aws_dynamodb_table.observable_catalog.name
      LOOKBACK_DAYS     = var.lookback_days
      EXPORT_FORMAT     = "all"
      AWS_REGION        = var.aws_region
    }
  }

  tags = {
    Name        = "Splunk Observable Exporter"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.observable_exporter.function_name}"
  retention_in_days = 30

  tags = {
    Name        = "Lambda Logs"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_event_rule" "hourly_export" {
  name                = "splunk-observable-export-hourly"
  description         = "Trigger Splunk observable export hourly"
  schedule_expression = var.schedule_expression

  tags = {
    Name        = "Hourly Export Schedule"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.hourly_export.name
  target_id = "SplunkObservableExporterLambda"
  arn       = aws_lambda_function.observable_exporter.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.observable_exporter.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly_export.arn
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "splunk-observable-exporter-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name        = "Errors"
  namespace          = "AWS/Lambda"
  period             = 300
  statistic          = "Sum"
  threshold          = 0
  alarm_description  = "Alert when lambda function errors"
  treat_missing_data = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.observable_exporter.function_name
  }

  tags = {
    Name        = "Lambda Error Alarm"
    Environment = var.environment
  }
}

