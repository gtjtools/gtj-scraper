import { Aircraft, Operator } from '../lib/mock-data';
import { TailSearchResult, CharterOperator } from './api';

/**
 * Calculate a trust score based on available certifications
 */
function calculateTrustScore(charter_data: any): number {
  if (!charter_data || !charter_data.certifications) return 0;

  let score = 50; // Base score
  const certs = charter_data.certifications;

  // ARGUS Rating (up to +25 points)
  if (certs.argus_rating) {
    if (certs.argus_rating.toLowerCase().includes('platinum')) {
      score += 25;
    } else if (certs.argus_rating.toLowerCase().includes('gold')) {
      score += 15;
    } else if (certs.argus_rating !== 'No' && certs.argus_rating !== 'N/A') {
      score += 10;
    }
  }

  // Wyvern (up to +15 points)
  if (certs.wyvern_certified && certs.wyvern_certified !== 'No' && certs.wyvern_certified !== 'N/A') {
    if (certs.wyvern_certified.toLowerCase().includes('wingman')) {
      score += 15;
    } else {
      score += 10;
    }
  }

  // IS-BAO (up to +10 points)
  if (certs.is_bao && certs.is_bao !== 'No' && certs.is_bao !== 'N/A') {
    score += 10;
  }

  return Math.min(score, 100); // Cap at 100
}

/**
 * Extract certifications array from charter data
 */
function extractCertifications(charter_data: any): string[] {
  if (!charter_data || !charter_data.certifications) return [];

  const certs: string[] = [];
  const certData = charter_data.certifications;

  if (certData.argus_rating && certData.argus_rating !== 'No' && certData.argus_rating !== 'N/A') {
    certs.push(`ARGUS ${certData.argus_rating}`);
  }

  if (certData.wyvern_certified && certData.wyvern_certified !== 'No' && certData.wyvern_certified !== 'N/A') {
    certs.push(`Wyvern ${certData.wyvern_certified}`);
  }

  if (certData.is_bao && certData.is_bao !== 'No' && certData.is_bao !== 'N/A') {
    certs.push(`IS-BAO ${certData.is_bao}`);
  }

  if (certData.aoc_part135) {
    certs.push(`Part 135: ${certData.aoc_part135}`);
  }

  return certs;
}

/**
 * Extract base location from charter data
 */
function extractBaseLocation(charter_data: any): string {
  if (!charter_data) return 'Unknown';

  // Try to get from bases array
  if (charter_data.bases && charter_data.bases.length > 0) {
    return charter_data.bases[0].location || 'Unknown';
  }

  // Try to get from country
  if (charter_data.country) {
    return charter_data.country;
  }

  return 'Unknown';
}

/**
 * Get fleet size from charter data (count of aircraft in bases)
 */
function getFleetSize(charter_data: any): number {
  if (!charter_data || !charter_data.bases) return 0;
  return charter_data.bases.length;
}

/**
 * Convert charter operator data to Operator interface
 */
function convertToOperator(
  operatorName: string,
  charter_data: any,
  score?: number
): Operator {
  const trustScore = score || calculateTrustScore(charter_data);
  const certs = charter_data?.certifications || {};

  return {
    id: operatorName.toLowerCase().replace(/\s+/g, '-'),
    name: operatorName,
    trustScore: trustScore,
    argusRating: certs.argus_rating || 'N/A',
    wyvernRating: certs.wyvern_certified || 'N/A',
    fleetSize: getFleetSize(charter_data),
    baseLocation: extractBaseLocation(charter_data),
    certifications: extractCertifications(charter_data),
    aogIncidents: 0, // We don't have AOG data from the API yet
  };
}

/**
 * Parse aircraft make/model/series to extract manufacturer and model
 */
function parseAircraftMakeModel(makeModelString: string): { manufacturer: string; model: string; type: string } {
  if (!makeModelString) {
    return { manufacturer: 'Unknown', model: 'Unknown', type: 'Unknown' };
  }

  const parts = makeModelString.split(' ').filter(p => p);
  const manufacturer = parts[0] || 'Unknown';
  const model = parts.slice(1).join(' ') || 'Unknown';

  // Determine aircraft type based on make/model
  const makeModelLower = makeModelString.toLowerCase();
  let type = 'Unknown';

  if (makeModelLower.includes('citation') || makeModelLower.includes('phenom') || makeModelLower.includes('learjet')) {
    type = 'Light Jet';
  } else if (makeModelLower.includes('challenger') || makeModelLower.includes('hawker') || makeModelLower.includes('legacy')) {
    type = 'Midsize Jet';
  } else if (makeModelLower.includes('gulfstream') || makeModelLower.includes('global')) {
    if (makeModelLower.includes('g650') || makeModelLower.includes('global 7500')) {
      type = 'Heavy Jet';
    } else {
      type = 'Super Midsize';
    }
  } else if (makeModelLower.includes('falcon')) {
    type = 'Super Midsize';
  }

  return { manufacturer, model, type };
}

/**
 * Estimate hourly rate based on aircraft type and year
 */
function estimateHourlyRate(makeModel: string, year?: number): number {
  const makeModelLower = makeModel.toLowerCase();
  let baseRate = 3500; // Default for light jets

  // Determine base rate by aircraft type
  if (makeModelLower.includes('g650') || makeModelLower.includes('global 7500')) {
    baseRate = 10500; // Heavy jets
  } else if (makeModelLower.includes('global') || makeModelLower.includes('falcon')) {
    baseRate = 8500; // Large cabin
  } else if (makeModelLower.includes('gulfstream')) {
    baseRate = 6500; // Super midsize
  } else if (makeModelLower.includes('challenger') || makeModelLower.includes('legacy')) {
    baseRate = 5500; // Midsize
  } else if (makeModelLower.includes('citation') || makeModelLower.includes('phenom')) {
    baseRate = 3500; // Light jets
  }

  // Adjust for year (newer = more expensive)
  if (year && year >= 2020) {
    baseRate *= 1.2;
  } else if (year && year >= 2015) {
    baseRate *= 1.1;
  } else if (year && year < 2010) {
    baseRate *= 0.9;
  }

  return Math.round(baseRate);
}

/**
 * Estimate aircraft capacity based on make/model
 */
function estimateCapacity(makeModel: string): number {
  const makeModelLower = makeModel.toLowerCase();

  if (makeModelLower.includes('citation cj') || makeModelLower.includes('phenom 100')) {
    return 5;
  } else if (makeModelLower.includes('citation') || makeModelLower.includes('phenom 300') || makeModelLower.includes('learjet')) {
    return 7;
  } else if (makeModelLower.includes('challenger 350') || makeModelLower.includes('hawker')) {
    return 9;
  } else if (makeModelLower.includes('g280') || makeModelLower.includes('falcon')) {
    return 10;
  } else if (makeModelLower.includes('challenger') || makeModelLower.includes('legacy')) {
    return 12;
  } else if (makeModelLower.includes('g650') || makeModelLower.includes('global')) {
    return 14;
  }

  return 8; // Default
}

/**
 * Estimate aircraft range based on make/model
 */
function estimateRange(makeModel: string): number {
  const makeModelLower = makeModel.toLowerCase();

  if (makeModelLower.includes('g650')) {
    return 7000;
  } else if (makeModelLower.includes('global 7500')) {
    return 7700;
  } else if (makeModelLower.includes('global 5500') || makeModelLower.includes('global 6000')) {
    return 5900;
  } else if (makeModelLower.includes('g550') || makeModelLower.includes('g500')) {
    return 6750;
  } else if (makeModelLower.includes('g280')) {
    return 3600;
  } else if (makeModelLower.includes('falcon 7x')) {
    return 5950;
  } else if (makeModelLower.includes('falcon 2000')) {
    return 3350;
  } else if (makeModelLower.includes('challenger 650')) {
    return 4000;
  } else if (makeModelLower.includes('challenger 350')) {
    return 3200;
  } else if (makeModelLower.includes('citation cj3')) {
    return 2040;
  } else if (makeModelLower.includes('citation x')) {
    return 3460;
  } else if (makeModelLower.includes('phenom 300')) {
    return 2010;
  } else if (makeModelLower.includes('learjet')) {
    return 2000;
  }

  return 2500; // Default
}

/**
 * Extract year from serial number or return a default
 */
function extractYear(serialNumber?: string | number): number {
  if (!serialNumber) return 2018;

  // Convert to string first
  const serialStr = String(serialNumber);

  // Try to extract year from serial number (varies by manufacturer)
  // This is a simplified approach
  const match = serialStr.match(/(\d{4})/);
  if (match) {
    const year = parseInt(match[1]);
    if (year >= 1990 && year <= 2024) {
      return year;
    }
  }

  return 2018; // Default to a reasonable year
}

/**
 * Convert tail number search result to Aircraft array
 */
export function convertTailSearchToAircraft(searchResult: TailSearchResult): Aircraft[] {
  if (!searchResult.found || !searchResult.aircraft || searchResult.aircraft.length === 0) {
    return [];
  }

  const aircraftList: Aircraft[] = [];

  searchResult.aircraft.forEach((aircraftData, index) => {
    try {
      // Find matching operator data
      const operatorInfo = searchResult.operators?.find(
        op => op.operator_name === aircraftData.operator
      );

      const { manufacturer, model, type } = parseAircraftMakeModel(aircraftData.make_model);
      const year = extractYear(aircraftData.serial_number);

      // Create operator object
      const operator: Operator = operatorInfo
        ? convertToOperator(operatorInfo.operator_name, operatorInfo.charter_data, operatorInfo.score)
        : {
            id: aircraftData.operator.toLowerCase().replace(/\s+/g, '-'),
            name: aircraftData.operator,
            trustScore: 0,
            argusRating: 'N/A',
            wyvernRating: 'N/A',
            fleetSize: 0,
            baseLocation: aircraftData.faa_district || 'Unknown',
            certifications: [`Part 135: ${aircraftData.certificate_designator}`],
            aogIncidents: 0,
          };

      const aircraft: Aircraft = {
        id: `${aircraftData.registration}-${index}`,
        tailNumber: String(aircraftData.registration),
        type: type,
        manufacturer: manufacturer,
        model: model,
        year: year,
        capacity: estimateCapacity(aircraftData.make_model),
        range: estimateRange(aircraftData.make_model),
        operator: operator,
        hourlyRate: estimateHourlyRate(aircraftData.make_model, year),
        availability: operator.trustScore > 0 ? 'available' : 'limited',
        category: type,
        amenities: determineAmenities(type),
        aogIncidents: [],
        tripReports: [],
      };

      aircraftList.push(aircraft);
    } catch (error) {
      console.error('Error converting aircraft:', error, aircraftData);
    }
  });

  return aircraftList;
}

/**
 * Determine amenities based on aircraft type
 */
function determineAmenities(type: string): string[] {
  const baseAmenities = ['WiFi', 'Refreshments', 'Leather Seats'];

  if (type === 'Midsize Jet') {
    return [...baseAmenities, 'Entertainment System', 'Full Galley', 'Lavatory'];
  } else if (type === 'Super Midsize') {
    return [...baseAmenities, 'Entertainment System', 'Full Galley', 'Enclosed Lavatory', 'Satellite Phone'];
  } else if (type === 'Heavy Jet') {
    return [...baseAmenities, 'Entertainment System', 'Full Galley', 'Enclosed Lavatory', 'Satellite Phone', 'Bedroom', 'Conference Seating'];
  }

  return baseAmenities; // Light jets
}

/**
 * Convert charter operator search results to Aircraft array
 * This is used when searching by operator name
 */
export function convertCharterOperatorToAircraft(operators: CharterOperator[]): Aircraft[] {
  const aircraftList: Aircraft[] = [];

  operators.forEach(charterOp => {
    // If we don't have detailed data with bases, skip this operator
    if (!charterOp.data || !charterOp.data.bases || charterOp.data.bases.length === 0) {
      console.log(`Skipping ${charterOp.company} - no aircraft data available`);
      return;
    }

    const operator = convertToOperator(
      charterOp.company,
      charterOp.data,
      charterOp.score
    );

    // Convert each base (which represents an aircraft) to an Aircraft object
    charterOp.data.bases.forEach((base, index) => {
      const { manufacturer, model, type } = parseAircraftMakeModel(base.aircraft);

      const aircraft: Aircraft = {
        id: `${charterOp.company}-${index}`,
        tailNumber: 'Unknown', // We don't have tail numbers in charter data
        type: type,
        manufacturer: manufacturer,
        model: model,
        year: 2018, // Default year since we don't have it
        capacity: estimateCapacity(base.aircraft),
        range: estimateRange(base.aircraft),
        operator: operator,
        hourlyRate: estimateHourlyRate(base.aircraft),
        availability: operator.trustScore > 70 ? 'available' : 'limited',
        category: type,
        amenities: determineAmenities(type),
        aogIncidents: [],
        tripReports: [],
      };

      aircraftList.push(aircraft);
    });
  });

  return aircraftList;
}
