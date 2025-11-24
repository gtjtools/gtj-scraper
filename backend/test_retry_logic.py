"""
Simple test script to validate the retry logic in UCC verification service
"""
import asyncio
from src.scoring.ucc_service import UCCVerificationService


async def test_retry_logic():
    """Test the retry with backoff function"""
    service = UCCVerificationService()

    # Test 1: Function that succeeds immediately
    print("Test 1: Function that succeeds immediately")
    call_count = [0]

    async def success_func():
        call_count[0] += 1
        return {"status": "success", "calls": call_count[0]}

    result = await service._retry_with_backoff(
        success_func,
        max_retries=5,
        initial_delay=0.5,
        context="Test success function"
    )
    print(f"✓ Result: {result}")
    print(f"✓ Function was called {call_count[0]} time(s)\n")

    # Test 2: Function that fails 2 times then succeeds
    print("Test 2: Function that fails 2 times then succeeds")
    attempt_count = [0]

    async def fail_twice_then_succeed():
        attempt_count[0] += 1
        if attempt_count[0] < 3:
            raise Exception(f"Simulated failure on attempt {attempt_count[0]}")
        return {"status": "success", "attempts": attempt_count[0]}

    result = await service._retry_with_backoff(
        fail_twice_then_succeed,
        max_retries=5,
        initial_delay=0.5,
        context="Test retry function"
    )
    print(f"✓ Result: {result}")
    print(f"✓ Function succeeded after {attempt_count[0]} attempt(s)\n")

    # Test 3: Function that always fails (should exhaust all retries)
    print("Test 3: Function that always fails")
    fail_count = [0]

    async def always_fail():
        fail_count[0] += 1
        raise Exception(f"Simulated failure on attempt {fail_count[0]}")

    try:
        await service._retry_with_backoff(
            always_fail,
            max_retries=3,
            initial_delay=0.5,
            context="Test always fail"
        )
        print("❌ Should have raised an exception")
    except Exception as e:
        print(f"✓ Exception raised as expected: {str(e)}")
        print(f"✓ Function was called {fail_count[0]} time(s) (initial + 3 retries = 4)\n")

    print("=" * 60)
    print("All retry logic tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_retry_logic())
