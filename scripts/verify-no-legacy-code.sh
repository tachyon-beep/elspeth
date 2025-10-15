#!/bin/bash
# Verification script to ensure no legacy code references remain

set -e

echo "🔍 Verifying no legacy code references..."
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# Check 1: No old/ directory
echo "✓ Checking for old/ directory..."
if [ -d "old/" ]; then
    echo -e "${RED}✗ ERROR: old/ directory still exists${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}  ✓ old/ directory removed${NC}"
fi

# Check 2: No imports from old code
echo "✓ Checking for imports from old code..."
OLD_IMPORTS=$(grep -r "from old\." src/ tests/ 2>/dev/null || true)
if [ -n "$OLD_IMPORTS" ]; then
    echo -e "${RED}✗ ERROR: Found imports from old code:${NC}"
    echo "$OLD_IMPORTS"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}  ✓ No imports from old code${NC}"
fi

# Check 3: No references to old.* modules
echo "✓ Checking for old.* module references..."
OLD_REFS=$(grep -r "import old\." src/ tests/ 2>/dev/null || true)
if [ -n "$OLD_REFS" ]; then
    echo -e "${RED}✗ ERROR: Found references to old modules:${NC}"
    echo "$OLD_REFS"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}  ✓ No old module references${NC}"
fi

# Check 4: Check for 'dmp' namespace references (legacy)
echo "✓ Checking for legacy 'dmp' namespace..."
DMP_REFS=$(grep -r "from dmp\." src/ tests/ 2>/dev/null || true)
DMP_REFS2=$(grep -r "import dmp\." src/ tests/ 2>/dev/null || true)
if [ -n "$DMP_REFS" ] || [ -n "$DMP_REFS2" ]; then
    echo -e "${RED}✗ ERROR: Found references to legacy 'dmp' namespace${NC}"
    echo "$DMP_REFS"
    echo "$DMP_REFS2"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}  ✓ No legacy namespace references${NC}"
fi

# Check 5: .gitignore contains old/
echo "✓ Checking .gitignore..."
if grep -q "^old/" .gitignore; then
    echo -e "${GREEN}  ✓ old/ is in .gitignore${NC}"
else
    echo -e "${YELLOW}⚠ WARNING: old/ not in .gitignore${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 6: Look for TODO/FIXME comments about legacy code
echo "✓ Checking for legacy code TODOs..."
LEGACY_TODOS=$(grep -r "TODO.*legacy\|FIXME.*legacy\|TODO.*old/" src/ tests/ 2>/dev/null || true)
if [ -n "$LEGACY_TODOS" ]; then
    echo -e "${YELLOW}⚠ WARNING: Found TODO/FIXME comments about legacy code:${NC}"
    echo "$LEGACY_TODOS"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 7: Verify ADR exists documenting removal
echo "✓ Checking for ADR documenting removal..."
if [ ! -f "docs/architecture/decisions/003-remove-legacy-code.md" ]; then
    echo -e "${YELLOW}⚠ WARNING: ADR 003 (remove legacy code) not found${NC}"
    WARNINGS=$((WARNINGS + 1))
else
    echo -e "${GREEN}  ✓ ADR documenting removal exists${NC}"
fi

# Summary
echo ""
echo "=========================================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ PASSED: No legacy code found${NC}"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ PASSED WITH WARNINGS: ${WARNINGS} warnings${NC}"
    exit 0
else
    echo -e "${RED}❌ FAILED: ${ERRORS} errors, ${WARNINGS} warnings${NC}"
    exit 1
fi
