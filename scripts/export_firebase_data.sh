#!/bin/bash
################################################################################
# TPT-RFID Database Export Script
# Export data from Firebase PostgreSQL to local SQL dump file
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
EXPORT_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_FILE="$EXPORT_DIR/firebase_export_$TIMESTAMP.sql"

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}  TPT-RFID Database Export from Firebase${NC}"
echo -e "${BLUE}===============================================${NC}"
echo ""

# Create export directory if not exists
mkdir -p "$EXPORT_DIR"

# Prompt for Firebase connection string
echo -e "${YELLOW}Enter Firebase PostgreSQL connection string:${NC}"
echo -e "${YELLOW}Format: postgresql://user:password@host:port/database${NC}"
echo -e "${YELLOW}Example: postgresql://ahmad:pass123@35.240.xxx.xxx:5432/tpt_rfid${NC}"
echo -n "Connection string: "
read FIREBASE_DB_URL

# Validate input
if [ -z "$FIREBASE_DB_URL" ]; then
    echo -e "${RED}Error: Connection string cannot be empty${NC}"
    exit 1
fi

# Extract database name from connection string for logging
DB_NAME=$(echo "$FIREBASE_DB_URL" | sed -n 's|.*/\([^/]*\)$|\1|p')
echo ""
echo -e "${BLUE}Target Database: ${NC}$DB_NAME"
echo -e "${BLUE}Export File: ${NC}$EXPORT_FILE"
echo ""

# Confirm before proceeding
echo -e "${YELLOW}Proceed with export? (y/N): ${NC}"
read -r CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo -e "${RED}Export cancelled${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Starting export...${NC}"

# Export database using pg_dump
# Options:
#   --format=plain: Plain-text SQL script
#   --no-owner: Don't include ownership commands
#   --no-acl: Don't include access privileges
#   --clean: Include DROP commands before CREATE
#   --if-exists: Use IF EXISTS with DROP commands
#   --inserts: Use INSERT commands (more portable than COPY)

if pg_dump "$FIREBASE_DB_URL" \
    --format=plain \
    --no-owner \
    --no-acl \
    --clean \
    --if-exists \
    --inserts \
    --file="$EXPORT_FILE"; then
    
    echo -e "${GREEN}✓ Export successful!${NC}"
    echo ""
    
    # Get file size
    FILE_SIZE=$(du -h "$EXPORT_FILE" | cut -f1)
    echo -e "${GREEN}Export file created: ${NC}$EXPORT_FILE"
    echo -e "${GREEN}File size: ${NC}$FILE_SIZE"
    
    # Count records in export file
    STUDENT_COUNT=$(grep -c "INSERT INTO public.students" "$EXPORT_FILE" || echo "0")
    TOOL_COUNT=$(grep -c "INSERT INTO public.tools" "$EXPORT_FILE" || echo "0")
    TRANSACTION_COUNT=$(grep -c "INSERT INTO public.transactions" "$EXPORT_FILE" || echo "0")
    
    echo ""
    echo -e "${BLUE}Data Summary:${NC}"
    echo -e "  Students: ${GREEN}$STUDENT_COUNT${NC}"
    echo -e "  Tools: ${GREEN}$TOOL_COUNT${NC}"
    echo -e "  Transactions: ${GREEN}$TRANSACTION_COUNT${NC}"
    
    # Create compressed backup
    echo ""
    echo -e "${BLUE}Creating compressed backup...${NC}"
    gzip -k "$EXPORT_FILE"
    
    COMPRESSED_SIZE=$(du -h "${EXPORT_FILE}.gz" | cut -f1)
    echo -e "${GREEN}✓ Compressed backup created: ${NC}${EXPORT_FILE}.gz"
    echo -e "${GREEN}Compressed size: ${NC}$COMPRESSED_SIZE"
    
    echo ""
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${GREEN}  Export completed successfully!${NC}"
    echo -e "${GREEN}===============================================${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo -e "  1. Verify export file: ${BLUE}head -n 50 $EXPORT_FILE${NC}"
    echo -e "  2. Import to local: ${BLUE}./scripts/import_to_local.sh $EXPORT_FILE${NC}"
    echo ""
    
else
    echo -e "${RED}✗ Export failed!${NC}"
    echo -e "${RED}Please check:${NC}"
    echo "  1. Connection string is correct"
    echo "  2. Network connectivity to Firebase"
    echo "  3. PostgreSQL credentials are valid"
    echo "  4. pg_dump is installed: pg_dump --version"
    exit 1
fi
