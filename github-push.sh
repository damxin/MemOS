#!/bin/bash
# GitHub Push Script for MemOS
# Usage: ./github-push.sh [token|ssh|manual]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

cd "$(dirname "$0")"

echo -e "${BLUE}MemOS GitHub Push Script${NC}"
echo "=========================="
echo ""

# Check git status
echo -e "${BLUE}Checking git status...${NC}"
git status --short

# Get current branch
BRANCH=$(git branch --show-current)
echo ""
echo -e "${BLUE}Current branch: ${GREEN}${BRANCH}${NC}"
echo ""

# Count commits ahead of origin
AHEAD=$(git rev-list --count origin/${BRANCH}..${BRANCH} 2>/dev/null || echo "0")
if [ "$AHEAD" -gt 0 ]; then
    echo -e "${GREEN}You have ${AHEAD} commit(s) ready to push${NC}"
    git log --oneline origin/${BRANCH}..${BRANCH}
else
    echo -e "${YELLOW}No new commits to push${NC}"
    exit 0
fi

echo ""
echo "=========================="
echo "Choose push method:"
echo ""
echo "1) HTTPS with Personal Access Token (PAT)"
echo "2) SSH Key (if configured)"
echo "3) Show manual push commands"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo -e "${BLUE}HTTPS with PAT selected${NC}"
        echo ""
        echo "To create a PAT:"
        echo "  1. Go to https://github.com/settings/tokens/new"
        echo "  2. Select 'repo' scope"
        echo "  3. Generate and copy the token"
        echo ""
        read -p "Enter your GitHub username: " username
        read -sp "Enter your Personal Access Token: " token
        echo ""
        echo ""
        echo -e "${YELLOW}Pushing to GitHub...${NC}"
        
        if git push https://${username}:${token}@github.com/damxin/MemOS.git ${BRANCH}; then
            echo ""
            echo -e "${GREEN}✅ Push successful!${NC}"
            echo ""
            echo "View your changes at:"
            echo "  https://github.com/damxin/MemOS"
        else
            echo ""
            echo -e "${RED}❌ Push failed${NC}"
            exit 1
        fi
        ;;
    
    2)
        echo ""
        echo -e "${BLUE}SSH Key selected${NC}"
        
        # Check if SSH key exists
        if [ ! -f ~/.ssh/id_ed25519 ] && [ ! -f ~/.ssh/id_rsa ]; then
            echo ""
            echo -e "${YELLOW}No SSH key found. Generating one...${NC}"
            ssh-keygen -t ed25519 -C "dev@memos.io" -f ~/.ssh/id_ed25519 -N ""
            echo ""
            echo -e "${GREEN}SSH key generated!${NC}"
            echo ""
            echo "Add this public key to GitHub:"
            echo "  https://github.com/settings/keys"
            echo ""
            cat ~/.ssh/id_ed25519.pub
            echo ""
            read -p "Press Enter after adding the key to GitHub..."
        fi
        
        # Set remote to SSH
        git remote set-url origin git@github.com:damxin/MemOS.git
        
        echo ""
        echo -e "${YELLOW}Pushing to GitHub via SSH...${NC}"
        if git push origin ${BRANCH}; then
            echo ""
            echo -e "${GREEN}✅ Push successful!${NC}"
        else
            echo ""
            echo -e "${RED}❌ Push failed${NC}"
            echo ""
            echo "Troubleshooting:"
            echo "  1. Ensure SSH key is added to GitHub: https://github.com/settings/keys"
            echo "  2. Test SSH connection: ssh -T git@github.com"
            exit 1
        fi
        ;;
    
    3)
        echo ""
        echo -e "${BLUE}Manual push commands:${NC}"
        echo ""
        echo "Option A - HTTPS with PAT:"
        echo "  git push https://USERNAME:TOKEN@github.com/damxin/MemOS.git main"
        echo ""
        echo "Option B - SSH:"
        echo "  git remote set-url origin git@github.com:damxin/MemOS.git"
        echo "  git push origin main"
        echo ""
        echo "Option C - GitHub CLI:"
        echo "  gh auth login"
        echo "  git push origin main"
        ;;
    
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo "=========================="
echo -e "${GREEN}Done!${NC}"
