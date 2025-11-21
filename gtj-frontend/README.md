# TrustJet Parse Pilot

A comprehensive flight booking platform that combines a modern React UI with FAA Part 135 operator data and Business Air News charter operator information.

## Quick Start

### Install Dependencies
```bash
npm install
```

### Run Development Server (Frontend + Backend)
```bash
npm run dev
```

This starts:
- **Frontend**: http://localhost:5173 (React + Vite)
- **Backend**: http://localhost:3000 (Express API)

### Run Separately

**Backend only:**
```bash
npm run dev:server
```

**Frontend only:**
```bash
npm run dev:client
```

## Features

### Current Functionality
- ✅ Search aircraft by tail number
- ✅ Search by airport (departure/arrival)
- ✅ Search by operator
- ✅ View operator certifications (ARGUS, Wyvern, IS-BAO)
- ✅ Operator trust scores
- ✅ FAA Part 135 data integration
- ✅ Business Air News charter operator data
- ✅ Real-time operator lookup

### Flight Booking Interface
- Create and send quotes to clients
- Multi-aircraft quote comparison
- Quote management (drafts, sent, accepted, declined)
- Track flights and aircraft
- AOG (Aircraft on Ground) incident tracking
- TripScore generation
- Client management
- Financial dashboard

### Data Sources
- **FAA Part 135 Operators** (`Part_135_Operators.xlsx`)
- **Charter Operator Database** (`charter-operators-enriched.json`)
- **Business Air News** (live scraping)

## API Endpoints

### Search by Tail Number
```
GET /api/search/tail/:tailNumber
```
Returns operator info, certifications, and aircraft details.

### Charter Operators
```
GET /api/charter/operators
```
Returns all charter operators with scores and certifications.

### Filter Operators
```
GET /api/charter/filter?cert=argus-platinum&minScore=150
```
Filter operators by certification and trust score.

### Part 135 Search
```
GET /api/search?q=Miami
```
Search Part 135 operators by any field.

## Project Structure

```
trustjet-parse-pilot/
├── src/                          # React frontend
│   ├── components/              # UI components
│   ├── lib/                     # Data types and utilities
│   ├── services/                # API integration
│   │   │   └── api.ts              # Backend API client
│   ├── pages/                   # Page components
│   ├── Dashboard.tsx            # Main dashboard component
│   └── main.tsx                 # Entry point
├── public/                       # Legacy HTML interface
├── server.js                     # Express backend
├── scraper.js                    # Data scraping utilities
├── Part_135_Operators.xlsx      # FAA data
├── charter-operators-enriched.json  # Enriched operator data
├── vite.config.ts               # Vite configuration
├── tailwind.config.js           # Tailwind CSS config
├── tsconfig.json                # TypeScript config
└── package.json                 # Dependencies
```

## Environment Variables

For production deployment, create a `.env` file:

```bash
NODE_ENV=production
PORT=3000
APP_PASSWORD=your_secure_password
```

In development mode, password protection is disabled.

## Building for Production

```bash
# Build frontend
npm run build

# Start production server
npm start
```

The frontend build outputs to the `build/` directory.

## Documentation

- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - Detailed integration guide
- **[QUICKSTART.md](./QUICKSTART.md)** - Quick setup guide (legacy)
- **[DEPLOYMENT.md](./DEPLOYMENT.md)** - Deployment instructions

## Data Scraping

### Scrape Charter Companies
```bash
node scrape-alphabet.js
```

### Enrich with Certifications
```bash
node enrich-charter-data.js
```

### Load FAA Operators
```bash
node load-air-operators.js
```

## Tech Stack

### Frontend
- React 18
- TypeScript
- Vite
- Tailwind CSS
- Radix UI Components
- Lucide Icons
- Recharts (analytics)
- React Hook Form
- Sonner (toasts)

### Backend
- Node.js
- Express
- Axios (HTTP client)
- Cheerio (web scraping)
- XLSX (Excel parsing)

## Contributing

This is a private project. For questions or issues, contact the development team.

## License

Proprietary - All rights reserved
