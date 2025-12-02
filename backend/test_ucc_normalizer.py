"""
Test script for UCC normalizer
Demonstrates usage with the Paris Air verification result
"""

import json
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/scoring/ucc-filings-flow'))

from ucc_normalizer import normalize_all_states, normalize_ucc_filings


def test_normalizer():
    """Test the UCC normalizer with Paris Air data"""

    # Load the verification result
    with open('/home/marc/projects/weyobe/gotrustjet/gtj-scraper/backend/data/temp/verification_result_Paris_Air_20251202_200531.json', 'r') as f:
        data = json.load(f)

    print("=" * 80)
    print("Testing UCC Normalizer")
    print("=" * 80)

    # Get UCC data
    ucc_data = data.get("ucc", {})
    visited_states = ucc_data.get("visited_states", [])

    print(f"\nFound {len(visited_states)} state(s) to normalize\n")

    # Normalize all states
    all_normalized = normalize_all_states(visited_states)

    # Display results
    for state, filings in all_normalized.items():
        print(f"\n{'=' * 80}")
        print(f"State: {state}")
        print(f"Total Filings: {len(filings)}")
        print(f"{'=' * 80}\n")

        # Group by status
        status_counts = {}
        for filing in filings:
            status = filing["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        print("Status Summary:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")

        print("\nFirst 5 filings (normalized):")
        for i, filing in enumerate(filings[:5], 1):
            print(f"\n  Filing {i}:")
            print(f"    Date: {filing['filing_date']}")
            print(f"    Status: {filing['status']}")
            print(f"    Debtor: {filing['debtor_name']}")
            print(f"    File Number: {filing['file_number']}")
            if filing.get('address'):
                print(f"    Address: {filing['address']}")

        if len(filings) > 5:
            print(f"\n  ... and {len(filings) - 5} more filings")

    # Export normalized data
    output_file = '/home/marc/projects/weyobe/gotrustjet/gtj-scraper/backend/data/temp/normalized_ucc_filings.json'
    with open(output_file, 'w') as f:
        json.dump(all_normalized, f, indent=2)

    print(f"\n{'=' * 80}")
    print(f"✓ Normalized data exported to: {output_file}")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    test_normalizer()
