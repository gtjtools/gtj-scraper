const fs = require('fs');
const path = require('path');
const XLSX = require('xlsx');

// Load and parse Air Operators CSV
function loadAirOperators() {
    try {
        const csvPath = '/Users/jonassison/Downloads/Air Operators_data.csv';

        if (!fs.existsSync(csvPath)) {
            console.error('Air Operators CSV not found:', csvPath);
            return [];
        }

        // Read the file with proper encoding
        const fileContent = fs.readFileSync(csvPath, 'utf-16le'); // UTF-16 LE encoding for this file

        // Split into lines
        const lines = fileContent.split('\n').filter(line => line.trim());

        if (lines.length === 0) {
            console.error('CSV file is empty');
            return [];
        }

        // Parse header
        const headers = lines[0].split('\t').map(h => h.trim());
        console.log('CSV Headers:', headers);

        // Parse data rows
        const operators = [];
        for (let i = 1; i < lines.length; i++) {
            const values = lines[i].split('\t');
            const operator = {};

            headers.forEach((header, index) => {
                operator[header] = values[index] ? values[index].trim() : '';
            });

            operators.push(operator);
        }

        console.log(`Loaded ${operators.length} air operators from CSV`);
        console.log('Sample operator:', operators[0]);

        return operators;
    } catch (error) {
        console.error('Error loading Air Operators CSV:', error.message);
        return [];
    }
}

// Load and parse Aircraft XLSX
function loadAircraft() {
    try {
        const xlsxPath = '/Users/jonassison/Downloads/Aircraft.xlsx';

        if (!fs.existsSync(xlsxPath)) {
            console.error('Aircraft XLSX not found:', xlsxPath);
            return [];
        }

        const workbook = XLSX.readFile(xlsxPath);
        const sheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[sheetName];

        // Convert to JSON
        const aircraft = XLSX.utils.sheet_to_json(worksheet);

        console.log(`Loaded ${aircraft.length} aircraft from XLSX`);
        if (aircraft.length > 0) {
            console.log('Sample aircraft:', aircraft[0]);
            console.log('Aircraft columns:', Object.keys(aircraft[0]));
        }

        return aircraft;
    } catch (error) {
        console.error('Error loading Aircraft XLSX:', error.message);
        return [];
    }
}

// Test the functions
console.log('='.repeat(60));
console.log('Loading Air Operators and Aircraft data...');
console.log('='.repeat(60));

const operators = loadAirOperators();
const aircraft = loadAircraft();

// Save processed data for the server to use
if (operators.length > 0) {
    const outputPath = path.join(__dirname, 'air-operators.json');
    fs.writeFileSync(outputPath, JSON.stringify(operators, null, 2));
    console.log(`\n✓ Saved ${operators.length} operators to: air-operators.json`);
}

if (aircraft.length > 0) {
    const outputPath = path.join(__dirname, 'aircraft.json');
    fs.writeFileSync(outputPath, JSON.stringify(aircraft, null, 2));
    console.log(`✓ Saved ${aircraft.length} aircraft to: aircraft.json`);
}

module.exports = { loadAirOperators, loadAircraft };
