#!/usr/bin/env python3
"""
Test Script for Email and SMS Services
=====================================

This script tests the Azure Communication Services email and SMS functionality
to ensure they work correctly before testing the full MFA flow.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.acs.email_service import EmailService
from src.acs.sms_service import SmsService
from utils.ml_logging import get_logger

logger = get_logger("test_communication_services")


async def test_email_service():
    """Test email service configuration and sending."""
    print("\n🔍 Testing Email Service...")

    email_service = EmailService()

    # Check configuration
    if not email_service.is_configured():
        print("❌ Email service not configured properly")
        print("   Missing environment variables:")
        print(
            f"   AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING: {'✅' if os.getenv('AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING') else '❌'}"
        )
        print(
            f"   AZURE_EMAIL_SENDER_ADDRESS: {'✅' if os.getenv('AZURE_EMAIL_SENDER_ADDRESS') else '❌'}"
        )
        return False

    print("✅ Email service configuration valid")

    # Test sending email (you can replace with your email for testing)
    test_email = "test@example.com"  # Replace with your email for actual testing

    try:
        result = await email_service.send_email(
            email_address=test_email,
            subject="Financial Services - Test MFA Code",
            plain_text_body="Your MFA verification code is: 123456\n\nThis is a test message from the Financial Services authentication system.",
            html_body="<p>Your MFA verification code is: <strong>123456</strong></p><p>This is a test message from the Financial Services authentication system.</p>",
        )

        if result.get("success"):
            print(f"✅ Email sent successfully to {test_email}")
            print(f"   Message ID: {result.get('message_id')}")
            return True
        else:
            print(f"❌ Email sending failed: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ Email service error: {e}")
        return False


async def test_sms_service():
    """Test SMS service configuration and sending."""
    print("\n🔍 Testing SMS Service...")

    sms_service = SmsService()

    # Check configuration
    if not sms_service.is_configured():
        print("❌ SMS service not configured properly")
        print("   Missing environment variables:")
        print(
            f"   AZURE_COMMUNICATION_SMS_CONNECTION_STRING: {'✅' if os.getenv('AZURE_COMMUNICATION_SMS_CONNECTION_STRING') else '❌'}"
        )
        print(
            f"   AZURE_SMS_FROM_PHONE_NUMBER: {'✅' if os.getenv('AZURE_SMS_FROM_PHONE_NUMBER') else '❌'}"
        )
        return False

    print("✅ SMS service configuration valid")
    print(f"   From phone number: {sms_service.from_phone_number}")

    # Test sending SMS (you can replace with your phone number for testing)
    test_phone = "+1234567890"  # Replace with your phone number for actual testing

    try:
        result = await sms_service.send_sms(
            to_phone_numbers=test_phone,
            message="Financial Services MFA Code: 123456. This is a test message.",
            tag="MFA_Test",
        )

        if result.get("success"):
            print(f"✅ SMS sent successfully to {test_phone}")
            sent_messages = result.get("sent_messages", [])
            if sent_messages:
                print(f"   Message ID: {sent_messages[0].get('message_id')}")
            return True
        else:
            print(f"❌ SMS sending failed: {result.get('error')}")
            failed_messages = result.get("failed_messages", [])
            if failed_messages:
                for msg in failed_messages:
                    print(f"   Failed to {msg.get('to')}: {msg.get('error_message')}")
            return False

    except Exception as e:
        print(f"❌ SMS service error: {e}")
        return False


async def main():
    """Run all communication service tests."""
    print("🧪 Testing Azure Communication Services for Financial MFA")
    print("=" * 60)

    # Test email service
    email_success = await test_email_service()

    # Test SMS service
    sms_success = await test_sms_service()

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    print(f"   Email Service: {'✅ PASS' if email_success else '❌ FAIL'}")
    print(f"   SMS Service:   {'✅ PASS' if sms_success else '❌ FAIL'}")

    if email_success and sms_success:
        print("\n🎉 All communication services are working correctly!")
        print("   Ready to test the complete MFA authentication flow.")
    else:
        print("\n⚠️  Some services need configuration before MFA testing.")
        print("   Please update your .env file with proper ACS credentials.")

    return email_success and sms_success


if __name__ == "__main__":
    asyncio.run(main())
