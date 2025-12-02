"""
Migrate charter operators from JSON to Supabase gtj.charter_operators table
"""
import json
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from src.common.supabase import get_supabase_client


def migrate_charter_data():
    """Migrate charter operators from JSON to Supabase"""

    # Path to JSON file
    json_path = backend_dir.parent / 'frontend' / 'public' / 'charter-companies.json'

    if not json_path.exists():
        print(f"❌ JSON file not found: {json_path}")
        return

    print(f"📂 Loading data from: {json_path}")

    # Load JSON data
    with open(json_path, 'r') as f:
        charter_data = json.load(f)

    print(f"📊 Found {len(charter_data)} charter operators to migrate")

    supabase = get_supabase_client()

    # Check if table exists and is accessible
    try:
        test_query = supabase.schema('gtj').table('charter_operators').select('charter_operator_id').limit(1).execute()
        print("✅ Table gtj.charter_operators is accessible")
    except Exception as e:
        print(f"❌ Error accessing table: {e}")
        print("\n💡 Make sure you've run create_charter_operators_table.sql in Supabase SQL Editor first!")
        return

    # Batch insert
    batch_size = 100
    total_inserted = 0
    errors = []

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
            response = supabase.schema('gtj').table('charter_operators').insert(records).execute()
            inserted_count = len(response.data)
            total_inserted += inserted_count
            print(f"✅ Batch {i//batch_size + 1}: Inserted {inserted_count} records ({total_inserted}/{len(charter_data)})")
        except Exception as e:
            error_msg = f"Batch {i//batch_size + 1}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")

    print(f"\n{'='*60}")
    print(f"✅ Migration complete!")
    print(f"   Total records processed: {len(charter_data)}")
    print(f"   Successfully inserted: {total_inserted}")
    print(f"   Errors: {len(errors)}")

    if errors:
        print(f"\n❌ Errors encountered:")
        for error in errors:
            print(f"   - {error}")
    else:
        print(f"\n🎉 All data migrated successfully!")


if __name__ == "__main__":
    try:
        migrate_charter_data()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
