const fs = require('fs');
const path = require('path');

// Check if authenticated scraper is available (requires cookies.txt)
let scrapeOperatorDetails;
try {
    if (fs.existsSync(path.join(__dirname, 'cookies.txt'))) {
        const { scrapeOperatorDetailsAuthenticated } = require('./scraper-authenticated');
        scrapeOperatorDetails = scrapeOperatorDetailsAuthenticated;
        console.log('✓ Using authenticated scraper with cookies');
    } else {
        const { scrapeOperatorDetails: scrapeOp } = require('./scraper');
        scrapeOperatorDetails = scrapeOp;
        console.log('⚠ Using unauthenticated scraper (data may be masked)');
        console.log('  To use authenticated scraper, create cookies.txt file');
    }
} catch (error) {
    const { scrapeOperatorDetails: scrapeOp } = require('./scraper');
    scrapeOperatorDetails = scrapeOp;
    console.log('⚠ Using unauthenticated scraper');
}

// Load charter companies
const companiesData = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'public/charter-companies.json'), 'utf-8')
);

// Get command line arguments
const args = process.argv.slice(2);
const startLetter = (args[0] || 'B').toUpperCase();
const delaySeconds = parseInt(args[1]) || 5; // Default 5 seconds between requests
const delayMs = delaySeconds * 1000;

// Filter companies starting with specified letter
const letterCompanies = companiesData.filter(company =>
    company.company.toUpperCase().startsWith(startLetter)
);

console.log(`Found ${letterCompanies.length} companies starting with '${startLetter}'`);
console.log(`Using ${delaySeconds} second delay between requests`);

// Function to scrape with delay
async function scrapeWithDelay(companies, delayMs) {
    const results = [];

    for (let i = 0; i < companies.length; i++) {
        const company = companies[i];
        console.log(`\n[${i + 1}/${companies.length}] Scraping: ${company.company}`);

        if (!company.url) {
            console.log('  No URL available, skipping...');
            results.push({
                company: company.company,
                locations: company.locations,
                url: null,
                data: null,
                error: 'No URL available'
            });
            continue;
        }

        try {
            const data = await scrapeOperatorDetails(company.url);

            results.push({
                company: company.company,
                locations: company.locations,
                url: company.url,
                data: data,
                scrapedAt: new Date().toISOString()
            });

            console.log('  ✓ Success');
            console.log(`  Name: ${data.name || 'N/A'}`);
            console.log(`  Country: ${data.country || 'N/A'}`);
            console.log(`  Part 135: ${data.certifications.aoc_part135 || 'N/A'}`);
            console.log(`  Email: ${data.contact.email || 'N/A'}`);
            console.log(`  Phone: ${data.contact.telephone || 'N/A'}`);
            console.log(`  Bases: ${data.bases.length}`);

            // Save intermediate results after each successful scrape
            const outputPath = path.join(__dirname, `scraped-data-${startLetter}.json`);
            fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));

            // Add delay between requests
            if (i < companies.length - 1) {
                console.log(`  Waiting ${delaySeconds}s before next request...`);
                await new Promise(resolve => setTimeout(resolve, delayMs));
            }
        } catch (error) {
            console.log(`  ✗ Error: ${error.message}`);
            results.push({
                company: company.company,
                locations: company.locations,
                url: company.url,
                data: null,
                error: error.message,
                scrapedAt: new Date().toISOString()
            });

            // Save intermediate results even on error
            const outputPath = path.join(__dirname, `scraped-data-${startLetter}.json`);
            fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));

            // Still wait on error
            if (i < companies.length - 1) {
                await new Promise(resolve => setTimeout(resolve, delayMs));
            }
        }
    }

    return results;
}

// Main execution
async function main() {
    console.log(`\nStarting scrape of companies starting with '${startLetter}'...\n`);
    console.log('='  .repeat(60));

    const results = await scrapeWithDelay(letterCompanies, delayMs);

    // Save final results
    const outputPath = path.join(__dirname, `scraped-data-${startLetter}.json`);
    fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));

    console.log('\n' + '='.repeat(60));
    console.log('\nScraping complete!');
    console.log(`Results saved to: ${outputPath}`);
    console.log(`\nSummary:`);
    console.log(`  Total companies: ${results.length}`);
    console.log(`  Successful: ${results.filter(r => r.data).length}`);
    console.log(`  Failed: ${results.filter(r => !r.data).length}`);

    // Suggest next letter
    const nextLetter = String.fromCharCode(startLetter.charCodeAt(0) + 1);
    if (nextLetter <= 'Z') {
        console.log(`\nTo scrape the next letter, run:`);
        console.log(`  node scrape-alphabet.js ${nextLetter} ${delaySeconds}`);
    }
}

main().catch(console.error);
