const axios = require('axios');
const cheerio = require('cheerio');

// Base URL for Business Air News charter operators
const BASE_URL = 'https://www.businessairnews.com';
const SEARCH_URL = `${BASE_URL}/hb_charter.html`;

// Configure axios with browser-like headers to avoid blocking
const axiosConfig = {
    headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
};

/**
 * Calculate string similarity using Levenshtein distance
 */
function stringSimilarity(str1, str2) {
    const s1 = str1.toLowerCase().trim();
    const s2 = str2.toLowerCase().trim();

    const matrix = [];
    for (let i = 0; i <= s2.length; i++) {
        matrix[i] = [i];
    }
    for (let j = 0; j <= s1.length; j++) {
        matrix[0][j] = j;
    }

    for (let i = 1; i <= s2.length; i++) {
        for (let j = 1; j <= s1.length; j++) {
            if (s2.charAt(i - 1) === s1.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j] + 1
                );
            }
        }
    }

    const distance = matrix[s2.length][s1.length];
    const maxLength = Math.max(s1.length, s2.length);
    return 1 - distance / maxLength;
}

/**
 * Normalize company name for matching
 */
function normalizeCompanyName(name) {
    return name.toLowerCase()
        .replace(/\b(llc|inc|corp|corporation|limited|ltd|co|company)\b/g, '')
        .replace(/[^a-z0-9\s]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}

/**
 * Search for an operator on Business Air News
 * Returns the URL if found, null otherwise
 */
async function searchOperator(operatorName) {
    try {
        // Normalize the search name
        const normalizedSearch = normalizeCompanyName(operatorName);
        const searchWords = normalizedSearch.split(/\s+/);

        // First, try to construct a direct URL based on common patterns
        const sanitizedName = operatorName.toLowerCase()
            .replace(/[^a-z0-9\s]/g, '')
            .replace(/\s+/g, '_');

        const possibleUrls = [
            `${BASE_URL}/charter/${sanitizedName}.html`,
            `${BASE_URL}/hb_charter/${sanitizedName}.html`,
        ];

        // Try direct URLs first
        for (const url of possibleUrls) {
            try {
                const response = await axios.get(url, { ...axiosConfig, timeout: 5000 });
                if (response.status === 200) {
                    return url;
                }
            } catch (err) {
                // URL doesn't exist, continue
            }
        }

        // If direct URLs don't work, search the main charter page with fuzzy matching
        const response = await axios.get(SEARCH_URL, { ...axiosConfig, timeout: 10000 });
        const $ = cheerio.load(response.data);

        // Collect all potential matches with similarity scores
        const candidates = [];
        $('a').each((i, elem) => {
            const linkText = $(elem).text().trim();
            const href = $(elem).attr('href');

            if (!linkText || !href || !href.includes('hb_charterpage')) {
                return;
            }

            const normalizedLink = normalizeCompanyName(linkText);

            // Calculate similarity score
            const similarity = stringSimilarity(normalizedSearch, normalizedLink);

            // Also check if key words from search are in the link text
            const wordMatchCount = searchWords.filter(word =>
                normalizedLink.includes(word)
            ).length;
            const wordMatchScore = wordMatchCount / searchWords.length;

            // Combined score (weighted average)
            const combinedScore = (similarity * 0.6) + (wordMatchScore * 0.4);

            candidates.push({
                text: linkText,
                href: href.startsWith('http') ? href : `${BASE_URL}/${href}`,
                similarity: combinedScore,
                exactSimilarity: similarity,
                wordMatch: wordMatchScore
            });
        });

        // Sort by similarity score
        candidates.sort((a, b) => b.similarity - a.similarity);

        // Log top candidates for debugging
        if (candidates.length > 0) {
            console.log(`Top matches for "${operatorName}":`);
            candidates.slice(0, 3).forEach(c => {
                console.log(`  - ${c.text} (score: ${c.similarity.toFixed(2)}, exact: ${c.exactSimilarity.toFixed(2)}, words: ${c.wordMatch.toFixed(2)})`);
            });
        }

        // Return best match if similarity is above threshold (0.5 = 50% similar)
        if (candidates.length > 0 && candidates[0].similarity > 0.5) {
            console.log(`Selected: ${candidates[0].text} with score ${candidates[0].similarity.toFixed(2)}`);
            return candidates[0].href;
        }

        return null;
    } catch (error) {
        console.error(`Error searching for operator ${operatorName}:`, error.message);
        return null;
    }
}

/**
 * Scrape operator details from Business Air News page
 */
async function scrapeOperatorDetails(url) {
    try {
        const response = await axios.get(url, { ...axiosConfig, timeout: 10000 });
        const $ = cheerio.load(response.data);

        const details = {
            url: url,
            name: null,
            country: null,
            certifications: {
                aoc_part135: null,
                wyvern_certified: null,
                argus_rating: null,
                is_bao: null,
                acsf_ias: null
            },
            contact: {
                telephone: null,
                email: null,
                website: null
            },
            bases: [],
            aircraft: []
        };

        // Extract operator name from .hb-company div
        const companyDiv = $('.hb-company').first();
        if (companyDiv.length) {
            const fullText = companyDiv.text().trim();
            // Remove country from span if present
            const span = companyDiv.find('span').text().trim();
            if (span) {
                details.name = fullText.replace(span, '').trim();
                // Extract country from span (format: "(U.S.A.)")
                const countryMatch = span.match(/\((.+?)\)/);
                if (countryMatch) {
                    details.country = countryMatch[1].trim();
                }
            } else {
                details.name = fullText;
            }
        }

        // Fallback to h1/h2 if .hb-company not found
        if (!details.name) {
            const nameHeader = $('h1, h2').first().text().trim();
            if (nameHeader) {
                const match = nameHeader.match(/(.+?)\s*\((.+?)\)/);
                if (match) {
                    details.name = match[1].trim();
                    details.country = match[2].trim();
                } else {
                    details.name = nameHeader;
                }
            }
        }

        // Extract certifications
        $('body').each((i, elem) => {
            const text = $(elem).text();

            // AOC/Part 135
            const aocMatch = text.match(/AOC\/Part 135:\s*([^\n]+)/i);
            if (aocMatch) details.certifications.aoc_part135 = aocMatch[1].trim();

            // Wyvern Certified (capture the actual certification level like "Registered", "Wingman", etc.)
            const wyvernMatch = text.match(/Wyvern Certified:\s*([^\n]+)/i);
            if (wyvernMatch) details.certifications.wyvern_certified = wyvernMatch[1].trim();

            // ARGUS Rating
            const argusMatch = text.match(/ARGUS Rating:\s*([^\n]+)/i);
            if (argusMatch) details.certifications.argus_rating = argusMatch[1].trim();

            // IS-BAO (capture stage like "II", "III", "Yes", etc.)
            const isbaoMatch = text.match(/IS-BAO:\s*([^\n]+)/i);
            if (isbaoMatch) details.certifications.is_bao = isbaoMatch[1].trim();

            // ACSF IAS
            const acsfMatch = text.match(/ACSF IAS:\s*(Yes|No)/i);
            if (acsfMatch) details.certifications.acsf_ias = acsfMatch[1];
        });

        // Extract contact information
        const phoneMatch = $('body').text().match(/Telephone:\s*([^\n]+)/i);
        if (phoneMatch) details.contact.telephone = phoneMatch[1].trim();

        const emailMatch = $('a[href^="mailto:"]').first();
        if (emailMatch.length) {
            details.contact.email = emailMatch.attr('href').replace('mailto:', '');
        }

        const webMatch = $('body').text().match(/Web:\s*([^\n]+)/i);
        if (webMatch) {
            details.contact.website = webMatch[1].trim();
        } else {
            // Try to find website link
            $('a[href^="http"]').each((i, elem) => {
                const href = $(elem).attr('href');
                if (href && !href.includes('businessairnews.com') && !href.includes('facebook.com')) {
                    details.contact.website = href;
                    return false;
                }
            });
        }

        // Extract charter bases and aircraft
        // Look for table or structured data with bases
        $('table tr, div').each((i, elem) => {
            const text = $(elem).text();

            // Check if this contains base information
            if (text.match(/^\s*[A-Za-z\s]+\s+\d+\s*x\s*[A-Za-z0-9\s]+/)) {
                const baseMatch = text.match(/^\s*([A-Za-z\s\(\)]+?)\s+(\d+\s*x\s*.+?)(?:\s*-\s*(.+))?$/);
                if (baseMatch) {
                    const base = {
                        location: baseMatch[1].trim(),
                        aircraft: baseMatch[2].trim(),
                        type: baseMatch[3] ? baseMatch[3].trim() : null
                    };
                    details.bases.push(base);
                }
            }
        });

        // If no structured bases found, look for base section
        const baseHeader = $('h3:contains("CHARTER BASES"), h4:contains("CHARTER BASES")').first();
        if (baseHeader.length) {
            let currentBase = null;
            baseHeader.nextAll().each((i, elem) => {
                const text = $(elem).text().trim();
                if (!text || $(elem).is('h3, h4') || i > 20) return false;

                // Base name (usually bold or separate line)
                if ($(elem).is('strong, b') || text.match(/^[A-Za-z\s\(\)]+$/)) {
                    currentBase = text;
                } else if (currentBase && text.match(/\d+\s*x\s*/)) {
                    details.bases.push({
                        location: currentBase,
                        aircraft: text
                    });
                }
            });
        }

        return details;
    } catch (error) {
        console.error(`Error scraping operator details from ${url}:`, error.message);
        throw error;
    }
}

/**
 * Try to find operator by brute force searching record numbers
 * This is a fallback when the main charter page doesn't list the operator
 */
async function searchByRecordRange(operatorName) {
    const normalizedSearch = normalizeCompanyName(operatorName);

    // Try a range of record numbers (Business Air News uses sequential record numbers)
    // We'll try common ranges where charter operators are typically listed
    const ranges = [
        { start: 146900, end: 147100 }, // Range where Advanced Air Charters is
        { start: 1000, end: 1200 },
        { start: 163000, end: 163500 }
    ];

    for (const range of ranges) {
        // Sample every 10th record to avoid too many requests
        for (let recnum = range.start; recnum <= range.end; recnum += 10) {
            try {
                const url = `${BASE_URL}/hb_charterpage.html?recnum=${recnum}`;
                const response = await axios.get(url, { ...axiosConfig, timeout: 3000 });
                const $ = cheerio.load(response.data);

                const companyName = $('.hb-company').first().text().trim();
                if (companyName) {
                    const normalizedCompany = normalizeCompanyName(companyName);
                    const similarity = stringSimilarity(normalizedSearch, normalizedCompany);

                    if (similarity > 0.7) {
                        console.log(`Found match: ${companyName} at ${url} (similarity: ${similarity.toFixed(2)})`);
                        return url;
                    }
                }
            } catch (err) {
                // Skip failed requests
            }
        }
    }

    return null;
}

/**
 * Main function to enrich operator data
 */
async function enrichOperatorData(operatorName) {
    try {
        console.log(`Searching for operator: ${operatorName}`);

        let url = await searchOperator(operatorName);

        // If not found, try the record range search
        if (!url) {
            console.log('Not found in main listing, trying record range search...');
            url = await searchByRecordRange(operatorName);
        }

        if (!url) {
            return {
                found: false,
                message: 'Operator not found on Business Air News'
            };
        }

        console.log(`Found operator at: ${url}`);
        const details = await scrapeOperatorDetails(url);

        return {
            found: true,
            data: details
        };
    } catch (error) {
        console.error(`Error enriching operator ${operatorName}:`, error.message);
        return {
            found: false,
            error: error.message
        };
    }
}

module.exports = {
    searchOperator,
    scrapeOperatorDetails,
    enrichOperatorData
};
