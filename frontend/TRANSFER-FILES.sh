#!/bin/bash

# First create the directory on the server
echo "Creating directory on server..."
ssh root@134.199.202.100 "mkdir -p /var/www/trustjet-parse-pilot"

# Now upload the files
echo "Uploading application files..."
scp server.js root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp package.json root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp ecosystem.config.js root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp server-setup.sh root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp -r public root@134.199.202.100:/var/www/trustjet-parse-pilot/

echo "Uploading data files..."
scp Part_135_Operators.xlsx root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp charter-operators-enriched.json root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp air-operators.json root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp aircraft.json root@134.199.202.100:/var/www/trustjet-parse-pilot/

echo ""
echo "✅ All files uploaded!"
echo ""
echo "Now SSH into your server and run the setup:"
echo "  ssh root@134.199.202.100"
echo "  cd /var/www/trustjet-parse-pilot"
echo "  chmod +x server-setup.sh"
echo "  ./server-setup.sh"
