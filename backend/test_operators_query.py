#!/usr/bin/env python3
"""
Test script to query gtj.operators table directly
Run this to check what data and columns exist
"""

import sys
sys.path.insert(0, '.')

from src.common.models import Operator
from src.common.config import SessionLocal
from sqlalchemy import text

def main():
    print("🔄 Connecting to database...")
    db = SessionLocal()

    try:
        # Get operators using the Operator model
        operators = db.query(Operator).limit(5).all()

        if operators:
            print(f"\n✅ SUCCESS! Queried gtj.operators table")
            print(f"📊 Found {len(operators)} operators (showing first 5)\n")
            print("=" * 80)

            for op in operators:
                print(f"\n🏢 {op.name}")
                print(f"   ID: {op.operator_id}")
                print(f"   DBA Name: {op.dba_name}")
                print(f"   Certificate: {op.certificate_number}")
                print(f"   Base Airport: {op.base_airport}")
                print(f"   Trust Score: {op.trust_score}")
                print(f"   Status: {op.regulatory_status}")
                print(f"   Verified: {op.is_verified}")
                print(f"   Created: {op.created_at}")

                # Check for charter operator fields
                if hasattr(op, 'locations'):
                    print(f"   Locations: {op.locations}")
                if hasattr(op, 'url'):
                    print(f"   URL: {op.url}")
                if hasattr(op, 'data'):
                    print(f"   Data: {op.data}")
                if hasattr(op, 'faa_data'):
                    print(f"   FAA Data: {op.faa_data}")

            # Get total count
            total = db.query(Operator).count()
            print(f"\n📈 Total operators in table: {total}")

            # Check which columns exist
            print("\n🔍 Checking table structure...")
            result = db.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'gtj' AND table_name = 'operators'
                ORDER BY ordinal_position
            """))

            columns = result.fetchall()

            print("\n📋 All columns in gtj.operators:")
            print("-" * 80)
            for col in columns:
                print(f"  {col[0]:30} {col[1]}")

            # Check for missing charter operator fields
            existing_cols = [col[0] for col in columns]
            charter_fields = ['locations', 'url', 'faa_data', 'data']

            print("\n🎯 Charter operator field status:")
            print("-" * 80)
            missing = []
            for field in charter_fields:
                if field in existing_cols:
                    print(f"  ✅ {field}")
                else:
                    print(f"  ❌ {field} - MISSING")
                    missing.append(field)

            if missing:
                print(f"\n⚠️  Need to add columns: {', '.join(missing)}")
                print("\n💡 SQL to add missing columns:")
                print("-" * 80)
                for field in missing:
                    if field == 'locations':
                        print(f"ALTER TABLE gtj.operators ADD COLUMN {field} JSONB DEFAULT '[]'::jsonb;")
                    elif field in ['faa_data', 'data']:
                        print(f"ALTER TABLE gtj.operators ADD COLUMN {field} JSONB;")
                    else:  # url
                        print(f"ALTER TABLE gtj.operators ADD COLUMN {field} VARCHAR(512);")
            else:
                print("\n✅ All charter operator fields exist!")

        else:
            print("\n⚠️  Table is empty - no operators found")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
