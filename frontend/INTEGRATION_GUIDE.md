# TrustJet Integration Guide

## Overview

This project successfully merges the flight booking UI with the FAA Part 135 operators scraping infrastructure. The application now features:

1. **React-based flight booking interface** (frontend on port 5173)
2. **Express backend** with scraped operator data (backend on port 3000)
3. **API integration layer** connecting the UI with real data

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  React Frontend                      │
│                  (Vite on :5173)                     │
│                                                       │
│  ┌──────────────────────────────────────────────┐  │
│  │  Search Components (Tail/Airport/Operator)   │  │
│  └──────────────────────────────────────────────┘  │
│                        │                             │
│                        ▼                             │
│  ┌──────────────────────────────────────────────┐  │
│  │       API Service Layer (api.ts)             │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                         │
                         │ Proxy /api/* → :3000
                         ▼
┌─────────────────────────────────────────────────────┐
│                Express Backend (:3000)               │
│                                                       │
│  ┌──────────────────────────────────────────────┐  │
│  │  API Endpoints                               │  │
│  │  - /api/search/tail/:tailNumber              │  │
│  │  - /api/charter/operators                    │  │
│  │  - /api/charter/filter                       │  │
│  │  - /api/operators                            │  │
│  └──────────────────────────────────────────────┘  │
│                        │                             │
│                        ▼                             │
│  ┌──────────────────────────────────────────────┐  │
│  │  Data Sources                                │  │
│  │  - Part_135_Operators.xlsx                   │  │
│  │  - charter-operators-enriched.json           │  │
│  │  - Business Air News scraper                 │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Key Files

### Frontend
- **`src/Dashboard.tsx`** - Main React dashboard application
- **`src/services/api.ts`** - API integration layer (NEW)
- **`src/components/SearchForm.tsx`** - Search interface for tail numbers, airports, and operators
- **`src/lib/mock-data.ts`** - Data types and mock data (ready for backend integration)

### Backend
- **`server.js`** - Express server with API endpoints
- **`scraper.js`** - Business Air News scraper
- **`Part_135_Operators.xlsx`** - FAA Part 135 data
- **`charter-operators-enriched.json`** - Pre-scraped operator data with scores

### Configuration
- **`vite.config.ts`** - Vite configuration with proxy to backend
- **`package.json`** - Merged dependencies
- **`tailwind.config.js`** - Tailwind CSS configuration
- **`tsconfig.json`** - TypeScript configuration

---

## Running the Application

### Development Mode (Both Frontend & Backend)

```bash
npm run dev
```

This runs both services concurrently:
- Frontend: http://localhost:5173
- Backend: http://localhost:3000

### Run Services Separately

**Backend only:**
```bash
npm run dev:server
```

**Frontend only:**
```bash
npm run dev:client
```

**Production:**
```bash
npm start  # Runs backend only
npm run build  # Builds frontend for production
```

---

## API Integration

### Available Endpoints

#### 1. Search by Tail Number
```typescript
import { searchByTailNumber } from './services/api';

const result = await searchByTailNumber('N123AB');
// Returns: { found, tail_number, operators[], aircraft[] }
```

#### 2. Search Charter Operators
```typescript
import { searchCharterOperators } from './services/api';

const result = await searchCharterOperators('Skyward');
// Returns: { total, data: CharterOperator[] }
```

#### 3. Filter by Certification
```typescript
import { filterCharterOperators } from './services/api';

const result = await filterCharterOperators({
  cert: 'argus-platinum',
  minScore: 150
});
// Returns operators with ARGUS Platinum and score >= 150
```

#### 4. Search Part 135 Operators
```typescript
import { searchPart135Operators } from './services/api';

const result = await searchPart135Operators('Miami');
// Returns: { total, data: Part135Operator[] }
```

---

## Next Steps for Full Integration

### 1. Update SearchForm Component

The search form currently uses mock data. To connect it to real data:

**File:** `src/components/SearchForm.tsx`

```typescript
// Replace MOCK_TAIL_NUMBERS with API call
import { searchPart135Operators } from '../services/api';

// In TailNumberInput component, replace the filter with:
const [tailNumbers, setTailNumbers] = useState<string[]>([]);

useEffect(() => {
  const fetchTailNumbers = async () => {
    const result = await searchPart135Operators();
    const numbers = result.data.map(op => op['Registration Number']);
    setTailNumbers([...new Set(numbers)]); // Unique tail numbers
  };
  fetchTailNumbers();
}, []);
```

### 2. Update Aircraft Search

**File:** `src/Dashboard.tsx`

```typescript
import { searchByTailNumber, searchCharterOperators } from './services/api';

const handleSearch = async (criteria: SearchCriteria) => {
  setSearchCriteria(criteria);

  if (criteria.searchType === 'tail' && criteria.tailNumbers) {
    // Search by tail numbers
    const results = await Promise.all(
      criteria.tailNumbers.map(tn => searchByTailNumber(tn))
    );

    // Convert backend data to Aircraft[] format
    const aircraft = convertToAircraftFormat(results);
    setSearchResults(aircraft);
  } else if (criteria.searchType === 'operator') {
    // Search charter operators
    const result = await searchCharterOperators();
    const aircraft = convertOperatorsToAircraft(result.data);
    setSearchResults(aircraft);
  }

  setHasSearched(true);
  setCurrentPage('flights');
};
```

### 3. Create Data Adapter

Create a new file to convert backend data to frontend format:

**File:** `src/services/dataAdapter.ts`

```typescript
import { Aircraft, Operator } from '../lib/mock-data';
import { CharterOperator, Part135Operator } from './api';

export function convertCharterToAircraft(charter: CharterOperator): Aircraft[] {
  // Map charter operator bases to individual aircraft
  const aircraft: Aircraft[] = [];

  charter.data?.bases?.forEach((base, index) => {
    aircraft.push({
      id: `${charter.company}-${index}`,
      tailNumber: 'N/A', // Would need to match with Part 135 data
      manufacturer: extractManufacturer(base.aircraft),
      model: base.aircraft,
      type: base.type || 'Unknown',
      capacity: estimateCapacity(base.aircraft),
      range: estimateRange(base.aircraft),
      year: 2020, // Default, would need actual data
      operator: {
        id: charter.company,
        name: charter.company,
        trustScore: charter.score || 0,
        argusRating: charter.data?.certifications?.argus_rating || 'N/A',
        wyvernRating: charter.data?.certifications?.wyvern_certified || 'N/A',
        fleetSize: charter.data?.bases?.length || 0,
        baseLocation: base.location,
        certifications: extractCertifications(charter.data?.certifications),
        aogIncidents: 0,
      },
      hourlyRate: 0, // Would need pricing data
      availability: 'available',
      category: base.type || 'Unknown',
      amenities: [],
    });
  });

  return aircraft;
}

function extractCertifications(certs: any): string[] {
  const certList: string[] = [];
  if (certs?.argus_rating && certs.argus_rating !== 'No') {
    certList.push(`ARGUS ${certs.argus_rating}`);
  }
  if (certs?.wyvern_certified && certs.wyvern_certified !== 'No') {
    certList.push(certs.wyvern_certified);
  }
  if (certs?.is_bao && certs.is_bao !== 'No') {
    certList.push(certs.is_bao);
  }
  return certList;
}
```

---

## Data Flow Example

### User searches for tail number "N123AB":

1. **User Input** → SearchForm component
2. **SearchForm** → Calls `onSearch({ searchType: 'tail', tailNumbers: ['N123AB'] })`
3. **Dashboard.tsx** → Calls `searchByTailNumber('N123AB')` from api.ts
4. **api.ts** → Makes HTTP GET to `/api/search/tail/N123AB`
5. **Vite Proxy** → Forwards to `http://localhost:3000/api/search/tail/N123AB`
6. **Express** → `server.js` handles request
7. **Server** → Searches `Part_135_Operators.xlsx` + `charter-operators-enriched.json`
8. **Response** → Returns operator data, certifications, scores
9. **api.ts** → Returns data to Dashboard.tsx
10. **Dashboard.tsx** → Converts to Aircraft[] format → Updates searchResults state
11. **UI** → Displays aircraft cards with operator details

---

## Environment Variables

Create a `.env` file for production:

```bash
NODE_ENV=production
PORT=3000
APP_PASSWORD=your_secure_password
```

---

## Building for Production

```bash
# Build frontend
npm run build

# This creates a `build/` directory with static assets
# Serve these with Express or deploy to a CDN
```

Update `server.js` to serve built React app:

```javascript
// Add this after other middleware in server.js
if (process.env.NODE_ENV === 'production') {
  app.use(express.static(path.join(__dirname, 'build')));

  app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'build', 'index.html'));
  });
}
```

---

## Testing the Integration

### Test Tail Number Search
```bash
curl http://localhost:3000/api/search/tail/N123AB
```

### Test Charter Operators
```bash
curl http://localhost:3000/api/charter/operators
```

### Test Part 135 Search
```bash
curl http://localhost:3000/api/operators
```

---

## Key Features

### ✅ Completed
- Flight booking UI with modern React/TypeScript
- Express backend with scraped FAA data
- API integration layer
- Proxy configuration for development
- Tail number search
- Charter operator search with scores
- Operator certification filtering
- Part 135 operator data access

### 🔄 Ready for Integration
- Search forms can be connected to real data
- Aircraft results can display real operator info
- Certifications and scores from scraped data
- Real-time operator lookup

### 🚀 Future Enhancements
- Real-time pricing integration
- Aircraft availability tracking
- Booking system integration
- User authentication
- Saved searches and favorites
- Email notifications for quotes
- Advanced filtering (range, capacity, amenities)
- Interactive maps for aircraft locations

---

## Troubleshooting

### Port already in use
```bash
# Kill process on port 3000
lsof -ti:3000 | xargs kill -9

# Kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

### API not responding
- Check that backend is running on port 3000
- Verify proxy configuration in `vite.config.ts`
- Check browser console for CORS errors

### Data not loading
- Ensure `Part_135_Operators.xlsx` exists in project root
- Check `charter-operators-enriched.json` exists
- Verify Express server logs for errors

---

## Contact & Support

For questions about:
- **Frontend/React**: Check `src/` directory
- **Backend/API**: Check `server.js` and `scraper.js`
- **Data**: Check `Part_135_Operators.xlsx` and JSON files

Happy coding! 🚀
