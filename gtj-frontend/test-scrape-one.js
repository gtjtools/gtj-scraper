const fs = require('fs');
const path = require('path');

// Check if cookies.txt exists
const cookiesPath = path.join(__dirname, 'cookies.txt');
const hasCookies = fs.existsSync(cookiesPath);

console.log('='.repeat(60));
console.log('Testing Single Operator Scrape');
console.log('='.repeat(60));
console.log(`\nCookies file exists: ${hasCookies ? 'YES ✓' : 'NO ✗'}`);

if (!hasCookies) {
    console.log('\n⚠️  WARNING: No cookies.txt file found!');
    console.log('   The website masks certification data for unauthenticated users.');
    console.log('   You will see null values for Wyvern and IS-BAO certifications.');
    console.log('\nTo fix this:');
    console.log('1. Log in to businessairnews.com in your browser');
    console.log('2. Copy your session cookies');
    console.log('3. Create a file called cookies.txt with the Cookie header value');
    console.log('   Example format: "session_id=abc123; auth_token=xyz789"');
    console.log('\n');
}

// Load the appropriate scraper
let scrapeOperatorDetails;
if (hasCookies) {
    const { scrapeOperatorDetailsAuthenticated } = require('./scraper-authenticated');
    scrapeOperatorDetails = scrapeOperatorDetailsAuthenticated;
    console.log('Using authenticated scraper\n');
} else {
    const { scrapeOperatorDetails: scrapeOp } = require('./scraper');
    scrapeOperatorDetails = scrapeOp;
    console.log('Using unauthenticated scraper\n');
}

// Test URLs
const testOperators = [
    {
        name: 'Advanced Air Charters',
        url: 'https://www.businessairnews.com/hb_charterpage.html?recnum=146978'
    },
    {
        name: 'Flexjet Vertical Lift',
        url: 'https://www.businessairnews.com/hb_charterpage.html?recnum=170580'
    }
];

async function testScrape() {
    for (const operator of testOperators) {
        console.log('='.repeat(60));
        console.log(`Testing: ${operator.name}`);
        console.log(`URL: ${operator.url}`);
        console.log('='.repeat(60));

        try {
            const data = await scrapeOperatorDetails(operator.url);

            console.log('\n✓ Scrape successful!\n');
            console.log('Name:', data.name);
            console.log('Country:', data.country);
            console.log('\nCertifications:');
            console.log('  AOC/Part 135:', data.certifications.aoc_part135 || 'null');
            console.log('  Wyvern Certified:', data.certifications.wyvern_certified || 'null');
            console.log('  ARGUS Rating:', data.certifications.argus_rating || 'null');
            console.log('  IS-BAO:', data.certifications.is_bao || 'null');
            console.log('  ACSF IAS:', data.certifications.acsf_ias || 'null');
            console.log('\nContact:');
            console.log('  Phone:', data.contact.telephone || 'null');
            console.log('  Email:', data.contact.email || 'null');
            console.log('  Website:', data.contact.website || 'null');
            console.log('\n');

        } catch (error) {
            console.log(`\n✗ Error: ${error.message}\n`);
        }
    }
}

testScrape().catch(console.error);
