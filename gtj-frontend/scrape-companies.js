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

// Filter companies starting with 'A'
const aCompanies = companiesData.filter(company =>
    company.company.toUpperCase().startsWith('A')
);

console.log(`Found ${aCompanies.length} companies starting with 'A'`);

// Function to scrape with delay
async function scrapeWithDelay(companies, delayMs = 2000) {
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
            console.log(`  Certifications: ${Object.values(data.certifications).filter(v => v).length} found`);
            console.log(`  Bases: ${data.bases.length}`);
            console.log(`  Contact: ${data.contact.email || 'N/A'}`);

            // Add delay between requests to be respectful
            if (i < companies.length - 1) {
                console.log(`  Waiting ${delayMs}ms before next request...`);
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
    console.log('Starting scrape of companies starting with A...\n');
    console.log('='  .repeat(60));

    const results = await scrapeWithDelay(aCompanies, 2000);

    // Save results
    const outputPath = path.join(__dirname, 'scraped-data-A.json');
    fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));

    console.log('\n' + '='.repeat(60));
    console.log('\nScraping complete!');
    console.log(`Results saved to: ${outputPath}`);
    console.log(`\nSummary:`);
    console.log(`  Total companies: ${results.length}`);
    console.log(`  Successful: ${results.filter(r => r.data).length}`);
    console.log(`  Failed: ${results.filter(r => !r.data).length}`);
}

main().catch(console.error);
