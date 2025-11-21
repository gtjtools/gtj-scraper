const fs = require('fs');
const path = require('path');

// Certification scoring weights
const CERTIFICATION_SCORES = {
    // Safety certifications (highest value)
    'wyvern_wingman': 100,
    'wyvern_registered': 75,
    'argus_platinum': 90,
    'argus_gold': 70,
    'argus_gold_plus': 80,
    'argus_rated': 50,
    'is_bao_stage_3': 85,
    'is_bao_stage_2': 65,
    'is_bao_stage_1': 45,

    // Other certifications
    'airsafe': 30,
    'trips': 25,
    'bars': 40,

    // Part 135 (baseline)
    'aoc_part135': 20,
    'aoc_part121': 25,
};

// Calculate composite score for an operator
function calculateScore(certifications) {
    if (!certifications) return 0;

    let score = 0;
    let certCount = 0;

    // Part 135 certification
    if (certifications.aoc_part135 && certifications.aoc_part135 !== 'N/A' && certifications.aoc_part135 !== 'No') {
        score += CERTIFICATION_SCORES.aoc_part135;
        certCount++;
    }

    // Part 121 certification
    if (certifications.aoc_part121 && certifications.aoc_part121 !== 'N/A' && certifications.aoc_part121 !== 'No') {
        score += CERTIFICATION_SCORES.aoc_part121;
        certCount++;
    }

    // Wyvern certifications (check the wyvern_certified field)
    if (certifications.wyvern_certified) {
        const wyvernValue = String(certifications.wyvern_certified).toLowerCase();
        if (wyvernValue.includes('wingman')) {
            score += CERTIFICATION_SCORES.wyvern_wingman;
            certCount++;
        } else if (wyvernValue.includes('registered') || (wyvernValue !== 'no' && wyvernValue !== 'n/a' && wyvernValue !== '')) {
            score += CERTIFICATION_SCORES.wyvern_registered;
            certCount++;
        }
    }

    // ARGUS ratings (check the argus_rating field)
    if (certifications.argus_rating) {
        const argusValue = String(certifications.argus_rating).toLowerCase();
        if (argusValue.includes('platinum')) {
            score += CERTIFICATION_SCORES.argus_platinum;
            certCount++;
        } else if (argusValue.includes('gold plus')) {
            score += CERTIFICATION_SCORES.argus_gold_plus;
            certCount++;
        } else if (argusValue.includes('gold')) {
            score += CERTIFICATION_SCORES.argus_gold;
            certCount++;
        } else if (argusValue !== 'no' && argusValue !== 'n/a' && argusValue !== '') {
            score += CERTIFICATION_SCORES.argus_rated;
            certCount++;
        }
    }

    // IS-BAO certifications (check the is_bao field)
    if (certifications.is_bao) {
        const isbaoValue = String(certifications.is_bao).toLowerCase();
        if (isbaoValue.includes('stage 3') || isbaoValue.includes('stage3')) {
            score += CERTIFICATION_SCORES.is_bao_stage_3;
            certCount++;
        } else if (isbaoValue.includes('stage 2') || isbaoValue.includes('stage2')) {
            score += CERTIFICATION_SCORES.is_bao_stage_2;
            certCount++;
        } else if (isbaoValue.includes('stage 1') || isbaoValue.includes('stage1') || (isbaoValue !== 'no' && isbaoValue !== 'n/a' && isbaoValue !== '')) {
            score += CERTIFICATION_SCORES.is_bao_stage_1;
            certCount++;
        }
    }

    // ACSF/IAS certification
    if (certifications.acsf_ias && certifications.acsf_ias !== 'No' && certifications.acsf_ias !== 'N/A') {
        score += 30; // Additional certification bonus
        certCount++;
    }

    // Bonus for having multiple certifications (synergy bonus)
    if (certCount >= 3) score += 50;
    if (certCount >= 5) score += 75;
    if (certCount >= 7) score += 100;

    return score;
}

// Extract Part 135 certificate from certification data
function extractPart135(certifications) {
    if (!certifications || !certifications.aoc_part135) return null;

    const part135 = certifications.aoc_part135;
    if (part135 === 'N/A' || part135 === '' || part135 === 'No') return null;

    return part135;
}

// Main enrichment function
function enrichCharterData() {
    console.log('=' .repeat(60));
    console.log('Enriching Charter Data with Scores and AOC IDs');
    console.log('='.repeat(60));

    // Load combined scraped charter data
    const scrapedPath = path.join(__dirname, 'scraped-data-combined.json');
    if (!fs.existsSync(scrapedPath)) {
        console.error('Combined scraped data not found!');
        return;
    }

    const scrapedData = JSON.parse(fs.readFileSync(scrapedPath, 'utf-8'));
    console.log(`\nLoaded ${scrapedData.length} charter companies`);

    // Load air operators data
    const operatorsPath = path.join(__dirname, 'air-operators.json');
    let airOperators = [];
    if (fs.existsSync(operatorsPath)) {
        airOperators = JSON.parse(fs.readFileSync(operatorsPath, 'utf-8'));
        console.log(`Loaded ${airOperators.length} air operators from FAA data`);
    }

    // Create lookup map by Certificate_Number (DSGN_CODE + number)
    const operatorsByCert = new Map();
    airOperators.forEach(op => {
        if (op.Certificate_Number) {
            operatorsByCert.set(op.Certificate_Number.toUpperCase(), op);
        }
    });

    // Enrich each charter company
    let enrichedCount = 0;
    let scoredCount = 0;
    let linkedCount = 0;

    const enrichedData = scrapedData.map(entry => {
        const enriched = { ...entry };

        if (entry.data && entry.data.certifications) {
            // Calculate score
            const score = calculateScore(entry.data.certifications);
            enriched.score = score;
            if (score > 0) scoredCount++;

            // Extract Part 135 cert
            const part135 = extractPart135(entry.data.certifications);
            enriched.part135_cert = part135;

            // Try to link to FAA air operator data
            if (part135) {
                const part135Upper = part135.toUpperCase();
                // Try exact match first
                let airOp = operatorsByCert.get(part135Upper);

                // If not found, try extracting just the code part (e.g., "DDDA592Q" from various formats)
                if (!airOp) {
                    for (const [certNum, op] of operatorsByCert) {
                        if (part135Upper.includes(certNum) || certNum.includes(part135Upper)) {
                            airOp = op;
                            break;
                        }
                    }
                }

                if (airOp) {
                    enriched.faa_data = {
                        operator_name: airOp.Air_Operator_Name,
                        certificate_number: airOp.Certificate_Number,
                        dsgn_code: airOp.DSGN_CODE,
                        ceo: airOp['CEO Name'],
                        city: airOp.City,
                        state: airOp.St,
                        pic_captains: airOp.PIC_Captains
                    };
                    linkedCount++;
                }
            }

            enrichedCount++;
        }

        return enriched;
    });

    // Sort by score (highest first)
    enrichedData.sort((a, b) => (b.score || 0) - (a.score || 0));

    // Save enriched data
    const outputPath = path.join(__dirname, 'charter-operators-enriched.json');
    fs.writeFileSync(outputPath, JSON.stringify(enrichedData, null, 2));

    console.log('\n' + '='.repeat(60));
    console.log('Enrichment Complete!');
    console.log('='.repeat(60));
    console.log(`\nTotal companies: ${enrichedData.length}`);
    console.log(`Companies with data: ${enrichedCount}`);
    console.log(`Companies with scores: ${scoredCount}`);
    console.log(`Companies linked to FAA data: ${linkedCount}`);
    console.log(`\nSaved to: ${outputPath}`);

    // Show top 10 scored operators
    console.log('\n' + '='.repeat(60));
    console.log('Top 10 Highest Scored Operators:');
    console.log('='.repeat(60));
    enrichedData.slice(0, 10).forEach((entry, idx) => {
        if (entry.score) {
            console.log(`${idx + 1}. ${entry.company.padEnd(40)} Score: ${entry.score}`);
            if (entry.data && entry.data.certifications) {
                const certs = [];
                if (entry.data.certifications.wyvern_wingman && entry.data.certifications.wyvern_wingman !== 'N/A') certs.push('Wyvern Wingman');
                if (entry.data.certifications.argus_platinum && entry.data.certifications.argus_platinum !== 'N/A') certs.push('ARGUS Platinum');
                if (entry.data.certifications.is_bao_stage_3 && entry.data.certifications.is_bao_stage_3 !== 'N/A') certs.push('IS-BAO Stage 3');
                console.log(`   Certifications: ${certs.join(', ') || 'None listed'}`);
            }
        }
    });

    return enrichedData;
}

// Run the enrichment
enrichCharterData();
