# Test Guardrails Setup - Quick Reference

## Overview

This project has **three layers of protection** to prevent broken code from reaching production:

```
Layer 1: Local Git Hooks    → Catches issues before commit/push
Layer 2: GitHub Actions CI  → Validates all PRs and pushes
Layer 3: Branch Protection  → Enforces rules on GitHub
```

## Layer 1: Local Git Hooks ⚡

**Installed locally on your machine**

### Installation
```bash
# One-time setup (run after cloning)
./scripts/install-hooks.sh
```

### What it does
- **pre-commit hook**: Runs quick tests before each `git commit`
- **pre-push hook**: Runs full test suite before `git push` to main/develop

### Example
```bash
$ git commit -m "Add new feature"
🧪 Running pre-commit tests...
✅ All tests passed! Proceeding with commit.

$ git push origin main
🔒 Pushing to protected branch: main
🧪 Running full test suite...
✅ All tests passed! Proceeding with push to main.
```

### Bypass (Emergency Only)
```bash
# Not recommended - bypasses local checks
git commit --no-verify
git push --no-verify
```

## Layer 2: GitHub Actions CI 🤖

**Runs automatically on GitHub**

### When it runs
- Every push to `main` or `develop` branches
- Every pull request to `main` or `develop`
- Manual trigger via Actions tab

### What it does
```yaml
✓ Runs tests on Python 3.11 and 3.12
✓ Generates test coverage report
✓ Runs linting checks
✓ Reports status to PR
```

### View Results
- [GitHub Actions Tab](https://github.com/alpha-turing/capitalflow/actions)
- Status shown in PR as ✅ or ❌

### Configuration
File: `.github/workflows/tests.yml`

## Layer 3: Branch Protection 🛡️

**Enforced by GitHub**

### Setup Required (One-time)
Follow the guide: `.github/BRANCH_PROTECTION.md`

**Quick steps:**
1. Go to: Settings → Branches → Add rule
2. Branch name pattern: `main`
3. Check: "Require status checks to pass before merging"
4. Add status checks: `test (3.11)` and `test (3.12)`
5. Check: "Require pull request reviews before merging"
6. Save rule

### What it enforces
- ✅ All CI tests must pass
- ✅ Code review required
- ✅ No direct pushes to main
- ✅ No force pushes
- ✅ Branch must be up to date

### After Setup
```bash
# This will be blocked:
$ git push origin main
remote: error: GH006: Protected branch update failed

# Must use PR workflow:
$ git push origin feature/my-feature
# Then create PR on GitHub
```

## Recommended Workflow

### For New Features
```bash
# 1. Create feature branch
git checkout -b feature/awesome-feature

# 2. Make changes
# ... edit files ...

# 3. Test locally (optional but recommended)
pytest

# 4. Commit (hooks run automatically)
git add .
git commit -m "Add awesome feature"
# → pre-commit hook runs tests

# 5. Push
git push origin feature/awesome-feature
# → pre-push hook runs if pushing to main

# 6. Create Pull Request on GitHub
# → GitHub Actions CI runs automatically

# 7. Wait for:
#    ✅ All tests pass
#    ✅ Code review approval

# 8. Merge on GitHub
# → Protected branch ensures everything is validated
```

### For Hotfixes
```bash
# Same process, but use hotfix branch
git checkout -b hotfix/critical-bug
# ... fix the bug ...
git commit -m "Fix critical bug"
# → tests run
git push origin hotfix/critical-bug
# Create PR, get quick review, merge when tests pass
```

## Testing the Setup

### Test Local Hooks
```bash
# 1. Make a change that breaks tests
echo "broken code" >> app/main.py

# 2. Try to commit
git commit -m "Test"
# Should see: ❌ Tests failed! Commit rejected.

# 3. Revert
git checkout app/main.py
```

### Test GitHub Actions
```bash
# 1. Create a test branch
git checkout -b test-ci

# 2. Make a small change
echo "# CI test" >> README.md

# 3. Push
git commit -m "Test CI"
git push origin test-ci

# 4. Check Actions tab on GitHub
# Should see workflow running
```

### Test Branch Protection
```bash
# 1. After configuring branch protection, try:
git checkout main
echo "test" >> test.txt
git commit -m "Test protection"
git push origin main

# Should see:
# remote: error: GH006: Protected branch update failed
```

## Troubleshooting

### Hooks not running?
```bash
# Re-install hooks
./scripts/install-hooks.sh

# Verify they exist
ls -la .git/hooks/pre-*

# Should see:
# -rwxr-xr-x  pre-commit
# -rwxr-xr-x  pre-push
```

### CI not running on GitHub?
- Check `.github/workflows/tests.yml` exists
- View Actions tab for errors
- Verify GitHub Actions is enabled in repo settings

### Can't merge PR even though tests pass?
- Check branch protection rules are configured
- Ensure PR is up to date with main
- Check if review approval is required

### Emergency: Need to bypass everything?
**Not recommended, but if absolutely necessary:**
```bash
# Local bypass
git commit --no-verify
git push --no-verify

# GitHub bypass (admin only)
# 1. Temporarily disable branch protection
# 2. Push directly
# 3. RE-ENABLE protection immediately
```

## Maintenance

### Update hooks for team
```bash
# When hooks change, team members should re-run:
./scripts/install-hooks.sh
```

### Monitor CI usage
- GitHub Actions free tier: 2,000 minutes/month
- Each test run: ~2-3 minutes
- Monitor at: Settings → Billing

### Review test coverage
```bash
# Generate coverage report
pytest --cov=app --cov-report=html

# View in browser
open htmlcov/index.html
```

## Benefits

✅ **Catch bugs early** - Before they reach production  
✅ **Faster debugging** - Identify issues immediately  
✅ **Team confidence** - Know main is always stable  
✅ **Better code reviews** - Focus on logic, not test failures  
✅ **Audit trail** - All changes tracked and validated  
✅ **Professional workflow** - Industry best practices  

## Status

Current setup status for this repository:

- [x] GitHub Actions workflow created
- [x] Local git hooks created
- [x] Installation script available
- [x] Documentation complete
- [ ] **Branch protection rules need to be configured** (See `.github/BRANCH_PROTECTION.md`)
- [ ] Team notified about new workflow

## Next Steps

1. ✅ Install local hooks: `./scripts/install-hooks.sh`
2. ⚠️ Configure branch protection on GitHub (See `.github/BRANCH_PROTECTION.md`)
3. ✅ Test the workflow with a sample PR
4. 📢 Notify team about new process

---

**Questions?** Check the detailed guides:
- Branch Protection: `.github/BRANCH_PROTECTION.md`
- Testing Guide: `docs/testing-guide.md`
- CI Workflow: `.github/workflows/tests.yml`

**Last Updated**: November 2, 2025
