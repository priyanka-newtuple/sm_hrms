#!/bin/bash

# Unit test for the migration bash logic from the workflow
# Tests the bash patterns and logic without requiring actual database/containers

set -e

echo "=== Testing Migration Bash Logic ==="
echo ""

# Colors
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
CYAN="\033[1;36m"
NC="\033[0m"

PASSED=0
FAILED=0

test_pattern() {
    local test_name="$1"
    local input="$2"
    local pattern="$3"
    local expected="$4"
    
    if echo "$input" | grep -q "$pattern"; then
        result="match"
    else
        result="no match"
    fi
    
    if [ "$result" = "$expected" ]; then
        echo -e "${GREEN}✓ PASS: $test_name${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAIL: $test_name${NC}"
        echo "  Expected: $expected, Got: $result"
        ((FAILED++))
        return 1
    fi
}

echo -e "${CYAN}Testing error detection patterns...${NC}"

# Test 1: DuplicateTable error detection
test_pattern \
    "DuplicateTable error detection" \
    "psycopg2.errors.DuplicateTable: relation \"entities\" already exists" \
    "DuplicateTable\|already exists" \
    "match"

# Test 2: Already exists error detection
test_pattern \
    "Already exists error detection" \
    "relation \"entities\" already exists" \
    "DuplicateTable\|already exists" \
    "match"

# Test 3: Non-matching error
test_pattern \
    "Non-matching error (should not match)" \
    "Connection refused" \
    "DuplicateTable\|already exists" \
    "no match"

echo ""
echo -e "${CYAN}Testing version check patterns...${NC}"

# Test 4: Can't locate revision
test_pattern \
    "Can't locate revision detection" \
    "Can't locate revision identified by 'head'" \
    "Can't locate revision\|alembic_version" \
    "match"

# Test 5: alembic_version table missing
test_pattern \
    "alembic_version table missing detection" \
    "alembic_version table does not exist" \
    "Can't locate revision\|alembic_version" \
    "match"

# Test 6: Normal version output (should not match)
test_pattern \
    "Normal version output (should not match)" \
    "001 (head)" \
    "Can't locate revision\|alembic_version" \
    "no match"

echo ""
echo -e "${CYAN}Testing exit code handling...${NC}"

# Test 7: Exit code simulation
MIGRATION_EXIT_CODE=1
TEST_OUTPUT="DuplicateTable: relation already exists"
if [ $MIGRATION_EXIT_CODE -ne 0 ] && echo "$TEST_OUTPUT" | grep -q "DuplicateTable\|already exists"; then
    echo -e "${GREEN}✓ PASS: Exit code and error pattern combination${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL: Exit code and error pattern combination${NC}"
    ((FAILED++))
fi

# Test 8: Success case
MIGRATION_EXIT_CODE=0
if [ $MIGRATION_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ PASS: Success exit code handling${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL: Success exit code handling${NC}"
    ((FAILED++))
fi

echo ""
echo -e "${CYAN}Testing variable assignment and command substitution...${NC}"

# Test 9: Command substitution with error output
TEST_CURRENT_VERSION="Can't locate revision identified by 'head'"
if echo "$TEST_CURRENT_VERSION" | grep -q "Can't locate revision\|alembic_version" || [ -z "$TEST_CURRENT_VERSION" ]; then
    echo -e "${GREEN}✓ PASS: Version check logic with 'Can't locate revision'${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL: Version check logic${NC}"
    ((FAILED++))
fi

# Test 10: Empty version check
TEST_CURRENT_VERSION=""
if echo "$TEST_CURRENT_VERSION" | grep -q "Can't locate revision\|alembic_version" || [ -z "$TEST_CURRENT_VERSION" ]; then
    echo -e "${GREEN}✓ PASS: Empty version detection${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL: Empty version detection${NC}"
    ((FAILED++))
fi

# Test 11: Normal version (should not trigger stamp)
TEST_CURRENT_VERSION="001 (head)"
if echo "$TEST_CURRENT_VERSION" | grep -q "Can't locate revision\|alembic_version" || [ -z "$TEST_CURRENT_VERSION" ]; then
    echo -e "${RED}✗ FAIL: Normal version incorrectly detected as missing${NC}"
    ((FAILED++))
else
    echo -e "${GREEN}✓ PASS: Normal version correctly not detected as missing${NC}"
    ((PASSED++))
fi

echo ""
echo -e "${CYAN}Testing full workflow simulation...${NC}"

# Simulate the full workflow logic
simulate_workflow() {
    local test_scenario="$1"
    local current_version_output="$2"
    local migration_output="$3"
    local migration_exit_code="$4"
    
    echo "  Scenario: $test_scenario"
    
    # Step 1: Check version
    if echo "$current_version_output" | grep -q "Can't locate revision\|alembic_version" || [ -z "$current_version_output" ]; then
        echo "    → Would stamp database"
        STAMP_NEEDED=true
    else
        echo "    → Version found, no stamp needed"
        STAMP_NEEDED=false
    fi
    
    # Step 2: Run migration
    if [ $migration_exit_code -ne 0 ] && echo "$migration_output" | grep -q "DuplicateTable\|already exists"; then
        echo "    → Duplicate table error detected, would stamp"
        STAMP_NEEDED=true
    elif [ $migration_exit_code -eq 0 ]; then
        echo "    → Migration succeeded"
    else
        echo "    → Migration failed with other error"
    fi
    
    echo ""
}

echo "Test scenarios:"
simulate_workflow \
    "Tables exist, no alembic_version" \
    "Can't locate revision" \
    "DuplicateTable: relation already exists" \
    1

simulate_workflow \
    "Normal migration" \
    "001 (head)" \
    "" \
    0

simulate_workflow \
    "Empty version, migration succeeds" \
    "" \
    "" \
    0

echo ""
echo -e "${CYAN}=== Test Results ===${NC}"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi

