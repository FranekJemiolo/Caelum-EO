#!/usr/bin/env bash
# ==============================================================================
# Project Caelum-EO: Bare-Metal Production Deployment Script
# 100% On-Premises, Fully Local, Air-Gapped GEOINT Infrastructure
# Repository: github.com/FranekJemiolo/Caelum-EO
# ==============================================================================

set -euo pipefail

# ANSI Color Codes
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "=================================================================="
echo "    PROJECT CAELUM-EO // BARE-METAL PRODUCTION DEPLOYMENT         "
echo "    Autonomous Space-to-Surface Defense Intelligence Platform     "
echo "=================================================================="
echo -e "${NC}"

# 1. Validate Docker & Docker Compose
echo -e "${CYAN}[1/5] Checking Docker runtime prerequisites...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[ERROR] Docker is not installed. Please install Docker Engine: https://docs.docker.com/engine/install/${NC}"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}[ERROR] Docker Compose v2 is required. Please install the Docker Compose plugin.${NC}"
    exit 1
fi
echo -e "${GREEN}[OK] Docker and Docker Compose v2 detected.${NC}"

# 2. Validate NVIDIA Drivers & Container Toolkit
echo -e "${CYAN}[2/5] Validating GPU hardware acceleration (NVIDIA Container Toolkit)...${NC}"
HAS_GPU=false
if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || true)
    if [ -n "$GPU_INFO" ]; then
        echo -e "${GREEN}[OK] NVIDIA GPU Detected: ${GPU_INFO}${NC}"
        HAS_GPU=true
    fi
fi

if [ "$HAS_GPU" = false ]; then
    echo -e "${YELLOW}[WARNING] nvidia-smi not detected or no NVIDIA GPU found.${NC}"
    echo -e "${YELLOW}Hardware acceleration requires the NVIDIA Container Toolkit:${NC}"
    echo -e "${YELLOW}  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html${NC}"
    echo -e "${YELLOW}Continuing in CPU fallback mode for local evaluation...${NC}"
fi

# 3. Initialize Secure Environment File (.env.prod)
ENV_FILE=".env.prod"
echo -e "${CYAN}[3/5] Configuring production security credentials in ${ENV_FILE}...${NC}"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "Generating high-entropy cryptographic secrets..."

    # Generate random passwords using openssl or python fallback
    if command -v openssl &> /dev/null; then
        POSTGRES_PASS=$(openssl rand -hex 20)
        MINIO_PASS=$(openssl rand -hex 20)
        JWT_SECRET=$(openssl rand -hex 32)
    else
        POSTGRES_PASS=$(python3 -c "import secrets; print(secrets.token_hex(20))")
        MINIO_PASS=$(python3 -c "import secrets; print(secrets.token_hex(20))")
        JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    fi

    cat <<EOF > "$ENV_FILE"
# Project Caelum-EO: Production Environment Secrets
# Auto-generated on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# RESTRICTED: Ensure this file is never committed to public version control.

ENVIRONMENT=production

# Spatial Database Secrets
POSTGRES_DB=caelum_geoint
POSTGRES_USER=caelum_user
POSTGRES_PASSWORD=${POSTGRES_PASS}

# Object Storage Secrets
MINIO_ROOT_USER=caelum_minio_admin
MINIO_ROOT_PASSWORD=${MINIO_PASS}

# Security & Authentication
JWT_SECRET_KEY=${JWT_SECRET}

# Observability & Alerting
PRIORITY_ALERT_THRESHOLD=0.85
WEBHOOK_URLS=

# Storage Retention (Days)
RAW_DATA_RETENTION_DAYS=7

# Exposed Host Ports
FRONTEND_PORT=3000
API_PORT=8000
EOF

    chmod 600 "$ENV_FILE"
    echo -e "${GREEN}[OK] Generated secure ${ENV_FILE} with restricted permissions (chmod 600).${NC}"
else
    echo -e "${GREEN}[OK] Existing ${ENV_FILE} detected. Preserving credentials.${NC}"
fi

# 4. Prepare Host Storage Directories
echo -e "${CYAN}[4/5] Initializing local storage directories...${NC}"
mkdir -p data/raw data/chips data/interim weights
echo -e "${GREEN}[OK] Local directories initialized: data/raw, data/chips, data/interim, weights.${NC}"

# 5. Boot Production Composition
echo -e "${CYAN}[5/5] Launching bare-metal production Docker stack...${NC}"
if [ "$HAS_GPU" = true ]; then
    docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" up -d --build
else
    # In non-GPU environments, strip GPU reservations or pass --profile
    docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" up -d --build || {
        echo -e "${YELLOW}Falling back without GPU device reservation...${NC}"
        docker compose -f docker-compose.yml --env-file "$ENV_FILE" up -d --build
    }
fi

echo ""
echo -e "${GREEN}${BOLD}==================================================================${NC}"
echo -e "${GREEN}${BOLD}    CAELUM-EO PRODUCTION STACK SUCCESSFULLY DEPLOYED             ${NC}"
echo -e "${GREEN}${BOLD}==================================================================${NC}"
echo ""
echo -e "  ${BOLD}Analyst WebGL Portal:${NC}      http://localhost:3000"
echo -e "  ${BOLD}FastAPI Backend & Docs:${NC}    http://localhost:8000/docs"
echo -e "  ${BOLD}Martin Vector Tile Server:${NC} http://localhost:3001"
echo -e "  ${BOLD}TiTiler COG Raster Server:${NC} http://localhost:8001"
echo ""
echo -e "${BOLD}Default Operator Credentials (RBAC):${NC}"
echo -e "  • ${CYAN}Admin:${NC}    admin / caelum_admin_2026!"
echo -e "  • ${CYAN}Analyst:${NC}  analyst_viper / caelum_analyst_2026!"
echo -e "  • ${CYAN}Viewer:${NC}   viewer_01 / caelum_viewer_2026!"
echo ""
echo -e "To tail container logs:     ${CYAN}docker compose -f docker-compose.prod.yml logs -f${NC}"
echo -e "To stop production stack:   ${CYAN}docker compose -f docker-compose.prod.yml down${NC}"
echo ""
