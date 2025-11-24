#!/bin/bash

# Quick update script - deploys latest changes to server
# Usage: ./update-server.sh

SERVER_IP="134.199.202.100"
REMOTE_DIR="/var/www/trustjet-parse-pilot"

echo "🚀 Deploying updates to $SERVER_IP..."

# Push to git first (if you have a remote configured)
if git remote | grep -q origin; then
    echo "📤 Pushing to Git..."
    git push origin main
fi

# Upload changed files to server
echo "📤 Uploading files to server..."
rsync -avz --progress \
  --exclude 'node_modules' \
  --exclude '.DS_Store' \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'scraped-data-*.json' \
  --exclude 'cookies.txt' \
  --exclude '*.log' \
  . root@$SERVER_IP:$REMOTE_DIR/

# Restart the application
echo "🔄 Restarting application..."
ssh root@$SERVER_IP << 'ENDSSH'
cd /var/www/trustjet-parse-pilot
npm install --production
pm2 restart trustjet-parse-pilot
pm2 logs trustjet-parse-pilot --lines 10
ENDSSH

echo ""
echo "✅ Deployment complete!"
echo "📍 Visit http://$SERVER_IP to see changes"
