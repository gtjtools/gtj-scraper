"""
Hatchet worker for batch verification workflow.

Run this worker in a separate terminal to process batch verification jobs:
    python -m src.workers.batch_verify_worker

Requires HATCHET_CLIENT_TOKEN environment variable.
"""

from src.hatchet_client import hatchet
from src.workflows.batch_verify_workflow import batch_verify_workflow


def main():
    worker = hatchet.worker("batch-verify-worker", workflows=[batch_verify_workflow])
    worker.start()


if __name__ == "__main__":
    main()
