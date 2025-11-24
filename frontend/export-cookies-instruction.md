# Export Cookies from Business Air News

## Quick Method (Browser Console):

1. Open https://www.businessairnews.com in your browser
2. Make sure you're logged in
3. Open Developer Tools (F12 or Right-click → Inspect)
4. Go to the "Console" tab
5. Paste this code and press Enter:

```javascript
copy(document.cookie)
```

6. This copies your cookies to clipboard
7. Create a file called `cookies.txt` in the trustjet-parse-pilot folder
8. Paste the cookies into that file

## Alternative Method (Using Cookie Extension):

1. Install "EditThisCookie" extension from Chrome Web Store
2. Go to businessairnews.com (logged in)
3. Click the EditThisCookie icon
4. Click "Export" button
5. Copy the JSON
6. Save to `cookies.json` in the trustjet-parse-pilot folder

Once you have the cookies, let me know and I'll create the authenticated scraper!
