# ============================================================================
# VPC Module - Network foundation for the EKS cluster
# ============================================================================
#
# This module creates the entire network that all other AWS resources live in.
#
# ARCHITECTURE:
#   VPC (10.0.0.0/16)
#   ├── Public Subnet AZ-a  (10.0.0.0/24)  - ALB, NAT Gateway, internet-facing
#   ├── Public Subnet AZ-b  (10.0.1.0/24)  - ALB (multi-AZ requirement)
#   ├── Private Subnet AZ-a (10.0.10.0/24) - EKS nodes, RDS, Redis
#   └── Private Subnet AZ-b (10.0.11.0/24) - EKS nodes, RDS (multi-AZ subnet group)
#
# WHY PUBLIC + PRIVATE?
#   - Public subnets have a route to the Internet Gateway (direct internet access)
#   - Private subnets route through the NAT Gateway (outbound-only internet access)
#   - EKS nodes, RDS, and Redis go in PRIVATE subnets so they're not directly
#     reachable from the internet. Only the ALB (load balancer) is in public subnets.
#
# WHY 2 AVAILABILITY ZONES?
#   - EKS requires subnets in at least 2 AZs for high availability
#   - RDS subnet groups require at least 2 AZs
#   - We use 2 (not 3) to keep costs down - 3 is standard for production
# ============================================================================

# Dynamically look up the available AZs in the region (e.g. eu-west-1a, eu-west-1b)
# This avoids hardcoding AZ names which differ between regions
data "aws_availability_zones" "available" {
  state = "available"
}

# =============================================================================
# VPC - The top-level isolated network
# =============================================================================
# CIDR 10.0.0.0/16 gives us 65,536 IP addresses - more than enough.
# DNS hostnames + DNS support must be enabled for EKS to work properly
# (pods need to resolve internal service names).

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true # Required by EKS - assigns DNS names to EC2 instances
  enable_dns_support   = true # Required by EKS - enables DNS resolution within the VPC

  tags = merge(var.tags, {
    Name = "${var.project_name}-vpc"
  })
}

# =============================================================================
# Public Subnets - Where the ALB and NAT Gateway live
# =============================================================================
# These subnets have direct internet access via the Internet Gateway.
# The ALB (Application Load Balancer) sits here and routes external traffic
# to NGINX in the private subnets.
#
# TAGS:
#   - "kubernetes.io/role/elb" = "1"
#     Tells the AWS Load Balancer Controller to place internet-facing ALBs here
#   - "kubernetes.io/cluster/{name}" = "shared"
#     Tells EKS this subnet is available for the cluster to use
#
# cidrsubnet(var.vpc_cidr, 8, 0) = 10.0.0.0/24 (256 IPs)
# cidrsubnet(var.vpc_cidr, 8, 1) = 10.0.1.0/24 (256 IPs)

resource "aws_subnet" "public" {
  count = 2 # One per AZ - we use 2 AZs

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index) # 10.0.0.0/24, 10.0.1.0/24
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true # Instances in public subnets get a public IP automatically

  tags = merge(var.tags, {
    Name                                        = "${var.project_name}-public-${count.index + 1}"
    "kubernetes.io/role/elb"                    = "1"      # ALB subnet tag
    "kubernetes.io/cluster/${var.cluster_name}" = "shared" # EKS subnet tag
  })
}

# =============================================================================
# Private Subnets - Where EKS nodes, RDS, and Redis live
# =============================================================================
# These subnets have NO direct internet access. Outbound traffic goes through
# the NAT Gateway (so pods can pull Docker images, etc.) but nothing from the
# internet can reach these subnets directly.
#
# TAGS:
#   - "kubernetes.io/role/internal-elb" = "1"
#     Tells the AWS Load Balancer Controller to place internal ALBs here
#     (for service-to-service communication within the cluster)
#
# cidrsubnet(var.vpc_cidr, 8, 10) = 10.0.10.0/24 (256 IPs)
# cidrsubnet(var.vpc_cidr, 8, 11) = 10.0.11.0/24 (256 IPs)
# We skip indices 2-9 to leave a gap between public and private subnets

resource "aws_subnet" "private" {
  count = 2 # One per AZ

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10) # 10.0.10.0/24, 10.0.11.0/24
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = merge(var.tags, {
    Name                                        = "${var.project_name}-private-${count.index + 1}"
    "kubernetes.io/role/internal-elb"           = "1"      # Internal ALB subnet tag
    "kubernetes.io/cluster/${var.cluster_name}" = "shared" # EKS subnet tag
  })
}

# =============================================================================
# Internet Gateway - Gives public subnets direct internet access
# =============================================================================
# Without this, nothing in the VPC can reach the internet.
# Only public subnets route through the IGW (see route tables below).

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-igw"
  })
}

# =============================================================================
# NAT Gateway - Gives private subnets OUTBOUND-ONLY internet access
# =============================================================================
# EKS nodes need outbound internet to:
#   - Pull container images from Docker Hub
#   - Communicate with the EKS API server
#   - Download CoreDNS / kube-proxy addons
#
# The NAT Gateway sits in a PUBLIC subnet and has an Elastic IP (static public IP).
# Private subnet traffic → NAT Gateway → Internet Gateway → Internet
# Internet → CANNOT reach private subnets (one-way only)
#
# We use a SINGLE NAT gateway to save costs (~$32/month per gateway).
# In production you'd have one per AZ for HA, but for a college project one is fine.

resource "aws_eip" "nat" {
  domain = "vpc" # Elastic IP allocated in the VPC domain

  tags = merge(var.tags, {
    Name = "${var.project_name}-nat-eip"
  })
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id          # Attach the Elastic IP
  subnet_id     = aws_subnet.public[0].id # NAT GW must be in a PUBLIC subnet

  tags = merge(var.tags, {
    Name = "${var.project_name}-nat"
  })

  depends_on = [aws_internet_gateway.main] # IGW must exist first
}

# =============================================================================
# Route Tables - Control where network traffic goes
# =============================================================================
#
# PUBLIC route table:  0.0.0.0/0 → Internet Gateway (direct internet)
# PRIVATE route table: 0.0.0.0/0 → NAT Gateway (outbound only via NAT)
#
# Each subnet is associated with exactly one route table.

# Public route table - all traffic to the internet goes via the IGW
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"                  # "All traffic not destined for the VPC..."
    gateway_id = aws_internet_gateway.main.id # "...goes to the Internet Gateway"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-public-rt"
  })
}

# Private route table - all traffic to the internet goes via the NAT Gateway
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"             # "All traffic not destined for the VPC..."
    nat_gateway_id = aws_nat_gateway.main.id # "...goes through the NAT Gateway"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-private-rt"
  })
}

# Associate each public subnet with the public route table
resource "aws_route_table_association" "public" {
  count = 2

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Associate each private subnet with the private route table
resource "aws_route_table_association" "private" {
  count = 2

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
