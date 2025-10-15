#!/bin/bash
# Daily verification script for ATO remediation work

set -e

echo "🔍 Running daily verification checks..."
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

# Check 1: Run all tests
echo "=========================================="
echo "1. Running test suite..."
echo "=========================================="
if python -m pytest tests/ -v --tb=short --maxfail=3 -x; then
    echo -e "${GREEN}✅ All tests passed${NC}"
else
    echo -e "${RED}❌ Tests failed${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check 2: Run linting
echo ""
echo "=========================================="
echo "2. Running linting..."
echo "=========================================="
if make lint; then
    echo -e "${GREEN}✅ Linting passed${NC}"
else
    echo -e "${RED}❌ Linting failed${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check 3: Verify no legacy code
echo ""
echo "=========================================="
echo "3. Checking for legacy code..."
echo "=========================================="
if ./scripts/verify-no-legacy-code.sh; then
    echo -e "${GREEN}✅ No legacy code found${NC}"
else
    echo -e "${RED}❌ Legacy code verification failed${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check 4: Verify secure mode is documented
echo ""
echo "=========================================="
echo "4. Checking documentation..."
echo "=========================================="
if grep -q "ELSPETH_SECURE_MODE" docs/security/*.md 2>/dev/null || \
   grep -q "ELSPETH_SECURE_MODE" docs/deployment/*.md 2>/dev/null; then
    echo -e "${GREEN}✅ Secure mode documented${NC}"
else
    echo -e "${YELLOW}⚠ WARNING: Secure mode not documented${NC}"
fi

# Check 5: Verify security test suite exists
echo ""
echo "=========================================="
echo "5. Checking security tests..."
echo "=========================================="
if [ -d "tests/security" ] && [ -f "tests/security/test_security_hardening.py" ]; then
    echo -e "${GREEN}✅ Security test suite exists${NC}"
else
    echo -e "${YELLOW}⚠ WARNING: Security test suite incomplete${NC}"
fi

# Check 6: Test coverage check (if coverage installed)
echo ""
echo "=========================================="
echo "6. Checking test coverage..."
echo "=========================================="
if command -v coverage &> /dev/null; then
    if python -m pytest tests/ --cov=src/elspeth --cov-report=term-missing --cov-fail-under=80 -q; then
        echo -e "${GREEN}✅ Coverage ≥ 80%${NC}"
    else
        echo -e "${YELLOW}⚠ WARNING: Coverage < 80%${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Coverage not installed, skipping${NC}"
fi

# Summary
echo ""
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ Daily verification PASSED${NC}"
    echo ""
    echo "All checks completed successfully!"
    exit 0
else
    echo -e "${RED}❌ Daily verification FAILED with ${ERRORS} errors${NC}"
    echo ""
    echo "Please fix the errors above before proceeding."
    exit 1
fi
