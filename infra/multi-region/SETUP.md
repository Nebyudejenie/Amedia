# Arada Multi-Region Setup Guide

Deploy Arada Intelligence OS across multiple AWS regions with automatic failover and disaster recovery.

## Prerequisites

- AWS account with appropriate IAM permissions
- Terraform >= 1.5
- AWS CLI configured with credentials
- Domain name (for Route53)
- S3 bucket for Terraform state (create manually first)

```bash
# Create Terraform state bucket
aws s3api create-bucket \
  --bucket arada-terraform-state-$(date +%s) \
  --region us-east-1 \
  --create-bucket-configuration LocationConstraint=us-east-1

# Create DynamoDB table for locking
aws dynamodb create-table \
  --table-name terraform-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

## Step 1: Prepare Configuration

```bash
cd infra/multi-region/terraform

# Copy example configuration
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

**Required values:**
- `environment` — dev, staging, or prod
- `route53_zone_name` — Your domain (e.g., arada.fun)
- AWS region selections

## Step 2: Initialize Terraform

```bash
# Initialize Terraform (downloads providers)
terraform init

# Verify configuration is valid
terraform validate

# See what will be created
terraform plan -out=tfplan
```

Expected outputs:
- VPCs with subnets
- RDS instances (primary + read replica)
- ElastiCache Redis (global datastore)
- Application Load Balancers
- Auto Scaling Groups
- Route53 health checks and failover records

## Step 3: Deploy Infrastructure

```bash
# Apply the plan (creates all resources)
terraform apply tfplan

# Wait ~15-20 minutes for resources to be created

# Verify outputs
terraform output -json
```

Expected timeline:
- VPC creation: 2 min
- RDS primary: 5-8 min
- RDS replica creation: 5-8 min
- ElastiCache: 3-5 min
- EC2/ALB: 3-5 min
- Health checks: 1-2 min

## Step 4: Deploy Applications

Once infrastructure is ready, deploy the API containers to both regions:

### Primary Region (US-EAST)

```bash
# SSH to primary region's EC2 instance
ssh ec2-user@<PRIMARY_EC2_PUBLIC_IP>

# Clone Arada repository
git clone https://github.com/your-org/arada-os.git
cd arada-os

# Configure environment variables
cat > .env << 'EOF'
DB_HOST=<RDS_PRIMARY_ENDPOINT>
DB_PORT=5432
DB_USER=arada
DB_PASSWORD=<STRONG_PASSWORD>
DB_NAME=arada

REDIS_HOST=<REDIS_PRIMARY_ENDPOINT>
REDIS_PORT=6379

MINIO_HOST=<S3_BUCKET_NAME>
MINIO_REGION=us-east-1

JWT_SECRET_KEY=<64_CHAR_SECRET>
EOF

# Start services
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Verify health
curl https://<PRIMARY_API_LB>/system/health
```

### Secondary Region (EU-WEST)

```bash
# Repeat the same steps for secondary region
# But use secondary region endpoints

ssh ec2-user@<SECONDARY_EC2_PUBLIC_IP>

# ... same setup as primary, but:
DB_HOST=<RDS_REPLICA_ENDPOINT>
REDIS_HOST=<REDIS_REPLICA_ENDPOINT>
MINIO_REGION=eu-west-1
```

## Step 5: Verify Multi-Region Setup

### Check Replication Status

```bash
# PostgreSQL replication
aws rds describe-db-instances \
  --db-instance-identifier arada-replica \
  --query 'DBInstances[0].{Role:DBInstanceIdentifier,Status:DBInstanceStatus,ReplicationLag:StatusInfos}' \
  --region eu-west-1

# Redis replication
redis-cli -h <REDIS_PRIMARY> INFO replication | grep connected_slaves

redis-cli -h <REDIS_REPLICA> --region eu-west-1 INFO replication | grep master_sync_in_progress
```

### Test Failover (Simulated)

```bash
# Kill primary health check to trigger failover (simulated)
aws route53 update-health-check \
  --health-check-id <HEALTH_CHECK_PRIMARY_ID> \
  --alarm-identifier Name=test-alarm,Region=us-east-1 \
  --insufficient-data-health-status Unhealthy

# Verify DNS switch
nslookup api.arada.fun
# Should resolve to SECONDARY after ~30 seconds

# Restore health check
aws route53 update-health-check \
  --health-check-id <HEALTH_CHECK_PRIMARY_ID> \
  --health-check-type HTTPS
```

### Monitor Replication Lag

```bash
# CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name ReplicaLag \
  --dimensions Name=DBInstanceIdentifier,Value=arada-replica \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum \
  --region eu-west-1
```

## Step 6: Monitoring & Alerts

### CloudWatch Dashboards

Create a multi-region dashboard:

```bash
aws cloudwatch put-dashboard \
  --dashboard-name arada-multi-region \
  --dashboard-body file://cloudwatch-dashboard.json
```

### SNS Alerts

Configure SNS for failover alerts:

```bash
# Create SNS topic
aws sns create-topic --name arada-alerts

# Subscribe email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:arada-alerts \
  --protocol email \
  --notification-endpoint ops@arada.fun

# Create CloudWatch alarm for health check failure
aws cloudwatch put-metric-alarm \
  --alarm-name arada-primary-health-check-failed \
  --alarm-description "Primary region health check failed" \
  --metric-name HealthCheckStatus \
  --namespace AWS/Route53 \
  --statistic Minimum \
  --period 60 \
  --threshold 1 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:arada-alerts
```

## Step 7: Disaster Recovery Plan

### Practice Failover (Monthly)

```bash
#!/bin/bash
# runbook-test-failover.sh

echo "⚠️  Testing failover to secondary region..."

# 1. Simulate primary failure
echo "1. Simulating primary region failure..."
aws ec2 modify-network-interface-attribute \
  --network-interface-id eni-xxx \
  --no-source-dest-check \
  --region us-east-1

# 2. Monitor DNS change
echo "2. Monitoring DNS propagation..."
for i in {1..60}; do
  if nslookup api.arada.fun 8.8.8.8 | grep -q eu-west-1; then
    echo "✓ DNS switched to secondary region"
    break
  fi
  sleep 1
done

# 3. Verify secondary is responding
echo "3. Verifying secondary region..."
if curl -f https://api.arada.fun/system/health; then
  echo "✓ Secondary region is responsive"
else
  echo "✗ Secondary region not responding!"
  exit 1
fi

# 4. Verify data consistency
echo "4. Checking data consistency..."
PRIMARY_COUNT=$(psql -h primary.rds.amazonaws.com -U arada -d arada -t -c "SELECT COUNT(*) FROM content.normalized_items;")
SECONDARY_COUNT=$(psql -h secondary.rds.amazonaws.com -U arada -d arada -t -c "SELECT COUNT(*) FROM content.normalized_items;")

if [ "$PRIMARY_COUNT" = "$SECONDARY_COUNT" ]; then
  echo "✓ Data is consistent between regions"
else
  echo "⚠️  Data mismatch: Primary=$PRIMARY_COUNT, Secondary=$SECONDARY_COUNT"
fi

# 5. Restore primary
echo "5. Restoring primary region..."
aws ec2 modify-network-interface-attribute \
  --network-interface-id eni-xxx \
  --source-dest-check \
  --region us-east-1

echo "✅ Failover test complete"
```

### Real Failover (Emergency Only)

```bash
#!/bin/bash
# runbook-emergency-failover.sh

echo "🔴 EMERGENCY FAILOVER - PRIMARY REGION IS DOWN"
echo "Time: $(date)"
echo

# Step 1: Promote replica to primary
echo "Step 1: Promoting replica to primary..."
aws rds promote-read-replica \
  --db-instance-identifier arada-replica \
  --region eu-west-1 \
  --backup-retention-period 7

# Wait for promotion
echo "Waiting for promotion (5-10 min)..."
aws rds wait db-instance-available \
  --db-instance-identifier arada-replica \
  --region eu-west-1

echo "✓ Replica promoted to primary"

# Step 2: Update DNS to point to secondary
echo "Step 2: Updating DNS..."
aws route53 change-resource-record-sets \
  --hosted-zone-id Z123ABC \
  --change-batch file://failover-change-batch.json

echo "✓ DNS updated to secondary region"

# Step 3: Verify secondary can serve traffic
echo "Step 3: Verifying secondary can serve all traffic..."
curl -f https://api.arada.fun/system/health || exit 1

echo "✅ FAILOVER COMPLETE"
echo "All traffic now served from EU-WEST-1"
echo
echo "Next steps:"
echo "  1. Investigate US-EAST-1 failure"
echo "  2. Once repaired, run: bash runbook-failback.sh"
```

## Step 8: Cleanup (Optional)

To destroy all multi-region infrastructure:

```bash
# Review what will be deleted
terraform plan -destroy

# Delete all resources
terraform destroy

# Delete Terraform state
aws s3 rm s3://arada-terraform-state/ --recursive

# Delete DynamoDB table
aws dynamodb delete-table --table-name terraform-lock
```

⚠️ **Warning**: This is destructive and cannot be undone. Only do this if you're completely decommissioning.

## Cost Optimization Tips

### 1. Right-size secondary region
```hcl
# Secondary region can use smaller instances
api_instance_class_secondary = "t3.large"      # vs t3.xlarge on primary
api_min_size_secondary       = 1               # vs 2 on primary
api_max_size_secondary       = 3               # vs 10 on primary
```

### 2. Use on-demand secondary backup
For non-critical workloads, create secondary region on-demand:
```hcl
# Schedule secondary to spin up during business hours only
# Use EventBridge to start/stop secondary resources
```

### 3. Reduce backup retention
```hcl
# Shorter retention for dev/staging
rds_backup_retention_days = 7  # vs 30 for prod
```

## Troubleshooting

### Health checks not passing

```bash
# Check health check status
aws route53 get-health-check-status \
  --health-check-id <HEALTH_CHECK_ID>

# Verify ALB is responding
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:...

# Check EC2 security groups
aws ec2 describe-security-groups \
  --group-ids sg-xxx
```

### Replication lag too high

```bash
# Check network connectivity
ping <RDS_REPLICA_ENDPOINT>

# Check RDS parameter groups
aws rds describe-db-parameter-groups

# Increase RDS instance size
aws rds modify-db-instance \
  --db-instance-identifier arada-replica \
  --db-instance-class db.r6i.xlarge
```

### DNS not switching

```bash
# Check Route53 record
aws route53 list-resource-record-sets \
  --hosted-zone-id Z123ABC \
  --query 'ResourceRecordSets[?Name==`api.arada.fun.`]'

# Force TTL refresh
nslookup -type=A api.arada.fun 8.8.8.8

# Clear local DNS cache (macOS)
sudo dscacheutil -flushcache
```

## References

- [AWS RDS Multi-Region Failover](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html)
- [Route53 Health Checks](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-types.html)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Multi-Region Architecture Guide](MULTI_REGION.md)

---

**Need help?** Check [MULTI_REGION.md](MULTI_REGION.md) for detailed architecture and failover procedures.
