#!/usr/bin/env python3
"""
Get the PostHog project API key from a local instance.
Usage: python scripts/get_localhost_api_key.py [--host HOST] [--email EMAIL] [--password PASSWORD]
"""
import argparse
import sys
import requests


def get_api_key(
    host: str = "http://localhost:8010",
    email: str = "test@posthog.com",
    password: str = "12345678"
) -> str:
    """Get the project API key by logging in and checking the API."""
    session = requests.Session()

    # Login
    login_data = {
        "email": email,
        "password": password
    }

    try:
        response = session.post(f"{host}/api/login", json=login_data)

        if response.status_code != 200:
            raise Exception(f"Login failed: {response.status_code}")

        # Get current project info
        response = session.get(f"{host}/api/projects/@current")

        if response.status_code != 200:
            raise Exception(f"Failed to get project: {response.status_code}")

        project_data = response.json()
        api_token = project_data.get("api_token")

        if not api_token:
            raise Exception("api_token not found in project data")

        return api_token

    except requests.exceptions.ConnectionError:
        raise Exception(f"Could not connect to {host}. Is PostHog running?")
    except Exception as e:
        raise Exception(f"Error getting API key: {e}")


def main():
    parser = argparse.ArgumentParser(description="Get PostHog API key from localhost")
    parser.add_argument("--host", default="http://localhost:8010", help="PostHog host URL")
    parser.add_argument("--email", default="test@posthog.com", help="Login email")
    parser.add_argument("--password", default="12345678", help="Login password")
    parser.add_argument("--quiet", "-q", action="store_true", help="Only output the API key")

    args = parser.parse_args()

    try:
        api_key = get_api_key(args.host, args.email, args.password)
        if args.quiet:
            print(api_key)
        else:
            print(f"API Key: {api_key}")
        return 0
    except Exception as e:
        if not args.quiet:
            print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
