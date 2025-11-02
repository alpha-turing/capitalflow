# Branch Protection Setup Guide

This guide will help you configure GitHub branch protection rules to enforce test passing before merging to `main`.

## Why Branch Protection?

Branch protection ensures:
- ✅ All tests must pass before merging
- ✅ Code reviews are required
- ✅ Prevents accidental force pushes
- ✅ Maintains code quality standards

## Setup Instructions

### 1. Navigate to Branch Protection Settings

1. Go to your repository on GitHub: `https://github.com/alpha-turing/capitalflow`
2. Click on **Settings** tab
3. Click on **Branches** in the left sidebar
4. Under "Branch protection rules", click **Add rule** or **Add branch protection rule**

### 2. Configure Protection for `main` Branch

**Branch name pattern**: `main`

#### Required Settings (Recommended)

Check the following options:

##### ✅ Require a pull request before merging
- **Require approvals**: 1 (or more for production)
- ☐ Dismiss stale pull request approvals when new commits are pushed (optional but recommended)
- ☐ Require review from Code Owners (if you have CODEOWNERS file)

##### ✅ Require status checks to pass before merging
- **Require branches to be up to date before merging**: ✅ (Recommended)
- **Status checks that are required**:
  - Add: `test (3.11)` - Tests with Python 3.11
  - Add: `test (3.12)` - Tests with Python 3.12
  
  > **Note**: These status checks will appear after your first CI run. You may need to save the rule, push a commit, then edit to add them.

##### ✅ Require conversation resolution before merging
- Ensures all PR comments are addressed

##### ✅ Do not allow bypassing the above settings
- Prevents admins from bypassing rules (recommended for strict enforcement)

#### Additional Security Settings (Optional but Recommended)

##### ✅ Require linear history
- Prevents merge commits, enforces rebase or squash

##### ✅ Include administrators
- Branch protection applies to repository admins too

##### ☐ Allow force pushes
- **Leave UNCHECKED** to prevent force pushes to main

##### ☐ Allow deletions
- **Leave UNCHECKED** to prevent accidental branch deletion

### 3. Save the Rule

Click **Create** or **Save changes** at the bottom of the page.

## What Happens After Setup?

### ✅ Protection Enabled

Once configured, you will see:

1. **Direct pushes to main blocked**
   ```bash
   $ git push origin main
   remote: error: GH006: Protected branch update failed for refs/heads/main.
   ```

2. **Pull requests required**
   - All changes must go through a PR
   - Tests must pass (green checkmark)
   - Reviews must be approved

3. **Status checks visible on PRs**
   - You'll see test results directly in the PR
   - Merge button disabled until all checks pass

### Example Workflow

```bash
# Create a feature branch
git checkout -b feature/my-awesome-feature

# Make changes and commit
git add .
git commit -m "Add awesome feature"

# Push to GitHub
git push origin feature/my-awesome-feature

# On GitHub:
# 1. Create Pull Request
# 2. Wait for CI tests to pass ✅
# 3. Request review (if required)
# 4. Merge only when all checks pass
```

## Verification

To verify protection is active:

1. Go to: `https://github.com/alpha-turing/capitalflow/settings/branches`
2. You should see your `main` branch listed under "Branch protection rules"
3. Try pushing directly to main - it should be blocked

## Troubleshooting

### Status checks not appearing?

1. Push a commit to trigger the CI workflow
2. Wait for the workflow to complete
3. Go back to branch protection settings
4. The status checks should now appear in the dropdown

### Can't find status checks to add?

Make sure:
- The workflow file exists: `.github/workflows/tests.yml`
- At least one workflow run has completed
- The job name matches (check the workflow file)

### Emergency: Need to bypass protection?

If you're an admin and absolutely need to bypass:
1. Temporarily disable the rule
2. Make the critical fix
3. **Re-enable protection immediately**

**Better approach**: Use a hotfix PR that can be merged quickly once tests pass.

## Current Configuration Status

- [x] GitHub Actions workflow created (`.github/workflows/tests.yml`)
- [ ] Branch protection rule configured on GitHub
- [ ] Status checks added to protection rule
- [ ] Team notified about new workflow

## Next Steps

1. **Configure the branch protection** following steps above
2. Test it by creating a sample PR
3. Verify tests run automatically
4. Verify merge is blocked if tests fail
5. Update team documentation

## Reference Links

- [GitHub Docs: Branch Protection Rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub Actions: Status Checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks)

---

**Last Updated**: November 2, 2025  
**Repository**: alpha-turing/capitalflow
