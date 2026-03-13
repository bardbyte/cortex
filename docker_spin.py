import logging
import subprocess
import sys
from pathlib import Path

from scripts.load_lookml_to_pgvector import LookMLParser, PostgresOperations
from scripts.setup_optimized_age_schema import (
    create_graph,
    create_property_indexes,
    verify_hybrid_tables,
)

logger = logging.getLogger(__name__)


class DockerManager:
    def __init__(self):
        self.compose_service = ["pgage", "ageviewer"]

    def run_cmd(self, cmd: list[str]) -> None:
        logger.info("Running command: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("Command failed (code=%d): %s", result.returncode, result.stderr.strip())
        return result.stdout.strip()

    def container_services_exists(self):
        cmd = ["docker", "compose", "ps", "--services"]
        existing_services = self.run_cmd(cmd).splitlines()
        return set(self.compose_service).issubset(set(existing_services))

    def running_services_running(self):
        cmd = ["docker", "compose", "ps", "--services", "--filter", "status=running"]
        running_services = self.run_cmd(cmd).splitlines()
        return set(self.compose_service).issubset(set(running_services))

    # def start_container(self, name):
    #     print(f"Starting container: {name}")
    #     subprocess.run(["docker", "start", name], check=True)

    def start_with_compose(self):
        logger.info("Starting docker-compose services")
        subprocess.run(["docker-compose", "up", "-d"], check=True)

    def ensure_services(self):
        print("\nChecking docker services...\n")

        if not self.container_services_exists():
            print("Services not found. Starting containers with docker-compose...")
            self.start_with_compose()
        elif not self.running_services_running():
            print("Services exist but not running. Starting with docker-compose...")
            self.start_with_compose()
        else:
            print("All services are already running.")

    def main_setup_orchestration(self):
        """Main setup orchestration."""
        print("=" * 60)
        print("PostgreSQL AGE Optimized Schema Setup")
        print("=" * 60)

        try:
            # Step 1: Create graph
            create_graph()

            # Step 2: Create property indexes
            create_property_indexes()

            # Step 3: Create hybrid tables
            from scripts.setup_optimized_age_schema import create_hybrid_tables
            create_hybrid_tables()

            # Step 4: Verify
            from scripts.setup_optimized_age_schema import verify_setup
            verify_setup()

            # Step 5: Print next steps
            from scripts.setup_optimized_age_schema import print_next_steps
            print_next_steps()

        except Exception as e:
            print(f"\nSetup failed: {e}")
            print("\nTroubleshooting:")
            print("  - Ensure PostgreSQL is running")
            print("  - Check connection with: python examples/verify_setup.py")
            sys.exit(1)


if __name__ == "__main__":
    manager = DockerManager()
    manager.ensure_services()
    manager.main_setup_orchestration()
