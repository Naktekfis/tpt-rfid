#!/bin/bash
################################################################################
# TPT-RFID Database Import Script
# Import data from SQL dump to local PostgreSQL database
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}  TPT-RFID Database Import to Local${NC}"
echo -e "${BLUE}===============================================${NC}"
echo ""

# Check if dump file provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: No dump file specified${NC}"
    echo ""
    echo -e "${YELLOW}Usage:${NC}"
    echo "  $0 <dump_file.sql>"
    echo ""
    echo -e "${YELLOW}Example:${NC}"
    echo "  $0 backups/firebase_export_20260220_120000.sql"
    echo ""
    echo -e "${YELLOW}Available backup files:${NC}"
    ls -lh backups/*.sql 2>/dev/null || echo "  No backup files found"
    exit 1
fi

DUMP_FILE="$1"

# Check if dump file exists
if [ ! -f "$DUMP_FILE" ]; then
    echo -e "${RED}Error: Dump file not found: $DUMP_FILE${NC}"
    exit 1
fi

# Get database credentials from .env
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | grep DATABASE_URL | xargs)
fi

# Extract connection details from DATABASE_URL
# Format: postgresql://user:password@host:port/database
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}Error: DATABASE_URL not found in .env${NC}"
    exit 1
fi

# Extract components
DB_USER=$(echo "$DATABASE_URL" | sed -n 's|postgresql://\([^:]*\):.*|\1|p')
DB_PASS=$(echo "$DATABASE_URL" | sed -n 's|postgresql://[^:]*:\([^@]*\)@.*|\1|p')
DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^/]*\)$|\1|p')

echo -e "${BLUE}Target Database Details:${NC}"
echo "  User: $DB_USER"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo "  Database: $DB_NAME"
echo ""
echo -e "${BLUE}Import File: ${NC}$DUMP_FILE"

# Get file size and preview
FILE_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo -e "${BLUE}File Size: ${NC}$FILE_SIZE"
echo ""

# Count expected records
STUDENT_COUNT=$(grep -c "INSERT INTO public.students" "$DUMP_FILE" || echo "0")
TOOL_COUNT=$(grep -c "INSERT INTO public.tools" "$DUMP_FILE" || echo "0")
TRANSACTION_COUNT=$(grep -c "INSERT INTO public.transactions" "$DUMP_FILE" || echo "0")

echo -e "${BLUE}Expected Data to Import:${NC}"
echo "  Students: ${GREEN}$STUDENT_COUNT${NC}"
echo "  Tools: ${GREEN}$TOOL_COUNT${NC}"
echo "  Transactions: ${GREEN}$TRANSACTION_COUNT${NC}"
echo ""

# Warning
echo -e "${YELLOW}⚠️  WARNING: This will REPLACE all existing data!${NC}"
echo -e "${YELLOW}   Current data will be deleted and replaced with imported data.${NC}"
echo ""

# Create backup of current local data
BACKUP_FILE="backups/local_backup_before_import_$(date +%Y%m%d_%H%M%S).sql"
echo -e "${BLUE}Creating backup of current local data...${NC}"

export PGPASSWORD="$DB_PASS"
if pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-acl \
    > "$BACKUP_FILE" 2>/dev/null; then
    echo -e "${GREEN}✓ Backup created: ${NC}$BACKUP_FILE"
else
    echo -e "${YELLOW}⚠  Could not create backup (database might be empty)${NC}"
fi

echo ""
echo -e "${YELLOW}Proceed with import? (y/N): ${NC}"
read -r CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo -e "${RED}Import cancelled${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Starting import...${NC}"
echo ""

# Import using psql
export PGPASSWORD="$DB_PASS"

if psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
    -f "$DUMP_FILE" \
    -v ON_ERROR_STOP=1 \
    --quiet; then
    
    echo ""
    echo -e "${GREEN}✓ Import successful!${NC}"
    echo ""
    
    # Verify imported data
    echo -e "${BLUE}Verifying imported data...${NC}"
    
    # Get actual counts from database
    ACTUAL_STUDENTS=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
        -t -c "SELECT COUNT(*) FROM students;" 2>/dev/null | tr -d ' ')
    ACTUAL_TOOLS=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
        -t -c "SELECT COUNT(*) FROM tools;" 2>/dev/null | tr -d ' ')
    ACTUAL_TRANSACTIONS=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
        -t -c "SELECT COUNT(*) FROM transactions;" 2>/dev/null | tr -d ' ')
    
    echo ""
    echo -e "${BLUE}Imported Record Counts:${NC}"
    echo "  Students: ${GREEN}$ACTUAL_STUDENTS${NC}"
    echo "  Tools: ${GREEN}$ACTUAL_TOOLS${NC}"
    echo "  Transactions: ${GREEN}$ACTUAL_TRANSACTIONS${NC}"
    
    # Sample data
    echo ""
    echo -e "${BLUE}Sample Student Data:${NC}"
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
        -c "SELECT id, name, nim, email FROM students LIMIT 3;" 2>/dev/null
    
    echo ""
    echo -e "${BLUE}Sample Tool Data:${NC}"
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
        -c "SELECT id, name, category, status FROM tools LIMIT 3;" 2>/dev/null
    
    echo ""
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${GREEN}  Import completed successfully!${NC}"
    echo -e "${GREEN}===============================================${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo -e "  1. Verify data: ${BLUE}python scripts/verify_database.py${NC}"
    echo -e "  2. Test application: ${BLUE}python app.py${NC}"
    echo ""
    
else
    echo ""
    echo -e "${RED}✗ Import failed!${NC}"
    echo ""
    echo -e "${YELLOW}Attempting to restore from backup...${NC}"
    
    if [ -f "$BACKUP_FILE" ]; then
        psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
            < "$BACKUP_FILE" 2>/dev/null
        echo -e "${GREEN}✓ Backup restored${NC}"
    else
        echo -e "${RED}✗ No backup file found${NC}"
    fi
    
    echo ""
    echo -e "${RED}Please check:${NC}"
    echo "  1. SQL dump file is valid"
    echo "  2. PostgreSQL connection works"
    echo "  3. Database user has sufficient privileges"
    echo "  4. No syntax errors in dump file"
    exit 1
fi

# Clean up PGPASSWORD
unset PGPASSWORD
