#!/bin/bash

# TrustJet Parse Pilot - Complete Server Setup
# Run this on your Digital Ocean droplet

echo "🚀 Setting up TrustJet Parse Pilot..."

# Create .env file
cat > /var/www/trustjet-parse-pilot/.env << 'EOF'
APP_PASSWORD=1!TJpjnumber
PORT=3000
NODE_ENV=production
EOF

echo "✅ Created .env file"

# Create ecosystem.config.js
cat > /var/www/trustjet-parse-pilot/ecosystem.config.js << 'EOF'
module.exports = {
  apps: [{
    name: 'trustjet-parse-pilot',
    script: 'server.js',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production',
      PORT: 3000
    }
  }]
};
EOF

echo "✅ Created ecosystem config"

# Configure Nginx
cat > /etc/nginx/sites-available/trustjet << 'EOF'
server {
    listen 80;
    server_name 134.199.202.100;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/trustjet /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "✅ Configured Nginx"

# Configure firewall
ufw allow 22
ufw allow 80
ufw allow 443
echo "y" | ufw enable

echo "✅ Configured firewall"

# Install dependencies
cd /var/www/trustjet-parse-pilot
npm install --production

echo "✅ Installed dependencies"

# Start application
pm2 start ecosystem.config.js
pm2 save
pm2 startup | tail -1 | bash

echo "✅ Started application with PM2"

echo ""
echo "🎉 Setup complete!"
echo "📍 Visit http://134.199.202.100"
echo "🔑 Login with:"
echo "   Username: admin"
echo "   Password: 1!TJpjnumber"
echo ""
echo "📝 Check status with: pm2 status"
echo "📜 View logs with: pm2 logs"
