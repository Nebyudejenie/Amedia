# Arada Intelligence OS — Multi-Region Terraform Configuration
# Deploy Arada across two AWS regions with RDS, ElastiCache, S3, and Route53 failover

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "arada-terraform-state"
    key            = "multi-region/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-lock"
  }
}

# Primary region (US-EAST)
provider "aws" {
  alias  = "us_east"
  region = var.primary_region

  default_tags {
    tags = {
      Project     = "arada"
      Environment = var.environment
      Region      = var.primary_region
      ManagedBy   = "Terraform"
    }
  }
}

# Secondary region (EU-WEST)
provider "aws" {
  alias  = "eu_west"
  region = var.secondary_region

  default_tags {
    tags = {
      Project     = "arada"
      Environment = var.environment
      Region      = var.secondary_region
      ManagedBy   = "Terraform"
    }
  }
}

# ============================================================================
# PRIMARY REGION (US-EAST-1)
# ============================================================================

module "primary" {
  source = "./modules/region"

  providers = {
    aws = aws.us_east
  }

  environment                = var.environment
  region                     = var.primary_region
  region_short               = "us-east"
  vpc_cidr                   = var.primary_vpc_cidr

  # RDS (Primary)
  rds_multi_az              = true
  rds_instance_class        = var.rds_instance_class
  rds_allocated_storage     = var.rds_allocated_storage
  rds_backup_retention_days = var.rds_backup_retention_days
  enable_replication        = true
  replication_region        = var.secondary_region

  # ElastiCache (Primary)
  redis_node_type          = var.redis_node_type
  redis_num_cache_nodes    = 1

  # S3 (Primary with replication)
  s3_replication_enabled = true
  s3_destination_region  = var.secondary_region

  # API Configuration
  api_instance_type = var.api_instance_type
  api_min_size      = var.api_min_size
  api_max_size      = var.api_max_size

  # Monitoring
  enable_monitoring = true
  log_retention_days = var.log_retention_days

  tags = {
    Role = "Primary"
    Failover = "Standby"
  }
}

# ============================================================================
# SECONDARY REGION (EU-WEST-1)
# ============================================================================

module "secondary" {
  source = "./modules/region"

  providers = {
    aws = aws.eu_west
  }

  environment                = var.environment
  region                     = var.secondary_region
  region_short               = "eu-west"
  vpc_cidr                   = var.secondary_vpc_cidr

  # RDS (Replica)
  rds_multi_az              = true
  rds_instance_class        = var.rds_replica_instance_class  # Can be smaller
  rds_allocated_storage     = var.rds_allocated_storage
  rds_backup_retention_days = var.rds_backup_retention_days
  enable_replication        = false  # This is the replica

  # ElastiCache (Replica)
  redis_node_type       = var.redis_node_type
  redis_num_cache_nodes = 1

  # S3 (Replica with cross-region replication)
  s3_replication_enabled = false  # Receives replicated objects

  # API Configuration
  api_instance_type = var.api_instance_class_secondary
  api_min_size      = var.api_min_size_secondary
  api_max_size      = var.api_max_size_secondary

  # Monitoring
  enable_monitoring = true
  log_retention_days = var.log_retention_days

  tags = {
    Role = "Secondary"
    Failover = "Primary"
  }
}

# ============================================================================
# GLOBAL: ROUTE53 & FAILOVER
# ============================================================================

provider "aws" {
  alias  = "global"
  region = "us-east-1"
}

resource "aws_route53_zone" "arada" {
  provider = aws.global
  name     = var.route53_zone_name

  tags = {
    Name = "arada-dns"
  }
}

# Health checks
resource "aws_route53_health_check" "primary" {
  provider = aws.global

  ip_address        = module.primary.api_load_balancer_dns
  port              = 443
  type              = "HTTPS"
  resource_path     = "/system/health"
  failure_threshold = 3
  request_interval  = 30

  tags = {
    Name = "arada-primary-health"
  }
}

resource "aws_route53_health_check" "secondary" {
  provider = aws.global

  ip_address        = module.secondary.api_load_balancer_dns
  port              = 443
  type              = "HTTPS"
  resource_path     = "/system/health"
  failure_threshold = 3
  request_interval  = 30

  tags = {
    Name = "arada-secondary-health"
  }
}

# Failover record (primary)
resource "aws_route53_record" "api_primary" {
  provider = aws.global

  zone_id = aws_route53_zone.arada.zone_id
  name    = "api.${var.route53_zone_name}"
  type    = "A"

  alias {
    name                   = module.primary.api_load_balancer_dns
    zone_id                = module.primary.api_load_balancer_zone_id
    evaluate_target_health = true
  }

  set_identifier           = "Primary-${var.primary_region}"
  failover_routing_policy {
    type = "PRIMARY"
  }

  health_check_id = aws_route53_health_check.primary.id
}

# Failover record (secondary)
resource "aws_route53_record" "api_secondary" {
  provider = aws.global

  zone_id = aws_route53_zone.arada.zone_id
  name    = "api.${var.route53_zone_name}"
  type    = "A"

  alias {
    name                   = module.secondary.api_load_balancer_dns
    zone_id                = module.secondary.api_load_balancer_zone_id
    evaluate_target_health = true
  }

  set_identifier           = "Secondary-${var.secondary_region}"
  failover_routing_policy {
    type = "SECONDARY"
  }

  health_check_id = aws_route53_health_check.secondary.id
}

# ============================================================================
# RDS CROSS-REGION REPLICATION
# ============================================================================

resource "aws_db_instance" "replica" {
  provider = aws.eu_west

  identifier                    = "arada-replica"
  replicate_source_db          = module.primary.rds_instance_id

  skip_final_snapshot          = var.environment == "dev"
  final_snapshot_identifier    = "${var.environment}-arada-replica-final-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  backup_retention_period      = var.rds_backup_retention_days
  backup_window               = "03:00-04:00"
  preferred_maintenance_window = "mon:04:00-mon:05:00"

  publicly_accessible         = false
  multi_az                    = true

  tags = {
    Name = "arada-replica-rds"
  }
}

# ============================================================================
# REDIS CROSS-REGION REPLICATION (Global Datastore)
# ============================================================================

resource "aws_elasticache_global_replication_group" "redis" {
  provider = aws.us_east

  global_replication_group_description = "Arada global Redis"
  primary_replication_group_id          = module.primary.redis_replication_group_id
}

resource "aws_elasticache_replication_group" "replica" {
  provider = aws.eu_west

  replication_group_description = "Arada Redis Replica"
  engine                        = "redis"
  engine_version                = "7.0"
  node_type                     = var.redis_node_type
  num_cache_clusters            = 1
  parameter_group_name          = "default.redis7"
  port                          = 6379

  global_replication_group_id   = aws_elasticache_global_replication_group.redis.id

  tags = {
    Name = "arada-redis-replica"
  }
}

# ============================================================================
# S3 CROSS-REGION REPLICATION
# ============================================================================

resource "aws_s3_bucket_replication_configuration" "primary" {
  provider = aws.us_east

  depends_on = [aws_s3_bucket_versioning.primary]

  bucket = module.primary.s3_bucket_id

  role = aws_iam_role.s3_replication.arn

  rule {
    id       = "replicate-all"
    status   = "Enabled"
    priority = 1

    filter {
      prefix = ""
    }

    destination {
      bucket       = module.secondary.s3_bucket_arn
      storage_class = "STANDARD_IA"

      replication_time {
        status = "Enabled"
        time {
          minutes = 15
        }
      }

      metrics {
        status = "Enabled"
        event_threshold {
          minutes = 15
        }
      }
    }
  }
}

# ============================================================================
# IAM ROLE FOR S3 REPLICATION
# ============================================================================

resource "aws_iam_role" "s3_replication" {
  provider = aws.us_east

  name = "arada-s3-replication"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "s3_replication" {
  provider = aws.us_east

  name = "arada-s3-replication-policy"
  role = aws_iam_role.s3_replication.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetReplicationConfiguration",
          "s3:ListBucket"
        ]
        Resource = module.primary.s3_bucket_arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl"
        ]
        Resource = "${module.primary.s3_bucket_arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ReplicateObject",
          "s3:ReplicateDelete"
        ]
        Resource = "${module.secondary.s3_bucket_arn}/*"
      }
    ]
  })
}

# ============================================================================
# OUTPUTS
# ============================================================================

output "primary_api_endpoint" {
  description = "Primary region API endpoint"
  value       = module.primary.api_load_balancer_dns
}

output "secondary_api_endpoint" {
  description = "Secondary region API endpoint"
  value       = module.secondary.api_load_balancer_dns
}

output "global_api_endpoint" {
  description = "Global API endpoint (with automatic failover)"
  value       = "api.${aws_route53_zone.arada.name}"
}

output "primary_rds_endpoint" {
  description = "Primary RDS endpoint"
  value       = module.primary.rds_endpoint
  sensitive   = true
}

output "secondary_rds_endpoint" {
  description = "Secondary RDS endpoint"
  value       = aws_db_instance.replica.endpoint
  sensitive   = true
}

output "primary_redis_endpoint" {
  description = "Primary Redis endpoint"
  value       = module.primary.redis_endpoint
}

output "secondary_redis_endpoint" {
  description = "Secondary Redis endpoint"
  value       = module.secondary.redis_endpoint
}

output "primary_s3_bucket" {
  description = "Primary region S3 bucket"
  value       = module.primary.s3_bucket_name
}

output "secondary_s3_bucket" {
  description = "Secondary region S3 bucket"
  value       = module.secondary.s3_bucket_name
}

output "health_check_primary_id" {
  description = "Route53 health check for primary"
  value       = aws_route53_health_check.primary.id
}

output "health_check_secondary_id" {
  description = "Route53 health check for secondary"
  value       = aws_route53_health_check.secondary.id
}
