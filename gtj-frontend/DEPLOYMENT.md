# TrustJet Parse Pilot - Digital Ocean Deployment Guide

## Prerequisites
- Digital Ocean account
- Domain name (optional, but recommended)
- SSH key configured

## Step 1: Create Digital Ocean Droplet

1. Log in to Digital Ocean
2. Click "Create" → "Droplets"
3. Choose configuration:
   - **Image**: Ubuntu 22.04 LTS
   - **Plan**: Basic ($6/month - 1GB RAM, 1 CPU should be sufficient)
   - **Datacenter**: Choose closest to your location
   - **Authentication**: SSH key (recommended)
   - **Hostname**: trustjet-parse-pilot

4. Click "Create Droplet"
5. Note your droplet's IP address

## Step 2: Initial Server Setup

SSH into your droplet:
```bash
ssh root@YOUR_DROPLET_IP
```

Update the system:
```bash
apt update && apt upgrade -y
```

Install Node.js 18.x:
```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt install -y nodejs
```

Install PM2 (process manager):
```bash
npm install -g pm2
```

Install Nginx (web server):
```bash
apt install -y nginx
```

## Step 3: Upload Your Application

### Option A: Using rsync (from your local machine)

```bash
# From your local machine, in the trustjet-parse-pilot directory
rsync -avz --exclude 'node_modules' \
  --exclude '.DS_Store' \
  --exclude 'scraped-data-*.json' \
  . root@YOUR_DROPLET_IP:/var/www/trustjet-parse-pilot/
```

### Option B: Using Git

```bash
# On the server
cd /var/www
git clone YOUR_REPO_URL trustjet-parse-pilot
cd trustjet-parse-pilot
```

## Step 4: Configure the Application

On the server:

```bash
cd /var/www/trustjet-parse-pilot

# Install dependencies
npm install --production

# Create environment file
nano .env
```

Add the following to `.env`:
```
APP_PASSWORD=your_secure_password_here
PORT=3000
NODE_ENV=production
```

**Important**: Change `your_secure_password_here` to a strong password!

## Step 5: Upload Data Files

You need to upload these files from your local machine:

```bash
# From your local machine
scp Part_135_Operators.xlsx root@YOUR_DROPLET_IP:/var/www/trustjet-parse-pilot/
scp charter-operators-enriched.json root@YOUR_DROPLET_IP:/var/www/trustjet-parse-pilot/
scp air-operators.json root@YOUR_DROPLET_IP:/var/www/trustjet-parse-pilot/
scp aircraft.json root@YOUR_DROPLET_IP:/var/www/trustjet-parse-pilot/
```

## Step 6: Start the Application

On the server:

```bash
cd /var/www/trustjet-parse-pilot

# Start with PM2
pm2 start ecosystem.config.js

# Save PM2 configuration
pm2 save

# Set PM2 to start on boot
pm2 startup
# Follow the command it outputs
```

## Step 7: Configure Nginx as Reverse Proxy

On the server:

```bash
nano /etc/nginx/sites-available/trustjet
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

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
```

Enable the site:

```bash
ln -s /etc/nginx/sites-available/trustjet /etc/nginx/sites-enabled/
nginx -t  # Test configuration
systemctl restart nginx
```

## Step 8: Set Up Firewall

```bash
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS (for SSL later)
ufw enable
```

## Step 9: (Optional) Set Up SSL with Let's Encrypt

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

## Step 10: Access Your Application

Visit `http://YOUR_DROPLET_IP` or `http://your-domain.com`

You'll be prompted for credentials:
- **Username**: `admin`
- **Password**: (the password you set in .env file)

## Useful Commands

### Check application status
```bash
pm2 status
pm2 logs trustjet-parse-pilot
```

### Restart application
```bash
pm2 restart trustjet-parse-pilot
```

### Update application
```bash
cd /var/www/trustjet-parse-pilot
git pull  # if using git
npm install --production
pm2 restart trustjet-parse-pilot
```

### View Nginx logs
```bash
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

## Security Recommendations

1. **Change the default password** immediately after first deployment
2. **Set up SSH key authentication** and disable password login
3. **Keep the system updated**: `apt update && apt upgrade`
4. **Use SSL/HTTPS** in production
5. **Restrict SSH access** to specific IP addresses if possible
6. **Regular backups** of your data files

## Updating Data Files

To update the charter operator data or Part 135 data:

```bash
# From your local machine
scp charter-operators-enriched.json root@YOUR_DROPLET_IP:/var/www/trustjet-parse-pilot/
scp Part_135_Operators.xlsx root@YOUR_DROPLET_IP:/var/www/trustjet-parse-pilot/

# On the server
pm2 restart trustjet-parse-pilot
```

## Troubleshooting

### Application won't start
```bash
cd /var/www/trustjet-parse-pilot
pm2 logs trustjet-parse-pilot
```

### Can't access the site
```bash
# Check if app is running
pm2 status

# Check Nginx status
systemctl status nginx

# Check firewall
ufw status
```

### Password not working
Make sure your `.env` file has the correct APP_PASSWORD set and restart the app:
```bash
pm2 restart trustjet-parse-pilot
```

## Cost Estimate

- **Droplet**: $6/month (1GB RAM)
- **Domain** (optional): ~$12/year
- **Total**: ~$6-7/month

---

For support or questions, refer to the main README.md file.
