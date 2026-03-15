#!/bin/bash
# Check and create 1panel-network for MemOS

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}MemOS Network Checker${NC}"
echo "======================"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker is installed${NC}"

# Check if 1panel-network exists
echo ""
echo -e "${BLUE}Checking 1panel-network...${NC}"

if docker network inspect 1panel-network &>/dev/null; then
    echo -e "${GREEN}✓ 1panel-network exists${NC}"
    
    # Show network details
    echo ""
    echo -e "${BLUE}Network details:${NC}"
    docker network inspect 1panel-network --format='  Driver: {{.Driver}}
  Scope: {{.Scope}}
  Subnet: {{range .IPAM.Config}}{{.Subnet}}{{end}}
  Gateway: {{range .IPAM.Config}}{{.Gateway}}{{end}}'
    
    # List connected containers
    CONTAINERS=$(docker network inspect 1panel-network --format='{{range .Containers}}{{.Name}} {{end}}')
    if [ -n "$CONTAINERS" ]; then
        echo ""
        echo -e "${BLUE}Connected containers:${NC}"
        for container in $CONTAINERS; do
            echo "  - $container"
        done
    else
        echo ""
        echo -e "${YELLOW}No containers connected yet${NC}"
    fi
else
    echo -e "${YELLOW}✗ 1panel-network does not exist${NC}"
    echo ""
    read -p "Create 1panel-network now? (y/n) " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Creating 1panel-network...${NC}"
        
        # Try to create with specific subnet (common 1Panel subnet)
        if docker network create \
            --driver bridge \
            --subnet 172.18.0.0/16 \
            --gateway 172.18.0.1 \
            1panel-network 2>/dev/null; then
            echo -e "${GREEN}✓ 1panel-network created with subnet 172.18.0.0/16${NC}"
        else
            # Try without specific subnet
            if docker network create 1panel-network 2>/dev/null; then
                echo -e "${GREEN}✓ 1panel-network created (default subnet)${NC}"
            else
                echo -e "${RED}✗ Failed to create 1panel-network${NC}"
                exit 1
            fi
        fi
    else
        echo -e "${YELLOW}Network creation cancelled${NC}"
        echo ""
        echo "To create manually, run:"
        echo "  docker network create 1panel-network"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}✓ Network check complete${NC}"
echo ""
echo "Next steps:"
echo "  1. Run: ./deploy.sh up"
echo "  2. Or: docker-compose up -d"
