# Quick Deployment Guide - You're Already on the Server!

Since you're already SSH'd into your droplet at 134.199.202.100, here's what to do:

## Step 1: Install Remaining Prerequisites

You've already installed Node.js. Now install PM2 and Nginx:

```bash
# Install PM2
npm install -g pm2

# Install Nginx
apt install -y nginx
```

## Step 2: Upload Application Files

You have two options:

### Option A: Use Git (Recommended if you have a repo)
```bash
cd /var/www
git clone YOUR_REPO_URL trustjet-parse-pilot
cd trustjet-parse-pilot
```

### Option B: Manual Upload from Your Local Machine

On your **LOCAL MACHINE** (Mac), open a NEW terminal and run:

```bash
cd /Users/jonassison/Downloads/TrustJet/weyobe/trustjet-parse-pilot

# Upload application files
scp -r . root@134.199.202.100:/var/www/trustjet-parse-pilot/
```

When prompted for password, enter your droplet password.

## Step 3: Run the Automated Setup Script

Back on your **SERVER** (134.199.202.100), run:

```bash
cd /var/www/trustjet-parse-pilot
chmod +x server-setup.sh
./server-setup.sh
```

This will automatically:
- Create .env file with password 1!TJpjnumber
- Configure Nginx
- Set up firewall
- Install dependencies
- Start the app with PM2

## Step 4: Access Your Application

Visit: http://134.199.202.100

Login credentials:
- Username: admin
- Password: 1!TJpjnumber

## Troubleshooting

If something goes wrong, check:
```bash
pm2 logs trustjet-parse-pilot
systemctl status nginx
```
