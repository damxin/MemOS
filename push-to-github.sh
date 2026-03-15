#!/bin/bash
# Push MemOS to GitHub
# Usage: ./push-to-github.sh

set -e

cd "$(dirname "$0")"

echo "========================================"
echo "  Push MemOS to GitHub"
echo "========================================"
echo ""

# Check current status
echo "📋 Git Status:"
git status --short
echo ""

# Show commits to push
echo "📤 Commits to push:"
git log --oneline origin/main..main 2>/dev/null || echo "  (checking...)"
echo ""

# Push options
echo "🔐 Choose authentication method:"
echo ""
echo "1) HTTPS + Personal Access Token (Recommended)"
echo "   - Go to: https://github.com/settings/tokens/new"
echo "   - Select 'repo' scope"
echo "   - Generate and copy token"
echo ""
echo "2) SSH Key (if already configured)"
echo ""
echo "3) Show manual commands only"
echo ""

read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "📎 HTTPS + PAT selected"
        echo ""
        read -p "Enter GitHub username: " username
        read -sp "Enter Personal Access Token: " token
        echo ""
        echo ""
        echo "🚀 Pushing to GitHub..."
        
        if git push "https://${username}:${token}@github.com/damxin/MemOS.git" main; then
            echo ""
            echo "✅ SUCCESS! Code pushed to GitHub"
            echo ""
            echo "🔗 Repository: https://github.com/damxin/MemOS"
            echo ""
        else
            echo ""
            echo "❌ Push failed"
            exit 1
        fi
        ;;
    
    2)
        echo ""
        echo "🔑 SSH selected"
        echo ""
        
        # Configure SSH remote
        git remote set-url origin git@github.com:damxin/MemOS.git
        
        echo "🚀 Pushing to GitHub via SSH..."
        if git push origin main; then
            echo ""
            echo "✅ SUCCESS! Code pushed to GitHub"
        else
            echo ""
            echo "❌ Push failed"
            echo ""
            echo "💡 Make sure your SSH key is added to GitHub:"
            echo "   https://github.com/settings/keys"
            exit 1
        fi
        ;;
    
    3)
        echo ""
        echo "📋 Manual push commands:"
        echo ""
        echo "Option 1 - HTTPS with PAT:"
        echo "  git push https://USERNAME:TOKEN@github.com/damxin/MemOS.git main"
        echo ""
        echo "Option 2 - SSH:"
        echo "  git remote set-url origin git@github.com:damxin/MemOS.git"
        echo "  git push origin main"
        echo ""
        echo "Option 3 - GitHub CLI:"
        echo "  gh auth login"
        echo "  git push origin main"
        ;;
    
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "========================================"
echo "Done!"
