#!/bin/bash

# TrustJet Parse Pilot - Quick Deployment Script
# Usage: ./deploy.sh YOUR_DROPLET_IP

if [ -z "$1" ]; then
    echo "Error: Please provide your droplet IP address"
    echo "Usage: ./deploy.sh YOUR_DROPLET_IP"
    exit 1
fi

DROPLET_IP=$1
REMOTE_DIR="/var/www/trustjet-parse-pilot"

echo "🚀 Deploying TrustJet Parse Pilot to $DROPLET_IP..."

# Upload application files
echo "📤 Uploading application files..."
rsync -avz --progress \
  --exclude 'node_modules' \
  --exclude '.DS_Store' \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'scraped-data-*.json' \
  --exclude 'cookies.txt' \
  . root@$DROPLET_IP:$REMOTE_DIR/

# Upload data files
echo "📦 Uploading data files..."
scp Part_135_Operators.xlsx root@$DROPLET_IP:$REMOTE_DIR/
scp charter-operators-enriched.json root@$DROPLET_IP:$REMOTE_DIR/
scp air-operators.json root@$DROPLET_IP:$REMOTE_DIR/
scp aircraft.json root@$DROPLET_IP:$REMOTE_DIR/

# Install dependencies and restart
echo "🔧 Installing dependencies and restarting app..."
ssh root@$DROPLET_IP << 'ENDSSH'
cd /var/www/trustjet-parse-pilot
npm install --production
pm2 restart trustjet-parse-pilot || pm2 start ecosystem.config.js
pm2 save
ENDSSH

echo "✅ Deployment complete!"
echo "📍 Visit http://$DROPLET_IP to access your application"
echo "🔑 Login with username: admin and the password you set in .env"
