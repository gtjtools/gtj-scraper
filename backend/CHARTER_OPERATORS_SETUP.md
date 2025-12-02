# Charter Operators Supabase Setup Guide

This guide will help you complete the setup for the charter operators endpoint using Supabase.

## 📋 What's Been Done

✅ Created Supabase adapter (`src/common/supabase.py`)
✅ Created charter operator schemas (`src/operator/charter_schemas.py`)
✅ Created charter operator service (`src/operator/charter_service.py`)
✅ Added charter operator endpoints to router (`src/operator/router.py`)
✅ Updated frontend service to use backend API (`frontend/src/services/operator.service.ts`)

## 🔧 Setup Steps

### 1. Add Environment Variables

Add the following to your `.env` file in the backend directory:

```bash
# Supabase Configuration
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_or_service_key
```

**Where to find these:**
- Go to your Supabase project dashboard
- Navigate to Settings → API
- Copy the Project URL (SUPABASE_URL)
- Copy the anon/public key or service_role key (SUPABASE_KEY)

### 2. Create the Database Table

Run the following SQL in your Supabase SQL Editor to create the `charter_operators` table:

```sql
-- Create charter_operators table in the gtj schema
CREATE TABLE IF NOT EXISTS gtj.charter_operators (
    charter_operator_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company VARCHAR(255) NOT NULL,
    locations JSONB NOT NULL DEFAULT '[]'::jsonb,
    url VARCHAR(512),
    part135_cert VARCHAR(100),
    score INTEGER DEFAULT 0,
    faa_data JSONB,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_charter_operators_company ON gtj.charter_operators(company);
CREATE INDEX IF NOT EXISTS idx_charter_operators_score ON gtj.charter_operators(score DESC);
CREATE INDEX IF NOT EXISTS idx_charter_operators_locations ON gtj.charter_operators USING GIN(locations);
CREATE INDEX IF NOT EXISTS idx_charter_operators_data ON gtj.charter_operators USING GIN(data);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION gtj.update_charter_operators_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_charter_operators_updated_at
    BEFORE UPDATE ON gtj.charter_operators
    FOR EACH ROW
    EXECUTE FUNCTION gtj.update_charter_operators_updated_at();

-- Add comment to table
COMMENT ON TABLE gtj.charter_operators IS 'Charter operator companies with certifications and scores';
```

### 3. Migrate Data from JSON to Supabase (Optional)

If you have existing data in `charter-companies.json` or `charter-operators-enriched.json`, you can migrate it to Supabase.

Create a migration script:

```python
# scripts/migrate_charter_data.py
import json
import sys
sys.path.insert(0, '/home/marc/projects/weyobe/gotrustjet/gtj-scraper/backend')

from src.common.supabase import get_supabase_client

def migrate_charter_data():
    """Migrate charter operators from JSON to Supabase"""

    # Load JSON data
    with open('/home/marc/projects/weyobe/gotrustjet/gtj-scraper/frontend/public/charter-companies.json', 'r') as f:
        charter_data = json.load(f)

    supabase = get_supabase_client()

    # Batch insert
    batch_size = 100
    for i in range(0, len(charter_data), batch_size):
        batch = charter_data[i:i+batch_size]

        # Transform data to match schema
        records = []
        for item in batch:
            record = {
                'company': item.get('company'),
                'locations': item.get('locations', []),
                'url': item.get('url'),
                'part135_cert': item.get('part135_cert'),
                'score': item.get('score', 0),
                'faa_data': item.get('faa_data'),
                'data': item.get('data')
            }
            records.append(record)

        # Insert batch
        try:
            supabase.table('charter_operators').insert(records).execute()
            print(f"Inserted batch {i//batch_size + 1} ({len(records)} records)")
        except Exception as e:
            print(f"Error inserting batch: {e}")

    print(f"✅ Migration complete! Total records: {len(charter_data)}")

if __name__ == "__main__":
    migrate_charter_data()
```

Run the migration:
```bash
cd /home/marc/projects/weyobe/gotrustjet/gtj-scraper/backend
python scripts/migrate_charter_data.py
```

### 4. Update Frontend API URL

Make sure your frontend is pointing to the backend API. In `frontend/src/lib/env.ts`:

```typescript
export const env: Env = {
  SUPABASE_URL: getEnvVar('SUPABASE_URL'),
  SUPABASE_ANON_KEY: getEnvVar('SUPABASE_ANON_KEY'),
  API_URL: getOptionalEnvVar('API_URL') || 'http://localhost:8000', // Backend API
};
```

### 5. Start the Backend Server

```bash
cd /home/marc/projects/weyobe/gotrustjet/gtj-scraper/backend
uvicorn src.main:app --reload --port 8000
```

## 📡 Available Endpoints

### GET `/charter/operators`
Get all charter operators with pagination and search

**Query Parameters:**
- `skip` (int): Number of records to skip (default: 0)
- `limit` (int): Max records to return (default: 100)
- `search` (string): Search query for company name or locations

**Response:**
```json
{
  "total": 1234,
  "data": [
    {
      "charter_operator_id": "uuid",
      "company": "Example Aviation",
      "locations": ["New York", "Los Angeles"],
      "url": "https://...",
      "part135_cert": "ABC123",
      "score": 250,
      "faa_data": {},
      "data": {
        "certifications": {
          "argus_rating": "Platinum",
          "wyvern_certified": "Yes"
        }
      },
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### GET `/charter/operators/{id}`
Get a single charter operator by ID

### POST `/charter/operators`
Create a new charter operator

### PUT `/charter/operators/{id}`
Update a charter operator

### DELETE `/charter/operators/{id}`
Delete a charter operator

### GET `/charter/filter`
Filter charter operators by certification and score

**Query Parameters:**
- `cert` (string): Certification type (argus, wyvern, is-bao)
- `minScore` (int): Minimum score threshold

## 🧪 Testing

Test the endpoint:

```bash
# Get all charter operators
curl http://localhost:8000/charter/operators

# Search for operators
curl "http://localhost:8000/charter/operators?search=aviation"

# Filter by certification
curl "http://localhost:8000/charter/filter?cert=argus&minScore=200"
```

## 🎉 Next Steps

1. Add the environment variables to `.env`
2. Create the database table in Supabase
3. Optionally migrate existing data
4. Start the backend server
5. Test the endpoints
6. Update frontend to point to backend API URL (port 8000 instead of 3001)

## 📝 Notes

- The Supabase client library is already in `requirements.txt`
- The frontend has been updated to use the new endpoint structure
- All endpoints are documented with OpenAPI/Swagger
- Access the API docs at `http://localhost:8000/docs` when server is running
