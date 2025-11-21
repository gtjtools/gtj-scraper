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

// Load the combined data to get URLs
const combinedData = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'scraped-data-combined.json'), 'utf-8')
);

// Get command line arguments
const args = process.argv.slice(2);
const lettersToScrape = args.length > 0 ? args : ['A', 'B', 'C'];
const delaySeconds = parseFloat(args[args.length - 1]);
const delayMs = !isNaN(delaySeconds) && delaySeconds > 0 ? delaySeconds * 1000 : 0;

// If last arg is a number, remove it from letters
if (!isNaN(delaySeconds)) {
    lettersToScrape.pop();
}

console.log(`\nLetters to scrape: ${lettersToScrape.join(', ')}`);
console.log(`Delay between requests: ${delayMs / 1000}s`);

// Filter companies by letters
const companies = combinedData.filter(company =>
    lettersToScrape.some(letter => company.company.toUpperCase().startsWith(letter.toUpperCase()))
);

console.log(`Found ${companies.length} companies to re-scrape\n`);

// Function to scrape with optional delay
async function scrapeWithDelay(companies, delayMs) {
    const results = [];
    let successCount = 0;
    let errorCount = 0;

    for (let i = 0; i < companies.length; i++) {
        const company = companies[i];
        console.log(`[${i + 1}/${companies.length}] ${company.company}`);

        if (!company.url) {
            console.log('  ✗ No URL available');
            results.push({
                ...company,
                data: null,
                error: 'No URL available'
            });
            errorCount++;
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

            // Show key certifications
            const wyv = data.certifications.wyvern_certified || 'null';
            const argus = data.certifications.argus_rating || 'null';
            const isbao = data.certifications.is_bao || 'null';
            console.log(`  ✓ Wyvern: ${wyv} | ARGUS: ${argus} | IS-BAO: ${isbao}`);

            successCount++;

            // Add delay if specified
            if (delayMs > 0 && i < companies.length - 1) {
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
            errorCount++;

            // Still wait on error if delay specified
            if (delayMs > 0 && i < companies.length - 1) {
                await new Promise(resolve => setTimeout(resolve, delayMs));
            }
        }
    }

    return { results, successCount, errorCount };
}

// Main execution
async function main() {
    console.log('='.repeat(60));
    console.log('Starting re-scrape...');
    console.log('='.repeat(60));
    console.log('');

    const startTime = Date.now();
    const { results, successCount, errorCount } = await scrapeWithDelay(companies, delayMs);

    // Organize by letter
    const resultsByLetter = {};
    lettersToScrape.forEach(letter => {
        resultsByLetter[letter] = results.filter(r =>
            r.company.toUpperCase().startsWith(letter.toUpperCase())
        );
    });

    // Save each letter separately
    for (const letter of lettersToScrape) {
        const letterResults = resultsByLetter[letter];
        if (letterResults.length > 0) {
            const outputPath = path.join(__dirname, `scraped-data-${letter.toUpperCase()}.json`);
            fs.writeFileSync(outputPath, JSON.stringify(letterResults, null, 2));
            console.log(`\n✓ Saved ${letterResults.length} companies to: scraped-data-${letter.toUpperCase()}.json`);
        }
    }

    const duration = ((Date.now() - startTime) / 1000).toFixed(1);

    console.log('\n' + '='.repeat(60));
    console.log('Re-scrape Complete!');
    console.log('='.repeat(60));
    console.log(`\nTotal companies: ${results.length}`);
    console.log(`Successful: ${successCount}`);
    console.log(`Failed: ${errorCount}`);
    console.log(`Duration: ${duration}s`);
    console.log(`\nNext steps:`);
    console.log(`1. Run: node combine-scraped-data.js`);
    console.log(`2. Run: node enrich-charter-data.js`);
    console.log(`3. Restart the server`);
}

main().catch(console.error);
