const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');
const path = require('path');

// Load cookies from file
let cookieString = '';
try {
    const cookiesPath = path.join(__dirname, 'cookies.txt');
    if (fs.existsSync(cookiesPath)) {
        cookieString = fs.readFileSync(cookiesPath, 'utf-8').trim();
        console.log('Loaded cookies from cookies.txt');
    }
} catch (error) {
    console.error('Error loading cookies:', error.message);
}

// Configure axios with cookies
const axiosConfig = {
    headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://www.businessairnews.com/',
        'Cookie': cookieString
    }
};

/**
 * Scrape operator details from Business Air News page with authentication
 */
async function scrapeOperatorDetailsAuthenticated(url) {
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

        // Extract certifications - look for list items
        $('li').each((i, elem) => {
            const text = $(elem).text().trim();

            // AOC/Part 135
            const aocMatch = text.match(/AOC\/Part 135:\s*(.+)/i);
            if (aocMatch) {
                const value = aocMatch[1].trim();
                // Skip if it's the masked dots (●●●●●●●● or HTML entities)
                if (value && !value.match(/^[●\u25cf\s]+$/) && value !== '●●●●●●●●') {
                    details.certifications.aoc_part135 = value;
                }
            }

            // Wyvern Certified (capture the actual certification level like "Registered", "Wingman", etc.)
            const wyvernMatch = text.match(/Wyvern Certified:\s*(.+)/i);
            if (wyvernMatch) {
                const value = wyvernMatch[1].trim();
                // Skip if it's the masked dots
                if (value && !value.match(/^[●\u25cf\s]+$/) && value !== '●●●●●●●●') {
                    details.certifications.wyvern_certified = value;
                }
            }

            // ARGUS Rating
            const argusMatch = text.match(/ARGUS Rating:\s*(.+)/i);
            if (argusMatch) {
                const value = argusMatch[1].trim();
                if (value && !value.match(/^[●\u25cf\s]+$/) && value !== '●●●●') {
                    details.certifications.argus_rating = value;
                }
            }

            // IS-BAO (capture stage like "II", "III", "Yes", etc.)
            const isbaoMatch = text.match(/IS-BAO:\s*(.+)/i);
            if (isbaoMatch) {
                const value = isbaoMatch[1].trim();
                // Skip if it's the masked dots
                if (value && !value.match(/^[●\u25cf\s]+$/) && value !== '●●●●') {
                    details.certifications.is_bao = value;
                }
            }

            // ACSF IAS
            const acsfMatch = text.match(/ACSF IAS:\s*(Yes|No)/i);
            if (acsfMatch) details.certifications.acsf_ias = acsfMatch[1];

            // Telephone
            const phoneMatch = text.match(/Telephone:\s*(.+)/i);
            if (phoneMatch) {
                const value = phoneMatch[1].trim();
                if (value && !value.match(/^[●\u25cf\s]+$/) && value !== '●●●●●●●●●●') {
                    details.contact.telephone = value;
                }
            }
        });

        // Extract email from mailto links
        const emailMatch = $('a[href^="mailto:"]').first();
        if (emailMatch.length) {
            const email = emailMatch.attr('href').replace('mailto:', '');
            if (email && !email.match(/^[●\u25cf\s]+$/)) {
                details.contact.email = email;
            }
        }

        // Extract website
        $('a[href^="http"]').each((i, elem) => {
            const href = $(elem).attr('href');
            if (href && !href.includes('businessairnews.com') && !href.includes('facebook.com')) {
                if (!href.match(/^[●\u25cf\s]+$/)) {
                    details.contact.website = href;
                    return false; // break
                }
            }
        });

        // Also check for "Web:" label
        const webMatch = $('body').text().match(/Web:\s*([^\s●]+)/i);
        if (webMatch && !details.contact.website) {
            const value = webMatch[1].trim();
            if (value && !value.match(/^[●\u25cf\s]+$/)) {
                details.contact.website = value;
            }
        }

        // Extract charter bases and aircraft
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

        return details;
    } catch (error) {
        console.error(`Error scraping operator details from ${url}:`, error.message);
        throw error;
    }
}

module.exports = {
    scrapeOperatorDetailsAuthenticated
};
