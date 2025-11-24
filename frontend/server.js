const express = require('express');
const XLSX = require('xlsx');
const path = require('path');
const fs = require('fs');
const basicAuth = require('express-basic-auth');
const { enrichOperatorData } = require('./scraper');

const app = express();
const PORT = process.env.PORT || 3001;

// Password protection - Only in production
if (process.env.NODE_ENV === 'production') {
    const auth = basicAuth({
        users: {
            'admin': process.env.APP_PASSWORD || 'trustjet2024'
        },
        challenge: true,
        realm: 'TrustJet Parse Pilot'
    });
    app.use(auth);
    console.log('Password protection enabled (production mode)');
} else {
    console.log('Password protection disabled (development mode)');
}

// In-memory database
let operatorsData = [];
let enrichedData = new Map(); // Store enriched data by operator name
let scrapedCharterData = []; // Store pre-scraped charter company data

// Parse Excel file and load into memory
function loadExcelData() {
    try {
        const filePath = path.join(__dirname, 'Part_135_Operators.xlsx');

        if (!fs.existsSync(filePath)) {
            console.error('Excel file not found:', filePath);
            return;
        }

        const workbook = XLSX.readFile(filePath);
        const sheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[sheetName];

        // Get all data as array
        const allData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });

        // Row 0 is title, Row 1 is date updated, Row 2 is headers, Row 3+ is data
        const headers = allData[2]; // ["Part 135 Certificate Holder Name", "Certificate Designator", ...]
        const dataRows = allData.slice(3); // Skip title, date, and header rows

        // Convert to array of objects with proper headers
        operatorsData = dataRows
            .filter(row => {
                // Skip empty rows
                return row && row.some(cell => cell && String(cell).trim() !== '');
            })
            .map(row => {
                const obj = {};
                headers.forEach((header, index) => {
                    obj[header] = row[index] || '';
                });
                return obj;
            });

        console.log(`Loaded ${operatorsData.length} records from Excel file`);

        // Log first record to see structure
        if (operatorsData.length > 0) {
            console.log('Sample record:', operatorsData[0]);
            console.log('Column headers:', Object.keys(operatorsData[0]));
        }
    } catch (error) {
        console.error('Error loading Excel data:', error);
    }
}

// Load scraped charter data (enriched with scores and AOC IDs)
function loadScrapedCharterData() {
    try {
        // Try enriched data first
        let filePath = path.join(__dirname, 'charter-operators-enriched.json');

        // Fall back to public charter-companies.json if enriched doesn't exist
        if (!fs.existsSync(filePath)) {
            filePath = path.join(__dirname, 'public', 'charter-companies.json');

            if (!fs.existsSync(filePath)) {
                console.log('No charter data found');
                return;
            }

            console.log('Loading charter companies from public/charter-companies.json');
        } else {
            console.log('Loading enriched charter data');
        }

        const rawData = fs.readFileSync(filePath, 'utf-8');
        scrapedCharterData = JSON.parse(rawData);

        // Index by company name for fast lookup
        scrapedCharterData.forEach(entry => {
            if (entry.data) {
                enrichedData.set(entry.company.toLowerCase(), entry.data);
            }
        });

        console.log(`Loaded ${scrapedCharterData.length} enriched charter companies`);
        console.log(`${enrichedData.size} companies have data available`);

        // Count companies with scores
        const withScores = scrapedCharterData.filter(e => e.score > 0).length;
        console.log(`${withScores} companies have certification scores`);

        // Count companies linked to FAA data
        const withFAA = scrapedCharterData.filter(e => e.faa_data).length;
        console.log(`${withFAA} companies linked to FAA Part 135 data`);
    } catch (error) {
        console.error('Error loading scraped charter data:', error);
    }
}

// Serve static files from build directory (production) or public directory (development)
const staticDir = process.env.NODE_ENV === 'production' ? 'build' : 'public';
app.use(express.static(staticDir));
console.log(`Serving static files from: ${staticDir}`);

// API endpoint to get all operators
app.get('/api/operators', (req, res) => {
    res.json({
        total: operatorsData.length,
        data: operatorsData
    });
});

// API endpoint to get single operator by index
app.get('/api/operators/:id', (req, res) => {
    const id = parseInt(req.params.id);
    if (id >= 0 && id < operatorsData.length) {
        res.json(operatorsData[id]);
    } else {
        res.status(404).json({ error: 'Operator not found' });
    }
});

// API endpoint to search operators
app.get('/api/search', (req, res) => {
    const query = req.query.q?.toLowerCase() || '';

    if (!query) {
        return res.json({ data: operatorsData });
    }

    const filtered = operatorsData.filter(op => {
        return Object.values(op).some(val =>
            String(val).toLowerCase().includes(query)
        );
    });

    res.json({
        total: filtered.length,
        data: filtered
    });
});

// API endpoint to search by tail number (registration number)
app.get('/api/search/tail/:tailNumber', (req, res) => {
    try {
        const tailNumber = req.params.tailNumber.toUpperCase().trim();
        console.log(`Tail number search: ${tailNumber}`);

        // Search Part 135 operators for this tail number
        const aircraftRecords = operatorsData.filter(op => {
            const regNum = op['Registration Number'];
            if (!regNum) return false;
            return String(regNum).toUpperCase().trim() === tailNumber;
        });

        if (aircraftRecords.length === 0) {
            return res.json({
                found: false,
                message: 'No aircraft found with this tail number'
            });
        }

        // Get unique operator names from the results
        const operators = [];
        const seenOperators = new Set();

        for (const record of aircraftRecords) {
            const operatorName = record['Part 135 Certificate Holder Name'];
            const certDesignator = record['Certificate Designator'];

            if (!seenOperators.has(operatorName)) {
                seenOperators.add(operatorName);

                // Try to find charter operator data by name or cert designator
                let charterData = null;
                let score = 0;

                // Search charter operators by certificate designator or name
                const charterOperator = scrapedCharterData.find(charter => {
                    if (!charter.data || !charter.data.certifications) return false;

                    const part135Cert = charter.data.certifications.aoc_part135;
                    if (part135Cert) {
                        // Check if cert designator matches
                        if (part135Cert.includes(certDesignator)) {
                            return true;
                        }
                    }

                    // Fuzzy match by operator name
                    const charterName = charter.company.toLowerCase();
                    const operatorNameClean = operatorName.toLowerCase().trim();

                    return charterName.includes(operatorNameClean) ||
                           operatorNameClean.includes(charterName);
                });

                if (charterOperator) {
                    charterData = charterOperator.data;
                    score = charterOperator.score || 0;
                }

                operators.push({
                    operator_name: operatorName,
                    certificate_designator: certDesignator,
                    charter_data: charterData,
                    score: score
                });
            }
        }

        // Get all aircraft for this tail
        const aircraft = aircraftRecords.map(record => ({
            registration: record['Registration Number'],
            serial_number: record['Serial Number'],
            make_model: record['Aircraft Make/Model/Series'],
            operator: record['Part 135 Certificate Holder Name'],
            certificate_designator: record['Certificate Designator'],
            faa_district: record['FAA Certificate Holding District Office']
        }));

        res.json({
            found: true,
            tail_number: tailNumber,
            operators: operators,
            aircraft: aircraft
        });

    } catch (error) {
        console.error('Tail number search error:', error);
        res.status(500).json({
            found: false,
            error: error.message
        });
    }
});

// API endpoint to enrich operator data from Business Air News
app.get('/api/enrich/:operatorName', async (req, res) => {
    try {
        const operatorName = req.params.operatorName;

        // Check if already enriched
        if (enrichedData.has(operatorName)) {
            return res.json({
                cached: true,
                data: enrichedData.get(operatorName)
            });
        }

        // Fetch and cache
        const result = await enrichOperatorData(operatorName);

        if (result.found) {
            enrichedData.set(operatorName, result.data);
        }

        res.json(result);
    } catch (error) {
        console.error('Error enriching operator:', error);
        res.status(500).json({
            found: false,
            error: error.message
        });
    }
});

// API endpoint to get enriched data if available
app.get('/api/enriched/:operatorName', (req, res) => {
    const operatorName = req.params.operatorName;

    if (enrichedData.has(operatorName)) {
        res.json({
            found: true,
            data: enrichedData.get(operatorName)
        });
    } else {
        res.json({
            found: false
        });
    }
});

// API endpoint to get all charter operators (sorted by score)
app.get('/api/charter/operators', (req, res) => {
    res.json({
        total: scrapedCharterData.length,
        data: scrapedCharterData
    });
});

// API endpoint to filter charter operators by certification
app.get('/api/charter/filter', (req, res) => {
    const { cert, minScore } = req.query;

    let filtered = scrapedCharterData;

    // Filter by minimum score
    if (minScore) {
        const minScoreNum = parseInt(minScore);
        filtered = filtered.filter(op => (op.score || 0) >= minScoreNum);
    }

    // Filter by certification type
    if (cert && filtered.length > 0) {
        filtered = filtered.filter(op => {
            if (!op.data || !op.data.certifications) return false;

            const certs = op.data.certifications;
            const certLower = cert.toLowerCase();

            // Check for specific certifications
            if (certLower.includes('argus')) {
                if (certLower.includes('platinum')) {
                    return certs.argus_rating && certs.argus_rating.toLowerCase().includes('platinum');
                }
                if (certLower.includes('gold')) {
                    return certs.argus_rating && certs.argus_rating.toLowerCase().includes('gold');
                }
                return certs.argus_rating && certs.argus_rating !== 'No' && certs.argus_rating !== 'N/A';
            }

            if (certLower.includes('wyvern')) {
                return certs.wyvern_certified && certs.wyvern_certified !== 'No' && certs.wyvern_certified !== 'N/A';
            }

            if (certLower.includes('is-bao') || certLower.includes('isbao')) {
                return certs.is_bao && certs.is_bao !== 'No' && certs.is_bao !== 'N/A';
            }

            return false;
        });
    }

    res.json({
        total: filtered.length,
        filters: { cert, minScore },
        data: filtered
    });
});

// API endpoint for direct charter search (no Part 135 lookup)
app.get('/api/charter/search/:operatorName', async (req, res) => {
    try {
        const operatorName = req.params.operatorName;

        console.log(`Charter search for: ${operatorName}`);

        // Check if it's a record number
        if (/^\d+$/.test(operatorName)) {
            const recnum = operatorName;

            // First check if we have this record in scraped data
            const scrapedEntry = scrapedCharterData.find(entry =>
                entry.url && entry.url.includes(`recnum=${recnum}`)
            );

            if (scrapedEntry && scrapedEntry.data) {
                console.log(`Found in scraped data cache`);
                return res.json({
                    found: true,
                    cached: true,
                    data: scrapedEntry.data
                });
            }

            const url = `https://www.businessairnews.com/hb_charterpage.html?recnum=${recnum}`;

            console.log(`Direct record number lookup: ${url}`);

            const { scrapeOperatorDetails } = require('./scraper');
            const details = await scrapeOperatorDetails(url);

            enrichedData.set(operatorName, details);

            return res.json({
                found: true,
                data: details
            });
        }

        // Check cache first for name searches (includes scraped data)
        if (enrichedData.has(operatorName.toLowerCase())) {
            return res.json({
                found: true,
                cached: true,
                data: enrichedData.get(operatorName.toLowerCase())
            });
        }

        // Direct search on Business Air News
        const result = await enrichOperatorData(operatorName);

        if (result.found) {
            enrichedData.set(operatorName.toLowerCase(), result.data);
        }

        res.json(result);
    } catch (error) {
        console.error('Charter search error:', error);
        res.status(500).json({
            found: false,
            error: error.message
        });
    }
});

// Load data on startup
loadExcelData();
loadScrapedCharterData();

// Catch-all route to serve React app for client-side routing (SPA)
app.get('*', (req, res) => {
    const indexPath = path.join(__dirname, staticDir, 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Application not found');
    }
});

app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}`);
});
