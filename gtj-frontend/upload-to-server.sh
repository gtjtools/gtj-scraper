#!/bin/bash

# Quick upload script - run this from your LOCAL machine

SERVER_IP="134.199.202.100"
REMOTE_DIR="/var/www/trustjet-parse-pilot"

echo "📤 Uploading TrustJet Parse Pilot to $SERVER_IP..."

# Create remote directory
ssh root@$SERVER_IP "mkdir -p $REMOTE_DIR"

# Upload all application files
scp -r \
  server.js \
  package.json \
  package-lock.json \
  ecosystem.config.js \
  server-setup.sh \
  public/ \
  root@$SERVER_IP:$REMOTE_DIR/

# Upload data files
echo "📦 Uploading data files..."
scp \
  Part_135_Operators.xlsx \
  charter-operators-enriched.json \
  air-operators.json \
  aircraft.json \
  root@$SERVER_IP:$REMOTE_DIR/

echo ""
echo "✅ Files uploaded!"
echo ""
echo "Now SSH into your server and run:"
echo "  ssh root@$SERVER_IP"
echo "  cd $REMOTE_DIR"
echo "  chmod +x server-setup.sh"
echo "  ./server-setup.sh"
