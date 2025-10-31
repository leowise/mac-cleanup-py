# Implementation Plan for mac-cleanup-py Security and Safety Improvements

## Overview

This plan outlines the implementation of recommendations from the security and safety review, prioritized by severity level. Each item includes specific steps, estimated effort, and success criteria.

## Priority 1: High Severity Issues

### 1.1 Enhance Destructive File Operations Safety

**Current Issue:** `rm -rf` commands on critical directories with potential for data loss.

**Implementation Steps:**

1. **Add Mandatory Confirmation Prompts**
   - Modify `Path._execute()` to always show confirmation unless `--force` is used
   - Add size estimation display before confirmation
   - Implement "Are you sure?" prompts with clear warnings about irreversibility

2. **Implement Safer Deletion Methods**
   - Replace direct `rm -rf` with `trash` command where possible
   - Add `--safe-delete` flag to use trash instead of permanent deletion
   - Create backup of deletion list before operations

3. **Add Operation Logging**
   - Create `mac_cleanup/logger.py` module
   - Log all deletion operations to `~/.mac_cleanup_py/deletion_log.txt`
   - Include timestamps, paths, and sizes

4. **Enhance Dry-Run Mode**
   - Improve dry-run output with better formatting
   - Add size calculations for all operations
   - Make dry-run the default behavior (require explicit confirmation to proceed)

**Estimated Effort:** 2-3 weeks
**Success Criteria:** All deletion operations require explicit user confirmation, operations are logged, safer deletion methods available.

### 1.2 Implement Backup Mechanisms

**Current Issue:** No recovery options for accidental deletions.

**Implementation Steps:**

1. **Add Pre-Operation Backup**
   - Create `mac_cleanup/backup.py` module
   - Implement tar-based backup of directories before deletion
   - Store backups in `~/.mac_cleanup_py/backups/` with timestamps

2. **Add Restore Functionality**
   - Add `--restore` command line option
   - Interactive restore menu for backed-up items
   - Validation to prevent restore conflicts

3. **Backup Retention Policy**
   - Automatic cleanup of old backups (keep last 10 operations)
   - User-configurable retention settings

**Estimated Effort:** 1-2 weeks
**Success Criteria:** Users can restore accidentally deleted files, backup process is transparent.

## Priority 2: Medium Severity Issues

### 2.1 Improve Command Execution Security

**Current Issue:** Shell command execution without proper safeguards.

**Implementation Steps:**

1. **Add Command Validation**
   - Create whitelist of allowed commands
   - Validate command outputs before execution
   - Add timeout mechanisms (30-second default)

2. **Enhance Error Handling**
   - Improve `cmd()` function with better error reporting
   - Add retry logic for transient failures
   - Log command execution results

3. **Replace Shell Execution Where Possible**
   - Use Python APIs instead of shell commands where available
   - For example, use `shutil` for file operations instead of `rm`

**Estimated Effort:** 1 week
**Success Criteria:** All commands have timeouts, better error handling, reduced shell usage.

### 2.2 Secure Custom Modules

**Current Issue:** Dynamic loading of user-provided code.

**Implementation Steps:**

1. **Add Module Validation**
   - Create `mac_cleanup/module_validator.py`
   - Validate module code for dangerous operations
   - Sandbox module execution

2. **Improve User Warnings**
   - Add prominent warnings when enabling custom modules
   - Require explicit acknowledgment of security risks
   - Document safe module development practices

3. **Code Review Framework**
   - Add optional code review step for custom modules
   - Static analysis of module code
   - AST-based validation

**Estimated Effort:** 2 weeks
**Success Criteria:** Custom modules are validated, users are warned about risks.

### 2.3 Strengthen Path Validation

**Current Issue:** Path expansion and validation could be more robust.

**Implementation Steps:**

1. **Implement Whitelist Approach**
   - Create comprehensive whitelist of allowed paths
   - Move from blacklist to whitelist validation
   - Add user-configurable allowed paths

2. **Add Size Limits**
   - Implement maximum deletion size limits
   - Warn on unusually large operations
   - Add `--no-size-limit` override flag

3. **Improve Path Resolution**
   - Better handling of symlinks and aliases
   - Validation of expanded paths
   - Cross-platform path handling

**Estimated Effort:** 1 week
**Success Criteria:** Only explicitly allowed paths can be deleted, size limits prevent massive operations.

## Priority 3: Low-Medium Severity Issues

### 3.1 Enhance Error Handling

**Current Issue:** Inconsistent error handling across the application.

**Implementation Steps:**

1. **Standardize Exception Handling**
   - Create custom exception classes in `mac_cleanup/errors.py`
   - Implement consistent error reporting
   - Add user-friendly error messages

2. **Add Rollback Mechanisms**
   - Implement transaction-like behavior for operations
   - Rollback partial operations on failure
   - State tracking for resumable operations

3. **Improve User Feedback**
   - Better progress indicators
   - Detailed error messages with suggestions
   - Recovery instructions

**Estimated Effort:** 1 week
**Success Criteria:** All errors are handled gracefully with clear user feedback.

## Priority 4: Low Severity Issues

### 4.1 Expand Testing Coverage

**Current Issue:** Limited testing of destructive operations.

**Implementation Steps:**

1. **Add Integration Tests**
   - Create isolated test environment for file operations
   - Test actual deletion scenarios (with safe fallbacks)
   - Add performance testing

2. **Improve Unit Test Coverage**
   - Target 90%+ code coverage
   - Add edge case testing for path validation
   - Test custom module loading

3. **Add CI/CD Testing**
   - Automated security scanning
   - Performance regression tests
   - Cross-platform testing

**Estimated Effort:** 2 weeks
**Success Criteria:** Comprehensive test suite covering all critical paths.

### 4.2 Implement Dependency Management

**Current Issue:** Third-party dependencies need monitoring.

**Implementation Steps:**

1. **Add Vulnerability Scanning**
   - Integrate `safety` or `pip-audit` in CI/CD
   - Regular dependency updates
   - Automated security alerts

2. **Dependency Pinning**
   - Pin all dependency versions
   - Regular security audits
   - Update documentation

**Estimated Effort:** 3-5 days
**Success Criteria:** Dependencies are monitored for vulnerabilities.

### 4.3 Improve User Experience

**Current Issue:** Interactive configuration can be cumbersome.

**Implementation Steps:**

1. **Add Non-Interactive Configuration**
   - Support configuration via config file
   - Environment variable support
   - Default configuration profiles

2. **Enhance CLI Interface**
   - Better help messages
   - Progress indicators for long operations
   - Color-coded output improvements

**Estimated Effort:** 1 week
**Success Criteria:** Tool can be used in automated environments.

### 4.4 Optimize Performance

**Current Issue:** Large operations lack progress indication.

**Implementation Steps:**

1. **Add Progress Tracking**
   - Real-time progress bars for deletions
   - Size estimation before operations
   - ETA calculations

2. **Implement Resumable Operations**
   - State persistence for interrupted operations
   - Resume capability
   - Checkpoint system

**Estimated Effort:** 1 week
**Success Criteria:** Users get clear feedback during long operations.

## Implementation Timeline

### Phase 1 (Weeks 1-4): Critical Safety Improvements

- High severity issues (1.1, 1.2)
- Basic error handling improvements

### Phase 2 (Weeks 5-8): Security Hardening

- Medium severity issues (2.1, 2.2, 2.3)
- Enhanced validation and security

### Phase 3 (Weeks 9-12): Quality and UX Improvements

- Low-medium severity issues (3.1)
- Low severity issues (4.1, 4.2, 4.3, 4.4)

## Testing and Validation

- **Unit Tests:** All new code must have >90% coverage
- **Integration Tests:** End-to-end testing of critical paths
- **Security Testing:** Regular vulnerability scans
- **User Acceptance:** Beta testing with real users

## Risk Mitigation

- **Rollback Plan:** Ability to revert changes if issues arise
- **Gradual Rollout:** Feature flags for new safety features
- **Documentation:** Updated user guides and security documentation
- **Communication:** Clear release notes about safety improvements

## Success Metrics

- Zero data loss incidents in testing
- All high-risk operations require explicit confirmation
- Comprehensive logging of all operations
- Improved user satisfaction scores
- Clean security audit results
