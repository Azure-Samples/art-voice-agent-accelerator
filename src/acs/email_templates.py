"""
Email Templates for ARTAgent
===========================

Reusable email templates that can be used by any tool.
Provides both plain text and HTML versions with consistent styling.
"""

from typing import Any


class EmailTemplates:
    """Collection of reusable email templates."""

    @staticmethod
    def get_base_html_styles() -> str:
        """Get base CSS styles for HTML emails."""
        return """
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #0078d4, #106ebe); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }
        .content { padding: 20px; background: #f9f9f9; }
        .section { background: white; margin: 15px 0; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .section h3 { color: #0078d4; margin-top: 0; border-bottom: 2px solid #0078d4; padding-bottom: 5px; }
        .info-row { display: flex; justify-content: space-between; margin: 8px 0; padding: 5px 0; border-bottom: 1px solid #eee; }
        .label { font-weight: bold; color: #555; }
        .value { color: #333; }
        .highlight { background: #fff3cd; padding: 3px 6px; border-radius: 3px; }
        .footer { background: #333; color: white; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; }
        .next-steps { background: #e8f4fd; border-left: 4px solid #0078d4; }
        """

    @staticmethod
    def create_claim_confirmation_email(
        claim_data: dict[str, Any], claim_id: str, caller_name: str
    ) -> tuple[str, str, str]:
        """
        Create claim confirmation email content.

        Returns:
            Tuple of (subject, plain_text_body, html_body)
        """
        vehicle_details = claim_data.get("vehicle_details", {})
        loss_location = claim_data.get("loss_location", {})
        injury_assessment = claim_data.get("injury_assessment", {})

        subject = f"Claim Confirmation - {claim_id}"

        # Plain text version
        plain_text_body = f"""Dear {caller_name},

Your First Notice of Loss (FNOL) claim has been successfully recorded and assigned the following reference number:

CLAIM ID: {claim_id}

═══════════════════════════════════════════════════════════════════
CLAIM SUMMARY
═══════════════════════════════════════════════════════════════════

Date Reported: {claim_data.get('date_reported', 'N/A')}
Loss Date: {claim_data.get('loss_date', 'N/A')} at {claim_data.get('loss_time', 'N/A')}

VEHICLE INFORMATION:
• Vehicle: {vehicle_details.get('make', 'N/A')} {vehicle_details.get('model', 'N/A')} ({vehicle_details.get('year', 'N/A')})
• Policy ID: {vehicle_details.get('policy_id', 'N/A')}
• Vehicle Condition: {'Drivable' if claim_data.get('vehicle_drivable') else 'Not Drivable'}

INCIDENT DETAILS:
• Description: {claim_data.get('incident_description', 'N/A')}
• Vehicles Involved: {claim_data.get('number_of_vehicles_involved', 'N/A')}
• Trip Purpose: {claim_data.get('trip_purpose', 'N/A')}

LOCATION:
• Address: {loss_location.get('street', 'N/A')}
• City/State: {loss_location.get('city', 'N/A')}, {loss_location.get('state', 'N/A')} {loss_location.get('zipcode', 'N/A')}

INJURY ASSESSMENT:
• Injuries Reported: {'Yes' if injury_assessment.get('injured') else 'No'}
• Details: {injury_assessment.get('details', 'None reported')}

DRIVER INFORMATION:
• Driver Name: {claim_data.get('driver_name', 'N/A')}
• Relationship to Policyholder: {claim_data.get('driver_relationship', 'N/A')}

═══════════════════════════════════════════════════════════════════
NEXT STEPS
═══════════════════════════════════════════════════════════════════

1. A claims adjuster will contact you within 24-48 hours
2. Please keep this claim number for all future communications: {claim_id}
3. If you need immediate assistance, please call our 24/7 claims hotline

Thank you for choosing ARTVoice Insurance. We're here to help you through this process.

Best regards,
ARTVoice Insurance Claims Department"""

        # HTML version
        vehicle_condition_class = " highlight" if not claim_data.get("vehicle_drivable") else ""
        vehicle_condition_text = (
            "Drivable" if claim_data.get("vehicle_drivable") else "Not Drivable"
        )
        injury_class = " highlight" if injury_assessment.get("injured") else ""
        injury_text = "Yes" if injury_assessment.get("injured") else "No"
        injury_details_row = (
            f'<div class="info-row"><span class="label">Details:</span><span class="value">{injury_assessment.get("details", "None reported")}</span></div>'
            if injury_assessment.get("details")
            else ""
        )

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>{EmailTemplates.get_base_html_styles()}</style>
</head>
<body>
    <div class="header">
        <h1>🛡️ Claim Confirmation</h1>
        <div class="claim-id" style="font-size: 24px; font-weight: bold; background: rgba(255,255,255,0.2); padding: 10px; border-radius: 5px; margin: 10px 0;">CLAIM ID: {claim_id}</div>
        <p>Your First Notice of Loss has been successfully recorded</p>
    </div>
    
    <div class="content">
        <p>Dear <strong>{caller_name}</strong>,</p>
        <p>Thank you for reporting your claim. We have successfully recorded all the details and assigned your claim the reference number above.</p>
        
        <div class="section">
            <h3>📋 Claim Information</h3>
            <div class="info-row">
                <span class="label">Date Reported:</span>
                <span class="value">{claim_data.get('date_reported', 'N/A')}</span>
            </div>
            <div class="info-row">
                <span class="label">Loss Date & Time:</span>
                <span class="value">{claim_data.get('loss_date', 'N/A')} at {claim_data.get('loss_time', 'N/A')}</span>
            </div>
        </div>
        
        <div class="section">
            <h3>🚗 Vehicle Information</h3>
            <div class="info-row">
                <span class="label">Vehicle:</span>
                <span class="value">{vehicle_details.get('make', 'N/A')} {vehicle_details.get('model', 'N/A')} ({vehicle_details.get('year', 'N/A')})</span>
            </div>
            <div class="info-row">
                <span class="label">Policy ID:</span>
                <span class="value">{vehicle_details.get('policy_id', 'N/A')}</span>
            </div>
            <div class="info-row">
                <span class="label">Vehicle Condition:</span>
                <span class="value{vehicle_condition_class}">{vehicle_condition_text}</span>
            </div>
        </div>
        
        <div class="section">
            <h3>📍 Incident Details</h3>
            <div class="info-row">
                <span class="label">Description:</span>
                <span class="value">{claim_data.get('incident_description', 'N/A')}</span>
            </div>
            <div class="info-row">
                <span class="label">Vehicles Involved:</span>
                <span class="value">{claim_data.get('number_of_vehicles_involved', 'N/A')}</span>
            </div>
            <div class="info-row">
                <span class="label">Location:</span>
                <span class="value">{loss_location.get('street', 'N/A')}, {loss_location.get('city', 'N/A')}, {loss_location.get('state', 'N/A')} {loss_location.get('zipcode', 'N/A')}</span>
            </div>
        </div>
        
        <div class="section">
            <h3>🏥 Injury Assessment</h3>
            <div class="info-row">
                <span class="label">Injuries Reported:</span>
                <span class="value{injury_class}">{injury_text}</span>
            </div>
            {injury_details_row}
        </div>
        
        <div class="section next-steps">
            <h3>🎯 Next Steps</h3>
            <ol>
                <li><strong>Claims Adjuster Contact:</strong> You will be contacted within 24-48 hours</li>
                <li><strong>Reference Number:</strong> Please save this claim ID: <span class="highlight">{claim_id}</span></li>
                <li><strong>24/7 Support:</strong> Contact our claims hotline for immediate assistance</li>
            </ol>
        </div>
    </div>
    
    <div class="footer">
        <p><strong>ARTVoice Insurance Claims Department</strong></p>
        <p>We're here to help you through this process</p>
    </div>
</body>
</html>"""

        return subject, plain_text_body, html_body

    @staticmethod
    def create_policy_notification_email(
        customer_name: str, policy_id: str, notification_type: str, details: dict[str, Any]
    ) -> tuple[str, str, str]:
        """
        Create policy notification email content.

        Args:
            customer_name: Name of the customer
            policy_id: Policy ID
            notification_type: Type of notification (renewal, update, etc.)
            details: Additional details for the notification

        Returns:
            Tuple of (subject, plain_text_body, html_body)
        """
        subject = f"Policy {notification_type.title()} - {policy_id}"

        plain_text_body = f"""Dear {customer_name},

This is to notify you about your policy {policy_id}.

Notification Type: {notification_type.title()}

Details:
{chr(10).join([f"• {k}: {v}" for k, v in details.items()])}

If you have any questions, please contact our customer service team.

Best regards,
ARTVoice Insurance Customer Service"""

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>{EmailTemplates.get_base_html_styles()}</style>
</head>
<body>
    <div class="header">
        <h1>📋 Policy {notification_type.title()}</h1>
        <p>Policy ID: {policy_id}</p>
    </div>
    
    <div class="content">
        <p>Dear <strong>{customer_name}</strong>,</p>
        <p>This is to notify you about your policy <strong>{policy_id}</strong>.</p>
        
        <div class="section">
            <h3>📄 Notification Details</h3>
            {''.join([f'<div class="info-row"><span class="label">{k}:</span><span class="value">{v}</span></div>' for k, v in details.items()])}
        </div>
    </div>
    
    <div class="footer">
        <p><strong>ARTVoice Insurance Customer Service</strong></p>
        <p>We're here to help you</p>
    </div>
</body>
</html>"""

        return subject, plain_text_body, html_body

    @staticmethod
    def create_mfa_code_email(
        otp_code: str,
        client_name: str,
        institution_name: str,
        transaction_amount: float = 0,
        transaction_type: str = "general_inquiry",
    ) -> tuple[str, str, str]:
        """
        Create context-aware MFA verification code email for financial services.

        Args:
            otp_code: 6-digit verification code
            client_name: Name of the client
            institution_name: Financial institution name
            transaction_amount: Amount (used only for context, not displayed)
            transaction_type: Type of transaction or operation

        Returns:
            Tuple of (subject, plain_text_body, html_body)
        """
        # Get user-friendly call context
        call_reason = _get_call_context(transaction_type)

        subject = "Financial Services - Verification Code Required"

        # Plain text version (no transaction details)
        plain_text_body = f"""Dear {client_name},

Thank you for contacting Financial Services regarding {call_reason}.

Your verification code is: {otp_code}

This code expires in 5 minutes. Our specialist will ask for this code during your call to securely verify your identity before we can assist with your {call_reason.lower()}.

If you did not initiate this call, please contact us immediately.

Best regards,
Financial Services Team
Institution: {institution_name}
"""

        # HTML version (context-aware, no transaction details)
        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        {EmailTemplates.get_base_html_styles()}
        .verification-code {{
            background: linear-gradient(135deg, #0066cc, #004499);
            color: white;
            padding: 20px;
            text-align: center;
            margin: 20px 0;
            border-radius: 12px;
            font-size: 32px;
            font-weight: bold;
            letter-spacing: 8px;
            box-shadow: 0 4px 8px rgba(0,102,204,0.3);
        }}
        .call-context {{
            background: #f8f9fa;
            border-left: 4px solid #0066cc;
            padding: 15px;
            margin: 20px 0;
            border-radius: 8px;
        }}
    </style>
</head>
<body>
    <div class="header" style="background: linear-gradient(135deg, #0066cc, #004499);">
        <h1>🏛️ Financial Services</h1>
        <h2>Identity Verification Required</h2>
    </div>
    
    <div class="content">
        <p>Dear <strong>{client_name}</strong>,</p>
        
        <p>Thank you for contacting Financial Services regarding <strong>{call_reason}</strong>.</p>
        
        <div class="verification-code">
            {otp_code}
            <div style="color: #666; font-size: 14px; margin-top: 10px;">This code expires in 5 minutes</div>
        </div>
        
        <div class="call-context">
            <h4>� What happens next?</h4>
            <p>Our specialist will ask you for this code during your call to securely verify your identity before we can assist with your {call_reason.lower()}.</p>
        </div>
        
        <p><em>If you did not initiate this call, please contact us immediately.</em></p>
    </div>
    
    <div class="footer">
        <p><strong>Financial Services - Your Trusted Partner</strong></p>
        <p style="font-size: 12px; margin: 5px 0;">Institution: {institution_name}</p>
    </div>
</body>
</html>"""

        return subject, plain_text_body, html_body


def _get_call_context(transaction_type: str) -> str:
    """Map transaction types to actual call reasons that users understand."""
    call_reasons = {
        "account_inquiry": "account questions and information",
        "balance_check": "account balance and holdings review",
        "transaction_history": "transaction history and statements",
        "small_transfers": "transfer and payment requests",
        "medium_transfers": "transfer and payment requests",
        "large_transfers": "large transfer authorization",
        "liquidations": "investment liquidation and fund access",
        "large_liquidations": "large liquidation requests",
        "portfolio_rebalancing": "portfolio management and rebalancing",
        "account_modifications": "account updates and modifications",
        "fund_operations": "fund management operations",
        "institutional_transfers": "institutional transfer services",
        "drip_liquidation": "dividend reinvestment plan (DRIP) liquidation",
        "large_drip_liquidation": "large DRIP liquidation requests",
        "institutional_servicing": "institutional client services",
        "fraud_reporting": "fraud reporting and security concerns",
        "dispute_transaction": "transaction disputes and investigations",
        "fraud_investigation": "fraud investigation assistance",
        "general_inquiry": "general account and service inquiries",
        "emergency_liquidations": "emergency liquidation services",
        "regulatory_overrides": "regulatory compliance matters",
    }

    return call_reasons.get(transaction_type, "financial services assistance")


class FraudEmailTemplates:
    """Professional fraud case email templates matching MFA style."""

    @staticmethod
    def create_fraud_case_email(
        case_number: str,
        client_name: str,
        institution_name: str,
        email_type: str = "case_created",
        blocked_card_last_4: str = None,
        estimated_loss: float = 0,
        provisional_credits: list[dict] = None,
        additional_details: str = "",
    ) -> tuple[str, str, str]:
        """
        Create professional fraud case notification email.

        Args:
            case_number: Fraud case ID
            client_name: Name of the client
            institution_name: Financial institution name
            email_type: Type of email (case_created, card_blocked, etc.)
            blocked_card_last_4: Last 4 digits of blocked card
            estimated_loss: Total estimated loss amount
            provisional_credits: List of provisional credit transactions
            additional_details: Additional information to include

        Returns:
            Tuple of (subject, plain_text_body, html_body)
        """
        from datetime import datetime

        # Email subjects by type
        subject_map = {
            "case_created": f"🛡️ Fraud Protection Activated - Case {case_number}",
            "card_blocked": "🔒 Card Security Alert - Immediate Protection",
            "investigation_update": f"📋 Fraud Investigation Update - Case {case_number}",
            "resolution": f"✅ Fraud Case Resolved - Case {case_number}",
        }

        subject = subject_map.get(email_type, f"Security Notification - Case {case_number}")

        # Calculate total provisional credits
        total_credits = sum(credit.get("amount", 0) for credit in (provisional_credits or []))

        # Plain text version
        plain_text_body = f"""Dear {client_name},

FRAUD PROTECTION CONFIRMATION
Case Number: {case_number}
Institution: {institution_name}
Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

IMMEDIATE ACTIONS TAKEN:
✓ Card ending in {blocked_card_last_4 or 'XXXX'} has been BLOCKED
✓ Fraud case opened with high priority investigation team
✓ Replacement card expedited for 1-2 business day delivery
✓ Enhanced account monitoring activated
✓ Provisional credits being processed: ${total_credits:.2f}

NEXT STEPS:
• Investigation team will contact you within 24 hours
• New card will arrive with tracking information via SMS/Email  
• Update automatic payments with new card when received
• Monitor account for any additional suspicious activity

REPLACEMENT CARD DETAILS:
• Shipping: Expedited (1-2 business days)
• Tracking: Provided via SMS and email
• Activation: Required upon receipt

TEMPORARY ACCESS:
• Mobile wallet (Apple Pay, Google Pay) remains active if set up
• Online banking and bill pay available
• Branch visits with valid ID for emergency cash

IMPORTANT: Always reference case number {case_number} in communications.

24/7 Fraud Hotline: 1-800-555-FRAUD

{additional_details}

We sincerely apologize for this inconvenience and appreciate your prompt reporting. Your security is our highest priority.

Best regards,
Fraud Protection Team
{institution_name}
"""

        # Beautiful HTML version
        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        {EmailTemplates.get_base_html_styles()}
        .fraud-alert {{
            background: linear-gradient(135deg, #dc3545, #c82333);
            color: white;
            padding: 20px;
            text-align: center;
            margin: 20px 0;
            border-radius: 12px;
            box-shadow: 0 4px 8px rgba(220,53,69,0.3);
        }}
        .case-number {{
            background: #f8f9fa;
            border: 2px solid #0066cc;
            padding: 15px;
            text-align: center;
            margin: 20px 0;
            border-radius: 8px;
            font-size: 18px;
            font-weight: bold;
            color: #0066cc;
        }}
        .actions-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .action-item {{
            background: #d4edda;
            border-left: 4px solid #28a745;
            padding: 15px;
            border-radius: 8px;
        }}
        .action-item h4 {{
            margin: 0 0 5px 0;
            color: #155724;
        }}
        .credits-section {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 8px;
        }}
        .next-steps {{
            background: #f8f9fa;
            border-left: 4px solid #6c757d;
            padding: 15px;
            margin: 20px 0;
            border-radius: 8px;
        }}
        .contact-info {{
            background: linear-gradient(135deg, #0066cc, #004499);
            color: white;
            padding: 20px;
            text-align: center;
            margin: 20px 0;
            border-radius: 12px;
        }}
        .hotline {{
            font-size: 24px;
            font-weight: bold;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <div class="header" style="background: linear-gradient(135deg, #dc3545, #c82333);">
        <h1>🛡️ Fraud Protection Activated</h1>
        <h2>Your Account is Now Secure</h2>
    </div>
    
    <div class="content">
        <div class="fraud-alert">
            <h2>🚨 IMMEDIATE PROTECTION MEASURES ACTIVATED 🚨</h2>
            <p>We've taken swift action to protect your account from unauthorized activity.</p>
        </div>
        
        <p>Dear <strong>{client_name}</strong>,</p>
        
        <p>This email confirms the comprehensive fraud protection measures we've implemented on your account today.</p>
        
        <div class="case-number">
            <div>📋 Your Fraud Case Number</div>
            <div style="font-size: 24px; margin-top: 10px;">{case_number}</div>
            <div style="font-size: 14px; color: #666; margin-top: 5px;">Reference this number in all communications</div>
        </div>
        
        <h3>🚀 IMMEDIATE ACTIONS COMPLETED</h3>
        <div class="actions-grid">
            <div class="action-item">
                <h4>🔒 Card Secured</h4>
                <p>Card ending in {blocked_card_last_4 or 'XXXX'} blocked immediately</p>
            </div>
            <div class="action-item">
                <h4>📦 Replacement Ordered</h4>
                <p>Expedited delivery (1-2 business days)</p>
            </div>
            <div class="action-item">
                <h4>👥 Investigation Started</h4>
                <p>High priority fraud team assigned</p>
            </div>
            <div class="action-item">
                <h4>🔍 Monitoring Enhanced</h4>
                <p>Advanced security alerts activated</p>
            </div>
        </div>"""

        # Add provisional credits section if applicable
        if provisional_credits and total_credits > 0:
            html_body += """
        <div class="credits-section">
            <h4>💰 PROVISIONAL CREDITS PROCESSING</h4>
            <p>The following unauthorized transactions are being provisionally credited:</p>
            <ul>"""

            for credit in provisional_credits:
                merchant = credit.get("merchant", "Unknown Merchant")
                amount = credit.get("amount", 0)
                date = credit.get("date", "Recent")
                html_body += f"<li><strong>${amount:.2f}</strong> - {merchant} ({date})</li>"

            html_body += f"""
            </ul>
            <p><strong>Total Provisional Credit: ${total_credits:.2f}</strong></p>
            <p><em>These credits will appear in your account within 2-3 business days.</em></p>
        </div>"""

        # Continue with next steps
        html_body += f"""
        <div class="next-steps">
            <h4>📋 YOUR NEXT STEPS</h4>
            <ul>
                <li><strong>Investigation Contact:</strong> Our team will reach out within 24 hours</li>
                <li><strong>New Card Arrival:</strong> 1-2 business days with tracking notifications</li>
                <li><strong>Update Payments:</strong> Replace card info for automatic payments when received</li>
                <li><strong>Stay Vigilant:</strong> Monitor account for any additional suspicious activity</li>
            </ul>
        </div>
        
        <h3>💳 REPLACEMENT CARD DETAILS</h3>
        <div style="background: #e7f3ff; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <p><strong>📦 Shipping Method:</strong> Expedited (1-2 business days)<br>
            <strong>📱 Tracking:</strong> SMS and email notifications provided<br>
            <strong>🔑 Activation:</strong> Required upon receipt<br>
            <strong>🏠 Delivery:</strong> Your address on file</p>
        </div>
        
        <h3>🔓 TEMPORARY ACCESS OPTIONS</h3>
        <div style="background: #f0f8f0; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <p>While waiting for your new card:</p>
            <ul>
                <li><strong>📱 Mobile Wallet:</strong> Apple Pay, Google Pay remain active if set up</li>
                <li><strong>💻 Online Banking:</strong> Full access to account and bill pay</li>
                <li><strong>🏛️ Branch Access:</strong> Visit with valid ID for emergency cash</li>
                <li><strong>📞 Phone Support:</strong> 24/7 customer service available</li>
            </ul>
        </div>
        
        <div class="contact-info">
            <h3>🆘 24/7 FRAUD PROTECTION HOTLINE</h3>
            <div class="hotline">📞 1-800-555-FRAUD</div>
            <p>Always reference case number: <strong>{case_number}</strong></p>
        </div>
        
        {f'<div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0;"><h4>📝 Additional Information</h4><p>{additional_details}</p></div>' if additional_details else ''}
        
        <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
        
        <p style="text-align: center; color: #666;">
            <strong>We sincerely apologize for any inconvenience and appreciate your prompt reporting.</strong><br>
            Your security is our highest priority, and we're committed to resolving this matter quickly and completely.
        </p>
        
        <div style="text-align: center; margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
            <p><strong>Best regards,</strong><br>
            Fraud Protection Team<br>
            {institution_name}</p>
        </div>
    </div>
    
    <div class="footer">
        <p><em>This email contains confidential information. If you received this in error, please delete immediately and contact us.</em></p>
        <p>© {datetime.now().year} {institution_name}. All rights reserved.</p>
    </div>
</body>
</html>"""

        return subject, plain_text_body, html_body
