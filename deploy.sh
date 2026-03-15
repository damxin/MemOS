#!/bin/bash
# MemOS Deployment Script with pgvector + 1panel-network
# Usage: ./deploy.sh [up|down|logs|restart|status]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if 1panel-network exists, create if not
check_network() {
    if ! docker network inspect 1panel-network &>/dev/null; then
        echo -e "${YELLOW}Creating 1panel-network...${NC}"
        docker network create 1panel-network
        echo -e "${GREEN}1panel-network created successfully${NC}"
    else
        echo -e "${BLUE}1panel-network already exists${NC}"
    fi
}

# Deploy services
up() {
    echo -e "${GREEN}Starting MemOS services...${NC}"
    check_network
    
    # Check if .env exists
    if [[ ! -f ".env" ]]; then
        echo -e "${YELLOW}Warning: .env not found, copying from .env.docker${NC}"
        cp .env.docker .env
    fi
    
    # Start services
    docker-compose up -d
    
    echo -e "${GREEN}MemOS services started successfully!${NC}"
    echo ""
    echo -e "${BLUE}Services:${NC}"
    echo "  - PostgreSQL: localhost:24432"
    echo "  - Redis: localhost:6379"
    echo "  - MemOS API: http://localhost:8080"
    echo ""
    echo -e "${YELLOW}Check logs: ./deploy.sh logs${NC}"
}

# Stop services
down() {
    echo -e "${RED}Stopping MemOS services...${NC}"
    docker-compose down
    echo -e "${GREEN}MemOS services stopped${NC}"
}

# Show logs
logs() {
    docker-compose logs -f --tail=100
}

# Restart services
restart() {
    echo -e "${YELLOW}Restarting MemOS services...${NC}"
    down
    up
}

# Show status
status() {
    echo -e "${BLUE}MemOS Services Status:${NC}"
    echo ""
    docker-compose ps
    echo ""
    echo -e "${BLUE}1panel-network:${NC}"
    docker network inspect 1panel-network --format='{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null || echo "  No containers connected"
}

# Main
main() {
    case "${1:-up}" in
        up|start)
            up
            ;;
        down|stop)
            down
            ;;
        logs)
            logs
            ;;
        restart)
            restart
            ;;
        status)
            status
            ;;
        *)
            echo "Usage: $0 [up|down|logs|restart|status]"
            echo ""
            echo "Commands:"
            echo "  up      - Start MemOS services (default)"
            echo "  down    - Stop MemOS services"
            echo "  logs    - Show service logs"
            echo "  restart - Restart all services"
            echo "  status  - Show service status"
            exit 1
            ;;
    esac
}

main "$@"
