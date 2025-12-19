"""
Banking Email Templates for Credit Card Onboarding

Provides email generation for:
- Cardholder Agreement (with e-signature link and MFA code)
- Card Approval Confirmation (with delivery info and digital wallet instructions)
"""

from typing import Any, Dict
from datetime import datetime, timedelta

# Import centralized constants (local import)
from .constants import (
    INSTITUTION_CONFIG,
    CARD_DELIVERY_TIMEFRAME,
    CARD_DELIVERY_DAYS_MAX,
)


class BankingEmailTemplates:
    """Email templates for banking operations (credit cards, accounts, etc.)."""
    
    @staticmethod
    def get_base_html_styles() -> str:
        """Return base HTML styles for banking emails (matching existing EmailTemplates style)."""
        return """
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f5f5; margin: 0; padding: 0; }
        .container { max-width: 600px; margin: 20px auto; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { background: linear-gradient(135deg, #012169, #0078d4); color: white; padding: 30px; text-align: center; }
        .header h1 { margin: 0; font-size: 28px; }
        .header p { margin: 10px 0 0 0; font-size: 14px; opacity: 0.9; }
        .content { padding: 30px; }
        .section { margin-bottom: 25px; }
        .section h3 { color: #012169; margin-top: 0; }
        .label { font-weight: bold; color: #666; }
        .value { color: #333; }
        .next-steps { background: #e8f4fd; padding: 15px; border-left: 4px solid #0078d4; border-radius: 4px; }
        .footer { background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; }
        """
    
    @staticmethod
    def create_card_agreement_email(
        customer_name: str,
        email: str,
        card_data: Dict[str, Any],
        verification_code: str,
        institution_name: str = None
    ) -> tuple[str, str, str]:
        """
        Create cardholder agreement email with e-signature link.
        
        Args:
            customer_name: Full customer name
            email: Customer email address
            card_data: Dict with card_name, annual_fee, apr, rewards_rate, highlights, etc.
            verification_code: 6-digit MFA code for e-signature verification
            institution_name: Bank name (defaults to INSTITUTION_CONFIG.name)
            
        Returns:
            Tuple of (subject, plain_text_body, html_body)
        """
        # Use institution name from constants if not provided
        if institution_name is None:
            institution_name = INSTITUTION_CONFIG.name
        
        card_name = card_data.get("card_name", "Credit Card")
        annual_fee = card_data.get("annual_fee", 0)
        regular_apr = card_data.get("regular_apr", "19.24% - 29.24% variable")
        intro_apr = card_data.get("intro_apr", "")
        rewards_rate = card_data.get("rewards_rate", "")
        foreign_fee = card_data.get("foreign_transaction_fee", 0)
        highlights = card_data.get("highlights", [])
        
        subject = f"Cardholder Agreement - {card_name} | Action Required"
        
        # Build institution URL safely
        institution_url = institution_name.lower().replace(' ', '')
        
        # Plain text version
        plain_text_body = f"""Hi {customer_name},

Your {card_name} is ready to activate. Review and sign below.

YOUR CARD:
• {card_name}
• ${annual_fee} annual fee
• {regular_apr}"""
        
        if intro_apr:
            plain_text_body += f"\n• Intro APR: {intro_apr}"
        if rewards_rate:
            plain_text_body += f"\n• Rewards: {rewards_rate}"
            
        plain_text_body += f"""
• Foreign Transaction Fee: {foreign_fee}%

KEY BENEFITS:
"""
        for benefit in highlights[:5]:
            plain_text_body += f"  ✓ {benefit}\n"
        
        plain_text_body += f"""

TO ACTIVATE:
1. Enter code: {verification_code}
2. Review terms (2 min)
3. Sign

LINK: https://secure.{institution_url}.com/esign/{verification_code}
(Expires in 24 hours)

Questions? 1-800-XXX-XXXX

{institution_name} Credit Cards"""

        # Build benefits list for HTML
        benefits_html = ""
        for benefit in highlights[:6]:
            benefits_html += f"<li>✓ {benefit}</li>"
        
        # Build intro APR row conditionally
        intro_apr_row = ""
        if intro_apr:
            intro_apr_row = f'<div class="detail-row"><span class="label">Intro APR:</span><span class="value">{intro_apr}</span></div>'
        
        # Build rewards row conditionally
        rewards_row = ""
        if rewards_rate:
            rewards_row = f'<div class="detail-row"><span class="label">Rewards:</span><span class="value">{rewards_rate}</span></div>'
        
        # HTML version
        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        {BankingEmailTemplates.get_base_html_styles()}
        .cta-button {{ background: linear-gradient(135deg, #0078d4, #106ebe); color: white; padding: 15px 30px; 
                       text-decoration: none; border-radius: 25px; display: inline-block; font-weight: bold; 
                       margin: 20px 0; box-shadow: 0 4px 8px rgba(0,120,212,0.3); }}
        .cta-button:hover {{ background: linear-gradient(135deg, #106ebe, #0078d4); }}
        .verification-code {{ background: #fff3cd; font-size: 24px; font-weight: bold; letter-spacing: 3px; 
                             padding: 15px; text-align: center; border-radius: 8px; border: 2px dashed #ff8c00; 
                             margin: 20px 0; }}
        .benefits-list {{ background: #e8f4fd; padding: 15px; border-radius: 8px; }}
        .benefits-list li {{ margin: 8px 0; color: #333; list-style: none; }}
        .card-details {{ background: white; border-left: 4px solid #0078d4; padding: 15px; margin: 20px 0; }}
        .card-details .detail-row {{ display: flex; justify-content: space-between; padding: 8px 0; 
                                     border-bottom: 1px solid #eee; }}
        .timeline {{ display: flex; justify-content: space-around; margin: 20px 0; text-align: center; }}
        .timeline-step {{ flex: 1; padding: 10px; }}
        .timeline-number {{ background: #0078d4; color: white; border-radius: 50%; width: 30px; height: 30px; 
                            display: inline-flex; align-items: center; justify-content: center; margin-bottom: 10px; }}
    </style>
</head>
<body>
        <div class="container">
            <div class="header">
                <h1>Ready to Activate</h1>
                <p>Your {card_name} • 2 minutes to complete</p>
            </div>
            
            <div class="content">
                <div class="section">
                    <p>Hi <strong>{customer_name}</strong>,</p>
                    <p>Your application is <span style="color: #28a745; font-weight: bold;">pre-approved</span>. 
                    Review the terms and sign to activate.</p>
                </div>            <div class="section card-details">
                <h3>📇 Card Details</h3>
                <div class="detail-row">
                    <span class="label">Card:</span>
                    <span class="value"><strong>{card_name}</strong></span>
                </div>
                <div class="detail-row">
                    <span class="label">Annual Fee:</span>
                    <span class="value">${annual_fee}</span>
                </div>
                <div class="detail-row">
                    <span class="label">Regular APR:</span>
                    <span class="value">{regular_apr}</span>
                </div>
                {intro_apr_row}
                {rewards_row}
                <div class="detail-row">
                    <span class="label">Foreign Transaction Fee:</span>
                    <span class="value">{foreign_fee}%</span>
                </div>
            </div>
            
            <div class="section benefits-list">
                <h3>✨ Key Benefits</h3>
                <ul style="padding-left: 0;">
                    {benefits_html}
                </ul>
            </div>
            
                <div class="section">
                    <h3>Quick Steps</h3>
                    
                    <div class="timeline">
                        <div class="timeline-step">
                            <div class="timeline-number">1</div>
                            <p><strong>Enter Code</strong></p>
                        </div>
                        <div class="timeline-step">
                            <div class="timeline-number">2</div>
                            <p><strong>Review</strong></p>
                        </div>
                        <div class="timeline-step">
                            <div class="timeline-number">3</div>
                            <p><strong>Sign</strong></p>
                        </div>
                    </div>                    
                    <div class="verification-code">
                        <p style="margin: 0; font-size: 14px; color: #666; text-transform: uppercase; letter-spacing: 1px;">Your Code</p>
                        {verification_code}
                    </div>
                    
                    <div style="text-align: center;">
                        <a href="https://secure.{institution_url}.com/esign/{verification_code}" 
                           class="cta-button">
                            Review & Sign
                        </a>
                        <p style="color: #666; font-size: 12px;">Expires in 24 hours</p>
                    </div>
                </div>            <div class="section next-steps">
                <h3>📋 What Happens Next?</h3>
                <ol style="line-height: 2;">
                    <li><strong>Review and sign</strong> the agreement (takes 5 minutes)</li>
                    <li><strong>Instant approval</strong> confirmation</li>
                    <li><strong>Digital card available</strong> immediately in mobile wallet</li>
                    <li><strong>Physical card arrives</strong> in 5-7 business days</li>
                </ol>
            </div>
            
            <div class="section" style="background: #f8f9fa; padding: 15px; border-radius: 4px;">
                <p style="text-align: center; margin: 0;">
                    <strong>Questions?</strong> Call us at <a href="tel:1-800-XXX-XXXX">1-800-XXX-XXXX</a> 
                    or reply to this email.
                </p>
            </div>
        </div>
        
        <div class="footer">
            <p><strong>Thank you for choosing {institution_name}!</strong></p>
            <p style="font-size: 12px;">This is an automated message. Please do not reply directly to this email.</p>
            <p>© {datetime.now().year} {institution_name}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>"""

        return subject, plain_text_body, html_body
    
    @staticmethod
    def create_card_approval_email(
        customer_name: str,
        email: str,
        card_details: Dict[str, Any],
        institution_name: str = None
    ) -> tuple[str, str, str]:
        """
        Create card approval confirmation email with delivery info.
        
        Args:
            customer_name: Full customer name
            email: Customer email address
            card_details: Dict with card_name, card_number_last4, credit_limit, activation_date, 
                         physical_card_delivery, digital_wallet_ready
            institution_name: Bank name (defaults to INSTITUTION_CONFIG.name)
            
        Returns:
            Tuple of (subject, plain_text_body, html_body)
        """
        # Use institution name from constants if not provided
        if institution_name is None:
            institution_name = INSTITUTION_CONFIG.name
        
        card_name = card_details.get("card_name", "Credit Card")
        last4 = card_details.get("card_number_last4", "XXXX")
        credit_limit = card_details.get("credit_limit", 5000)
        delivery_timeframe = card_details.get("physical_card_delivery", CARD_DELIVERY_TIMEFRAME)
        digital_wallet_ready = card_details.get("digital_wallet_ready", True)
        
        delivery_date = (datetime.now() + timedelta(days=CARD_DELIVERY_DAYS_MAX)).strftime("%B %d, %Y")
        
        subject = f"🎉 Approved! Your {card_name} is on its way"
        
        # Plain text version
        plain_text_body = f"""Dear {customer_name},

🎉 CONGRATULATIONS! Your application has been approved!

═══════════════════════════════════════════════════════════════════
YOUR NEW CARD
═══════════════════════════════════════════════════════════════════

Card: {institution_name} {card_name}
Last 4 Digits: {last4}
Credit Limit: ${credit_limit:,}

═══════════════════════════════════════════════════════════════════
DELIVERY INFORMATION
═══════════════════════════════════════════════════════════════════

Your physical card will arrive in: {delivery_timeframe}

Expected Delivery: {delivery_date}

═══════════════════════════════════════════════════════════════════
NEXT STEPS
═══════════════════════════════════════════════════════════════════

"""
        
        if digital_wallet_ready:
            plain_text_body += "\n\nADD TO WALLET NOW:\nApple Wallet | Google Pay\n"
        
        plain_text_body += f"""\nACTIVATE WHEN IT ARRIVES:\n• Call or use the app\n• Set your PIN at any ATM\n\nQuestions? 1-800-XXX-XXXX\n\n{institution_name}"""

        # HTML version
        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        {BankingEmailTemplates.get_base_html_styles()}
        .celebration-header {{ background: linear-gradient(135deg, #28a745, #20c997); }}
        .card-visual {{ background: linear-gradient(135deg, #012169, #0078d4); color: white; 
                       padding: 20px; border-radius: 12px; margin: 20px 0; 
                       box-shadow: 0 4px 12px rgba(1,33,105,0.3); }}
        .card-visual h2 {{ margin: 0; font-size: 18px; }}
        .card-visual .card-number {{ font-size: 24px; letter-spacing: 3px; margin: 15px 0; }}
        .card-visual .card-info {{ display: flex; justify-content: space-between; font-size: 14px; }}
        .checklist {{ background: #e8f4fd; padding: 15px; border-radius: 8px; }}
        .checklist li {{ margin: 10px 0; color: #333; }}
        .action-buttons {{ text-align: center; margin: 20px 0; }}
        .action-button {{ background: #0078d4; color: white; padding: 12px 24px; text-decoration: none; 
                          border-radius: 20px; display: inline-block; margin: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header celebration-header">
            <h1>🎉 Congratulations!</h1>
            <p>Your Credit Card Application Has Been Approved</p>
        </div>
        
        <div class="content">
            <div class="section">
                <p>Dear <strong>{customer_name}</strong>,</p>
                <p>We're excited to inform you that your <strong>{institution_name} {card_name}</strong> 
                application has been <span style="color: #28a745; font-weight: bold;">approved</span>!</p>
            </div>
            
            <div class="section card-visual">
                <h2>{institution_name}</h2>
                <div class="card-number">•••• •••• •••• {last4}</div>
                <div class="card-info">
                    <span><strong>Credit Limit</strong><br>${credit_limit:,}</span>
                </div>
            </div>
            
            <div class="section">
                <h3>📦 Delivery Information</h3>
                <p><strong>Your card will arrive in:</strong> {delivery_timeframe}</p>
                <p><strong>Expected Delivery:</strong> {delivery_date}</p>
            </div>
            
            <div class="section checklist">
                <h3>✅ Next Steps</h3>
                <ul>"""
        
        if digital_wallet_ready:
            html_body += """
                    <li>✓ <strong>Add to Digital Wallet</strong> - Available now for immediate use</li>"""
        
        html_body += f"""
                    <li>✓ <strong>Activate Your Card</strong> - When it arrives, follow activation instructions</li>
                    <li>✓ <strong>Set Up Autopay</strong> - Never miss a payment</li>
                    <li>✓ <strong>Set Your PIN</strong> - Visit any ATM to set your secure PIN</li>
                </ul>
            </div>"""
        
        if digital_wallet_ready:
            html_body += """
            
            <div class="action-buttons">
                <a href="#" class="action-button">📱 Add to Apple Wallet</a>
                <a href="#" class="action-button">📱 Add to Google Pay</a>
            </div>"""
        
        html_body += f"""
            
            <div class="section" style="background: #f8f9fa; padding: 15px; border-radius: 4px;">
                <p style="text-align: center; margin: 0;">
                    <strong>Questions?</strong> Call us at <a href="tel:1-800-XXX-XXXX">1-800-XXX-XXXX</a> 
                    or visit your account dashboard.
                </p>
            </div>
        </div>
        
        <div class="footer">
            <p><strong>Thank you for choosing {institution_name}!</strong></p>
            <p style="font-size: 12px;">This is an automated message. Please do not reply directly to this email.</p>
            <p>© {datetime.now().year} {institution_name}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>"""

        return subject, plain_text_body, html_body