#!/bin/bash
# Script to install git hooks for all developers

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
HOOKS_TEMPLATE_DIR="$REPO_ROOT/scripts/git-hooks"

echo "🔧 Installing git hooks..."

# Create hooks directory if it doesn't exist
mkdir -p "$HOOKS_DIR"

# Copy pre-commit hook
cat > "$HOOKS_DIR/pre-commit" << 'EOF'
#!/bin/bash
# Pre-commit hook to run tests before allowing commits

echo "🧪 Running pre-commit tests..."

# Run tests
python -m pytest tests/ -q --tb=short

# Capture exit code
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ Tests failed! Commit rejected."
    echo "   Fix the failing tests before committing."
    echo "   Run 'python -m pytest tests/ -v' to see details."
    echo ""
    echo "   To bypass this check (not recommended):"
    echo "   git commit --no-verify"
    exit 1
fi

echo "✅ All tests passed! Proceeding with commit."
exit 0
EOF

# Copy pre-push hook
cat > "$HOOKS_DIR/pre-push" << 'EOF'
#!/bin/bash
# Pre-push hook to run tests before allowing push to main

CURRENT_BRANCH=$(git symbolic-ref --short HEAD)

# Only run for pushes to main or develop
if [[ "$CURRENT_BRANCH" == "main" ]] || [[ "$CURRENT_BRANCH" == "develop" ]]; then
    echo "🔒 Pushing to protected branch: $CURRENT_BRANCH"
    echo "🧪 Running full test suite..."
    
    # Run full test suite with coverage
    python -m pytest tests/ -v
    
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -ne 0 ]; then
        echo ""
        echo "❌ Tests failed! Push rejected."
        echo "   Cannot push to $CURRENT_BRANCH with failing tests."
        echo "   Fix the failing tests before pushing."
        echo ""
        echo "   To bypass this check (strongly not recommended):"
        echo "   git push --no-verify"
        exit 1
    fi
    
    echo "✅ All tests passed! Proceeding with push to $CURRENT_BRANCH."
fi

exit 0
EOF

# Make hooks executable
chmod +x "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-push"

echo "✅ Git hooks installed successfully!"
echo ""
echo "Installed hooks:"
echo "  - pre-commit: Runs tests before every commit"
echo "  - pre-push: Runs full test suite before pushing to main/develop"
echo ""
echo "To bypass hooks (not recommended): git commit --no-verify"
