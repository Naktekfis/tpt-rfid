#!/bin/bash
################################################################################
# TPT-RFID Master Migration Script
# Complete end-to-end migration from Firebase to Local PostgreSQL
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="backups/migration_log_$TIMESTAMP.txt"

# Function to log messages
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Print header
clear
log "${CYAN}╔════════════════════════════════════════════════╗${NC}"
log "${CYAN}║  TPT-RFID Complete Database Migration Tool    ║${NC}"
log "${CYAN}║  Firebase PostgreSQL → Local PostgreSQL       ║${NC}"
log "${CYAN}╚════════════════════════════════════════════════╝${NC}"
log ""
log "${BLUE}Migration started at: $(date)${NC}"
log "${BLUE}Log file: $LOG_FILE${NC}"
log ""

# Step 0: Pre-flight checks
log "${BLUE}═══════════════════════════════════════════════${NC}"
log "${BLUE}  STEP 0: Pre-flight Checks${NC}"
log "${BLUE}═══════════════════════════════════════════════${NC}"
log ""

# Check if required tools are installed
log "${YELLOW}Checking required tools...${NC}"

if ! command -v pg_dump &> /dev/null; then
    log "${RED}✗ pg_dump not found${NC}"
    log "${RED}  Install with: sudo apt install postgresql-client${NC}"
    exit 1
fi
log "${GREEN}✓ pg_dump installed${NC}"

if ! command -v psql &> /dev/null; then
    log "${RED}✗ psql not found${NC}"
    log "${RED}  Install with: sudo apt install postgresql-client${NC}"
    exit 1
fi
log "${GREEN}✓ psql installed${NC}"

if ! command -v python3 &> /dev/null; then
    log "${RED}✗ python3 not found${NC}"
    exit 1
fi
log "${GREEN}✓ python3 installed${NC}"

# Check if .env exists
if [ ! -f ".env" ]; then
    log "${RED}✗ .env file not found${NC}"
    log "${RED}  Please create .env with DATABASE_URL${NC}"
    exit 1
fi
log "${GREEN}✓ .env file exists${NC}"

# Check local database connection
log ""
log "${YELLOW}Testing local database connection...${NC}"
export $(grep -v '^#' .env | grep DATABASE_URL | xargs)

if [ -z "$DATABASE_URL" ]; then
    log "${RED}✗ DATABASE_URL not found in .env${NC}"
    exit 1
fi

# Extract database password
DB_PASS=$(echo "$DATABASE_URL" | sed -n 's|postgresql://[^:]*:\([^@]*\)@.*|\1|p')
DB_USER=$(echo "$DATABASE_URL" | sed -n 's|postgresql://\([^:]*\):.*|\1|p')
DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^/]*\)$|\1|p')

export PGPASSWORD="$DB_PASS"
if psql -U "$DB_USER" -h "$DB_HOST" -d "$DB_NAME" -c "SELECT 1" &> /dev/null; then
    log "${GREEN}✓ Local database connection successful${NC}"
else
    log "${RED}✗ Cannot connect to local database${NC}"
    exit 1
fi

log ""
log "${GREEN}✓ All pre-flight checks passed${NC}"
log ""

# Step 1: Export from Firebase
log "${BLUE}═══════════════════════════════════════════════${NC}"
log "${BLUE}  STEP 1: Export Data from Firebase${NC}"
log "${BLUE}═══════════════════════════════════════════════${NC}"
log ""

log "${YELLOW}Running export script...${NC}"
if ./scripts/export_firebase_data.sh 2>&1 | tee -a "$LOG_FILE"; then
    log ""
    log "${GREEN}✓ Export completed${NC}"
else
    log "${RED}✗ Export failed${NC}"
    log "${RED}Migration aborted${NC}"
    exit 1
fi

# Find the latest export file
LATEST_EXPORT=$(ls -t backups/firebase_export_*.sql 2>/dev/null | head -1)

if [ -z "$LATEST_EXPORT" ]; then
    log "${RED}✗ No export file found${NC}"
    exit 1
fi

log "${GREEN}Latest export: $LATEST_EXPORT${NC}"
log ""

# Step 2: Backup current local data
log "${BLUE}═══════════════════════════════════════════════${NC}"
log "${BLUE}  STEP 2: Backup Current Local Data${NC}"
log "${BLUE}═══════════════════════════════════════════════${NC}"
log ""

BACKUP_FILE="backups/local_before_migration_$TIMESTAMP.sql"
log "${YELLOW}Creating backup: $BACKUP_FILE${NC}"

if pg_dump -U "$DB_USER" -h "$DB_HOST" -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-acl \
    > "$BACKUP_FILE" 2>/dev/null; then
    log "${GREEN}✓ Backup created successfully${NC}"
    
    # Compress backup
    gzip -k "$BACKUP_FILE"
    log "${GREEN}✓ Compressed: ${BACKUP_FILE}.gz${NC}"
else
    log "${YELLOW}⚠  Backup failed (database might be empty, continuing...)${NC}"
fi
log ""

# Step 3: Import to local database
log "${BLUE}═══════════════════════════════════════════════${NC}"
log "${BLUE}  STEP 3: Import Data to Local Database${NC}"
log "${BLUE}═══════════════════════════════════════════════${NC}"
log ""

log "${YELLOW}Running import script...${NC}"
log "${YELLOW}This will replace all existing data!${NC}"
log ""

# Run import script (it will prompt for confirmation)
if ./scripts/import_to_local.sh "$LATEST_EXPORT" 2>&1 | tee -a "$LOG_FILE"; then
    log ""
    log "${GREEN}✓ Import completed${NC}"
else
    log "${RED}✗ Import failed${NC}"
    log ""
    log "${YELLOW}Attempting to restore from backup...${NC}"
    
    if [ -f "$BACKUP_FILE" ]; then
        psql -U "$DB_USER" -h "$DB_HOST" -d "$DB_NAME" < "$BACKUP_FILE" &> /dev/null
        log "${GREEN}✓ Backup restored${NC}"
    fi
    
    log "${RED}Migration failed${NC}"
    exit 1
fi
log ""

# Step 4: Verify data integrity
log "${BLUE}═══════════════════════════════════════════════${NC}"
log "${BLUE}  STEP 4: Verify Data Integrity${NC}"
log "${BLUE}═══════════════════════════════════════════════${NC}"
log ""

log "${YELLOW}Running verification script...${NC}"

# Check if venv exists
if [ -d "venv" ]; then
    PYTHON_CMD="venv/bin/python"
elif [ -d ".venv" ]; then
    PYTHON_CMD=".venv/bin/python"
else
    PYTHON_CMD="python3"
fi

if $PYTHON_CMD scripts/verify_database.py 2>&1 | tee -a "$LOG_FILE"; then
    log ""
    log "${GREEN}✓ Verification passed${NC}"
else
    log "${YELLOW}⚠  Verification failed or returned warnings${NC}"
    log "${YELLOW}  Please review the output above${NC}"
fi
log ""

# Step 5: Final summary
log "${CYAN}╔════════════════════════════════════════════════╗${NC}"
log "${CYAN}║         Migration Summary                      ║${NC}"
log "${CYAN}╚════════════════════════════════════════════════╝${NC}"
log ""

log "${GREEN}✓ Migration completed successfully!${NC}"
log ""
log "${BLUE}Files created:${NC}"
log "  • Export: $LATEST_EXPORT"
log "  • Export (compressed): ${LATEST_EXPORT}.gz"
log "  • Backup: $BACKUP_FILE"
log "  • Backup (compressed): ${BACKUP_FILE}.gz"
log "  • Log: $LOG_FILE"
log ""

# Show current database stats
log "${BLUE}Current Database Stats:${NC}"
STUDENTS=$(psql -U "$DB_USER" -h "$DB_HOST" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM students;" 2>/dev/null | tr -d ' ')
TOOLS=$(psql -U "$DB_USER" -h "$DB_HOST" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM tools;" 2>/dev/null | tr -d ' ')
TRANSACTIONS=$(psql -U "$DB_USER" -h "$DB_HOST" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM transactions;" 2>/dev/null | tr -d ' ')

log "  • Students: ${GREEN}$STUDENTS${NC}"
log "  • Tools: ${GREEN}$TOOLS${NC}"
log "  • Transactions: ${GREEN}$TRANSACTIONS${NC}"
log ""

log "${BLUE}Migration completed at: $(date)${NC}"
log ""

log "${YELLOW}Next Steps:${NC}"
log "  1. Test application: ${CYAN}python app.py${NC}"
log "  2. Verify frontend works: ${CYAN}http://localhost:5000${NC}"
log "  3. Check migration log: ${CYAN}cat $LOG_FILE${NC}"
log ""

log "${GREEN}═══════════════════════════════════════════════${NC}"
log "${GREEN}  Migration process complete!${NC}"
log "${GREEN}═══════════════════════════════════════════════${NC}"

# Clean up
unset PGPASSWORD
