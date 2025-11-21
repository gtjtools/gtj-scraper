const fs = require('fs');
const path = require('path');

// Get all scraped data files (excluding old/masked versions)
const files = fs.readdirSync(__dirname)
    .filter(f => f.startsWith('scraped-data-') && f.endsWith('.json'))
    .filter(f => !f.includes('old') && !f.includes('masked'))
    .filter(f => f !== 'scraped-data-combined.json'); // Exclude the combined file itself

console.log(`Found ${files.length} files to combine:`);
files.forEach(f => console.log(`  - ${f}`));

// Combine all data
let combinedData = [];
let stats = {
    totalFiles: files.length,
    totalCompanies: 0,
    successfulScrapes: 0,
    failedScrapes: 0,
    byLetter: {}
};

files.forEach(file => {
    const filePath = path.join(__dirname, file);
    const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const letter = file.replace('scraped-data-', '').replace('.json', '');

    const successful = data.filter(r => r.data).length;
    const failed = data.filter(r => !r.data).length;

    stats.byLetter[letter] = {
        total: data.length,
        successful,
        failed
    };

    stats.totalCompanies += data.length;
    stats.successfulScrapes += successful;
    stats.failedScrapes += failed;

    combinedData = combinedData.concat(data);
});

// Sort combined data alphabetically by company name
combinedData.sort((a, b) => a.company.localeCompare(b.company));

// Save combined data
const outputPath = path.join(__dirname, 'scraped-data-combined.json');
fs.writeFileSync(outputPath, JSON.stringify(combinedData, null, 2));

console.log('\n' + '='.repeat(60));
console.log('Combined data saved to: scraped-data-combined.json');
console.log('='.repeat(60));
console.log('\nStatistics:');
console.log(`  Total files combined: ${stats.totalFiles}`);
console.log(`  Total companies: ${stats.totalCompanies}`);
console.log(`  Successful scrapes: ${stats.successfulScrapes}`);
console.log(`  Failed scrapes: ${stats.failedScrapes}`);
console.log(`  Success rate: ${((stats.successfulScrapes / stats.totalCompanies) * 100).toFixed(2)}%`);

console.log('\nBreakdown by letter/number:');
Object.keys(stats.byLetter).sort().forEach(letter => {
    const s = stats.byLetter[letter];
    console.log(`  ${letter.toUpperCase().padEnd(10)}: ${s.total} companies (${s.successful} successful, ${s.failed} failed)`);
});

console.log('\n✓ Data is sorted alphabetically by company name');
