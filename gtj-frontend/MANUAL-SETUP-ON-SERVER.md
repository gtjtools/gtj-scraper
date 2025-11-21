# Manual Setup - Run These Commands on Your Server

Since you're already SSH'd into your server at 134.199.202.100, here's the complete setup process. Copy and paste these commands directly into your server terminal.

## Step 1: Install Prerequisites

```bash
# Install PM2
npm install -g pm2

# Install Nginx
apt install -y nginx
```

## Step 2: Create Application Directory

```bash
mkdir -p /var/www/trustjet-parse-pilot
cd /var/www/trustjet-parse-pilot
```

## Step 3: Create package.json

```bash
cat > package.json << 'EOF'
{
  "name": "trustjet-parse-pilot",
  "version": "1.0.0",
  "description": "TrustJet Charter Operator Lookup",
  "main": "server.js",
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "express-basic-auth": "^1.2.1",
    "cheerio": "^1.0.0-rc.12",
    "axios": "^1.4.0",
    "xlsx": "^0.18.5"
  }
}
EOF
```

## Step 4: Create Environment File

```bash
cat > .env << 'EOF'
APP_PASSWORD=1!TJpjnumber
PORT=3000
NODE_ENV=production
EOF
```

## Step 5: Create Ecosystem Config

```bash
cat > ecosystem.config.js << 'EOF'
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
```

## Step 6: Configure Nginx

```bash
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

# Enable site
ln -sf /etc/nginx/sites-available/trustjet /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
```

## Step 7: Configure Firewall

```bash
ufw allow 22
ufw allow 80
ufw allow 443
echo "y" | ufw enable
```

## Step 8: Upload Files

Now you need to get the application files onto the server. You have 3 options:

### Option A: Use Git (if you have a repo)
```bash
# Clone your repo
git clone YOUR_REPO_URL .
```

### Option B: Copy from local machine (run this on YOUR LOCAL MACHINE in a new terminal)
```bash
cd /Users/jonassison/Downloads/TrustJet/weyobe/trustjet-parse-pilot
scp server.js root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp -r public root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp Part_135_Operators.xlsx root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp charter-operators-enriched.json root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp air-operators.json root@134.199.202.100:/var/www/trustjet-parse-pilot/
scp aircraft.json root@134.199.202.100:/var/www/trustjet-parse-pilot/
```

### Option C: Create files manually on server

I'll provide the complete server.js and HTML files next if you need to create them manually.

## Step 9: Install Dependencies and Start

```bash
cd /var/www/trustjet-parse-pilot
npm install --production
pm2 start ecosystem.config.js
pm2 save
pm2 startup | tail -1 | bash
```

## Step 10: Verify

Visit: http://134.199.202.100

Login:
- Username: admin
- Password: 1!TJpjnumber

## Check Status

```bash
pm2 status
pm2 logs trustjet-parse-pilot
systemctl status nginx
```
