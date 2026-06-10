# Arada Multi-Region Terraform Variables

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "primary_region" {
  description = "Primary AWS region"
  type        = string
  default     = "us-east-1"
}

variable "secondary_region" {
  description = "Secondary AWS region for disaster recovery"
  type        = string
  default     = "eu-west-1"
}

variable "primary_vpc_cidr" {
  description = "CIDR block for primary VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "secondary_vpc_cidr" {
  description = "CIDR block for secondary VPC"
  type        = string
  default     = "10.1.0.0/16"
}

variable "route53_zone_name" {
  description = "Route53 domain name (e.g., arada.fun)"
  type        = string
}

# ============================================================================
# RDS Configuration
# ============================================================================

variable "rds_instance_class" {
  description = "RDS instance type for primary"
  type        = string
  default     = "db.t3.medium"

  validation {
    condition = can(regex("^db\\.[a-z0-9]+\\.[a-z0-9]+$", var.rds_instance_class))
    error_message = "RDS instance class must be valid AWS RDS instance type."
  }
}

variable "rds_replica_instance_class" {
  description = "RDS instance type for replica (can be smaller)"
  type        = string
  default     = "db.t3.small"
}

variable "rds_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 100

  validation {
    condition     = var.rds_allocated_storage >= 20 && var.rds_allocated_storage <= 65536
    error_message = "RDS allocated storage must be between 20 and 65536 GB."
  }
}

variable "rds_backup_retention_days" {
  description = "RDS backup retention period in days"
  type        = number
  default     = 30

  validation {
    condition     = var.rds_backup_retention_days >= 1 && var.rds_backup_retention_days <= 35
    error_message = "Backup retention must be between 1 and 35 days."
  }
}

# ============================================================================
# ElastiCache (Redis) Configuration
# ============================================================================

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.medium"

  validation {
    condition = can(regex("^cache\\.[a-z0-9]+\\.[a-z0-9]+$", var.redis_node_type))
    error_message = "Redis node type must be valid AWS ElastiCache type."
  }
}

# ============================================================================
# EC2 / API Configuration
# ============================================================================

variable "api_instance_type" {
  description = "EC2 instance type for API servers (primary)"
  type        = string
  default     = "t3.medium"
}

variable "api_instance_class_secondary" {
  description = "EC2 instance type for API servers (secondary, can be smaller)"
  type        = string
  default     = "t3.small"
}

variable "api_min_size" {
  description = "Minimum number of API instances (primary)"
  type        = number
  default     = 2

  validation {
    condition     = var.api_min_size >= 1 && var.api_min_size <= 10
    error_message = "Min size must be between 1 and 10."
  }
}

variable "api_max_size" {
  description = "Maximum number of API instances (primary)"
  type        = number
  default     = 10

  validation {
    condition     = var.api_max_size >= var.api_min_size && var.api_max_size <= 50
    error_message = "Max size must be >= min size and <= 50."
  }
}

variable "api_min_size_secondary" {
  description = "Minimum number of API instances (secondary)"
  type        = number
  default     = 1
}

variable "api_max_size_secondary" {
  description = "Maximum number of API instances (secondary)"
  type        = number
  default     = 5
}

# ============================================================================
# Monitoring & Logging
# ============================================================================

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30

  validation {
    condition = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.log_retention_days)
    error_message = "Log retention must be a valid CloudWatch retention period."
  }
}

variable "enable_monitoring" {
  description = "Enable enhanced monitoring and dashboards"
  type        = bool
  default     = true
}

# ============================================================================
# Tags
# ============================================================================

variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default = {
    CostCenter = "Engineering"
    Owner      = "Platform"
  }
}
