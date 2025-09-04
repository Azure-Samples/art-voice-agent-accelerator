import os

"""
Azure Communication Services Phone Number Management Script
This script provides functionality to purchase and release phone numbers using Azure Communication Services.
It supports both toll-free and geographic phone numbers with configurable capabilities.
The script uses Azure Identity for authentication and can retrieve connection information from:
1. Command line arguments
2. Azure Developer CLI (azd) environment variables
Usage Examples:
Purchase a toll-free phone number:
    python acs_purchase_phone_number.py purchase --country-code US --area-code 833 --phone-number-type TOLL_FREE
Purchase a geographic phone number:
    python acs_purchase_phone_number.py purchase --country-code US --area-code 206 --phone-number-type GEOGRAPHIC
Release an existing phone number:
    python acs_purchase_phone_number.py release +18335551234
Using custom endpoint:
    python acs_purchase_phone_number.py --endpoint https://your-acs-resource.communication.azure.com purchase
Using connection string:
    python acs_purchase_phone_number.py --connection-string "endpoint=https://your-acs-resource.communication.azure.com/;accesskey=..." purchase
Requirements:
    - Azure Communication Services resource
    - Appropriate Azure permissions for phone number management
    - Azure CLI or azd CLI configured (if using environment variables)
    - azure-communication-phonenumbers and azure-identity Python packages
Environment Variables (when using azd):
    - ACS_CONNECTION_STRING: Azure Communication Services connection string
"""
import argparse
import subprocess

from azure.communication.phonenumbers import (
    PhoneNumberAssignmentType,
    PhoneNumberCapabilities,
    PhoneNumberCapabilityType,
    PhoneNumbersClient,
    PhoneNumberType,
)
from azure.identity import DefaultAzureCredential


# You can find your endpoint from your resource in the Azure portal
# Get ACS connection string from azd environment
def get_azd_env_value(key: str) -> str:
    """Retrieve environment value using azd env get-value command."""
    try:
        result = subprocess.run(
            ["azd", "env", "get-value", key], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get {key} from azd env: {e}")


def purchase_phone_number(phone_numbers_client, args):
    """Purchase a new phone number."""
    print("Azure Communication Services - Phone Numbers Purchase")
    capabilities = PhoneNumberCapabilities(
        calling=PhoneNumberCapabilityType.INBOUND_OUTBOUND,
        sms=PhoneNumberCapabilityType.NONE,
    )

    phone_type = (
        PhoneNumberType.TOLL_FREE
        if args.phone_number_type == "TOLL_FREE"
        else PhoneNumberType.GEOGRAPHIC
    )

    search_poller = phone_numbers_client.begin_search_available_phone_numbers(
        args.country_code,
        phone_type,
        PhoneNumberAssignmentType.APPLICATION,
        capabilities,
        area_code=args.area_code,
        polling=True,
    )
    search_result = search_poller.result()
    print("Search id: " + search_result.search_id)
    phone_number_list = search_result.phone_numbers
    print("Reserved phone numbers:")
    for phone_number in phone_number_list:
        print(phone_number)

    purchase_poller = phone_numbers_client.begin_purchase_phone_numbers(
        search_result.search_id, polling=True
    )
    purchase_poller.result()
    print("The status of the purchase operation was: " + purchase_poller.status())


def release_phone_number(phone_numbers_client, phone_number):
    """Release an existing phone number."""
    print(f"Azure Communication Services - Releasing Phone Number: {phone_number}")
    release_poller = phone_numbers_client.begin_release_phone_number(phone_number)
    release_poller.result()
    print("Status of the operation: " + release_poller.status())


def main():
    parser = argparse.ArgumentParser(
        description="Manage Azure Communication Services phone numbers"
    )
    parser.add_argument("--endpoint", help="ACS endpoint URL")
    parser.add_argument("--connection-string", help="ACS connection string")

    # Add subcommands for purchase and release
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # Purchase subcommand
    purchase_parser = subparsers.add_parser(
        "purchase", help="Purchase a new phone number"
    )
    purchase_parser.add_argument(
        "--country-code", default="US", help="Country code (default: US)"
    )
    purchase_parser.add_argument(
        "--area-code", default="833", help="Area code (default: 833)"
    )
    purchase_parser.add_argument(
        "--phone-number-type",
        choices=["TOLL_FREE", "GEOGRAPHIC"],
        default="TOLL_FREE",
        help="Phone number type (default: TOLL_FREE)",
    )

    # Release subcommand
    release_parser = subparsers.add_parser(
        "release", help="Release an existing phone number"
    )
    release_parser.add_argument(
        "phone_number", help="Phone number to release (e.g., +18001234567)"
    )

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return

    # Get endpoint - prioritize command line argument, then connection string, then azd env
    endpoint = args.endpoint
    if not endpoint:
        if args.connection_string:
            connection_string = args.connection_string
        else:
            connection_string = get_azd_env_value("ACS_CONNECTION_STRING")
        # Parse endpoint from connection string
        endpoint = connection_string.split(";")[0].replace("endpoint=", "")

    try:
        credential = DefaultAzureCredential()
        phone_numbers_client = PhoneNumbersClient(endpoint, credential)

        if args.action == "purchase":
            purchase_phone_number(phone_numbers_client, args)
        elif args.action == "release":
            release_phone_number(phone_numbers_client, args.phone_number)

    except Exception as ex:
        print("Exception:")
        print(ex)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"Error: {ex}")
        exit(1)
