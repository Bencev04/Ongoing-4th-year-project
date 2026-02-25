#!/bin/bash
# ==============================================================================
# Test All Services - Comprehensive Test Runner
# ==============================================================================
# This script runs tests for all services in the microservices architecture.
# It tracks pass/fail status for each service and provides a summary at the end.
#
# Usage:
#   ./scripts/test-all.sh           # Run all tests in Docker
#   ./scripts/test-all.sh --local   # Run tests locally (requires venv setup)
#   ./scripts/test-all.sh --service frontend  # Run tests for specific service
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more test suites failed
# ==============================================================================

set -e  # Exit on error (disabled later for test runs)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
USE_DOCKER=true
SPECIFIC_SERVICE=""
VERBOSE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            USE_DOCKER=false
            shift
            ;;
        --service)
            SPECIFIC_SERVICE="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --local           Run tests locally instead of in Docker"
            echo "  --service NAME    Run tests for specific service only"
            echo "  --verbose, -v     Show detailed test output"
            echo "  --help, -h        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Service definitions
# Format: "service_name:test_path:docker_container"
SERVICES=(
    "frontend:services/frontend:crm_frontend"
    "auth-service:services/auth-service:crm_auth_service"
    "user-bl-service:services/user-bl-service:crm_user_bl_service"
    "user-db-access-service:services/user-db-access-service:crm_user_db_access_service"
    "customer-bl-service:services/customer-bl-service:crm_customer_bl_service"
    "customer-db-access-service:services/customer-db-access-service:crm_customer_db_access_service"
    "job-bl-service:services/job-bl-service:crm_job_bl_service"
    "job-db-access-service:services/job-db-access-service:crm_job_db_access_service"
)

# Track results
declare -A results
declare -A test_counts
total_services=0
passed_services=0
failed_services=0
skipped_services=0

# Function to print section header
print_header() {
    echo ""
    echo -e "${BLUE}================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}================================================================${NC}"
    echo ""
}

# Function to print service header
print_service_header() {
    echo ""
    echo -e "${YELLOW}┌────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│  Testing: $1${NC}"
    echo -e "${YELLOW}└────────────────────────────────────────────────────────────┘${NC}"
}

# Function to run tests for a service
run_service_tests() {
    local service_name=$1
    local service_path=$2
    local container_name=$3
    
    # Check if we should skip this service
    if [[ -n "$SPECIFIC_SERVICE" && "$service_name" != "$SPECIFIC_SERVICE" ]]; then
        return 0
    fi
    
    print_service_header "$service_name"
    ((total_services++))
    
    # Determine test directory based on service structure
    local test_dir=""
    if [[ -d "$service_path/app/tests" ]]; then
        test_dir="app/tests"
    elif [[ -d "$service_path/tests" ]]; then
        test_dir="tests"
    else
        echo -e "${YELLOW}⚠ No tests directory found for $service_name${NC}"
        results[$service_name]="SKIP"
        ((skipped_services++))
        return 0
    fi
    
    # Run tests based on mode
    local exit_code=0
    local output=""
    
    if $USE_DOCKER; then
        echo "Running tests in Docker container: $container_name"
        
        # Check if container is running
        if ! docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
            echo -e "${RED}✗ Container $container_name is not running${NC}"
            echo "  Run: docker-compose up -d $service_name"
            results[$service_name]="FAIL"
            ((failed_services++))
            return 1
        fi
        
        # Run pytest in container
        if $VERBOSE; then
            docker-compose exec -T $service_name pytest $test_dir -v --tb=short
            exit_code=$?
        else
            output=$(docker-compose exec -T $service_name pytest $test_dir -v --tb=short 2>&1)
            exit_code=$?
            
            # Extract summary line
            summary=$(echo "$output" | grep -E "passed|failed|error" | tail -1 || echo "No summary available")
            echo "$summary"
        fi
    else
        echo "Running tests locally"
        cd "$service_path"
        
        if $VERBOSE; then
            pytest $test_dir -v --tb=short
            exit_code=$?
        else
            output=$(pytest $test_dir -v --tb=short 2>&1)
            exit_code=$?
            
            summary=$(echo "$output" | grep -E "passed|failed|error" | tail -1 || echo "No summary available")
            echo "$summary"
        fi
        
        cd - > /dev/null
    fi
    
    # Record results
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ $service_name tests PASSED${NC}"
        results[$service_name]="PASS"
        ((passed_services++))
    else
        echo -e "${RED}✗ $service_name tests FAILED${NC}"
        results[$service_name]="FAIL"
        ((failed_services++))
        
        if ! $VERBOSE; then
            echo ""
            echo "Failed test output:"
            echo "$output" | grep -A 10 "FAILED\|ERROR" || echo "$output"
        fi
    fi
}

# Main execution
print_header "CRM Calendar Platform - Test Suite Runner"

if $USE_DOCKER; then
    echo "Mode: Docker"
    echo "Checking Docker services..."
    
    # Check if docker-compose is available
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}Error: docker-compose not found${NC}"
        exit 1
    fi
    
    # Check if any containers are running
    if [ -z "$(docker-compose ps -q)" ]; then
        echo -e "${YELLOW}Warning: No Docker containers are running${NC}"
        echo "Starting services..."
        docker-compose up -d
        echo "Waiting for services to be healthy..."
        sleep 10
    fi
else
    echo "Mode: Local"
    echo "Note: Ensure you have activated the appropriate virtual environment for each service"
fi

if [[ -n "$SPECIFIC_SERVICE" ]]; then
    echo "Running tests for: $SPECIFIC_SERVICE"
else
    echo "Running tests for all services"
fi

echo ""

# Run tests for each service
for service_def in "${SERVICES[@]}"; do
    IFS=':' read -r name path container <<< "$service_def"
    run_service_tests "$name" "$path" "$container" || true  # Continue even if tests fail
done

# Print summary
print_header "Test Results Summary"

echo -e "${BLUE}Service Results:${NC}"
echo ""

# Print results table
printf "%-30s %s\n" "Service" "Status"
printf "%-30s %s\n" "-------" "------"

for service_def in "${SERVICES[@]}"; do
    IFS=':' read -r name path container <<< "$service_def"
    
    # Skip if we filtered by specific service
    if [[ -n "$SPECIFIC_SERVICE" && "$name" != "$SPECIFIC_SERVICE" ]]; then
        continue
    fi
    
    status="${results[$name]:-SKIP}"
    
    case $status in
        PASS)
            printf "%-30s ${GREEN}✓ PASSED${NC}\n" "$name"
            ;;
        FAIL)
            printf "%-30s ${RED}✗ FAILED${NC}\n" "$name"
            ;;
        SKIP)
            printf "%-30s ${YELLOW}⊘ SKIPPED${NC}\n" "$name"
            ;;
    esac
done

echo ""
echo -e "${BLUE}Summary:${NC}"
echo "  Total services tested: $total_services"
echo -e "  ${GREEN}Passed: $passed_services${NC}"
echo -e "  ${RED}Failed: $failed_services${NC}"
echo -e "  ${YELLOW}Skipped: $skipped_services${NC}"

echo ""

# Exit with appropriate code
if [ $failed_services -gt 0 ]; then
    echo -e "${RED}❌ Some tests failed${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
fi
