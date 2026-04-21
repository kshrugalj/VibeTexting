---
name: code-doctor
description: Autonomous code review, security auditing, and issue fixing. Use this skill when you need to scan the codebase for potential bugs, security vulnerabilities, or architectural issues, automatically resolve them where possible, and provide a detailed summary of all actions taken.
---

# Code Doctor

## Overview
This skill provides a fully autonomous workflow for identifying, fixing, and summarizing code-related issues. It prioritizes security, performance, and maintainability, ensuring that changes align with industry-standard Software Engineering (SWE) principles.

## Core Workflow

### 1. Diagnostic Scan
Perform a comprehensive scan of the target files or directory to identify potential issues.
- **Security Check:** Scan for hardcoded secrets, insecure API usage, and input validation vulnerabilities (see `references/security-principles.md`).
- **Logic & Bug Analysis:** Identify logical flaws, edge cases, and potential runtime errors.
- **Architectural Review:** Ensure code follows established project patterns and SOLID principles.

### 2. Autonomous Fixing
Once issues are identified, proceed with surgical, automated fixes.
- **Safe Refactoring:** Apply fixes that resolve the identified issue without introducing regressions.
- **Pattern Alignment:** Ensure that any new or modified code matches the project's existing style and structure.
- **Validation:** After applying a fix, run any available project-specific tests to confirm the change is successful.

### 3. Verification
Manually verify the success of the autonomous fixes through targeted analysis or by executing specific test cases.

### 4. Summary Generation
Provide a clear, concise report of the session, detailing:
- **Identified Issues:** What was found and its severity.
- **Applied Fixes:** What was changed and why.
- **Security Impact:** How security was improved.
- **Pending Tasks:** Any issues that require manual intervention.

## Resources

### references/security-principles.md
A detailed reference guide covering core SWE security principles, including secret detection, input sanitization, and secure communication patterns.

## Example Scenario

### Scenario: Fixing an insecure API endpoint
1. User: "Review and fix the security issues in `api/auth.py` and summarize the results."
2. Diagnostic: Load `references/security-principles.md` and identify a hardcoded secret and a missing input validation step.
3. Fix: Replace the hardcoded secret with an environment variable lookup and add validation logic.
4. Validate: Run `pytest api/test_auth.py` to ensure the endpoint still functions correctly.
5. Summary: Provide a report detailing the secret removal, the added validation, and the test results.
