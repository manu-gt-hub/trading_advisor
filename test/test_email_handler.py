import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from email_handler import *


def send_trading_advices_via_email(
    trading_advices_df,
    new_buys,
    sells,
    revenue_percentage,
    email_subject,
    sender_email,
    sender_password,
    recipient_emails
):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['Subject'] = email_subject

    html_parts = ["<p>Here are the daily trading advices:</p>"]
    html_parts.append(trading_advices_df.to_html(index=False))

    if new_buys is not None and not new_buys.empty:
        html_parts.append("<br><p>The following stocks are worth buying:</p>")
        html_parts.append(new_buys.to_html(index=False))

    if sells is not None and not sells.empty:
        html_parts.append(f"<br><p>The following stocks have reached the {revenue_percentage}% target and are recommended to sell:</p>")
        html_parts.append(sells.to_html(index=False))

    full_html_body = "<br>".join(html_parts)
    msg.attach(MIMEText(full_html_body, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)

        for recipient_email in recipient_emails:
            msg['To'] = recipient_email
            server.sendmail(sender_email, recipient_email, msg.as_string())

        server.quit()
        return "✅ Email sent successfully!"
    
    except Exception as e:
        return f"❌ Failed to send email: {e}"



class TestSendTradingAdvicesEmail(unittest.TestCase):
    @patch('smtplib.SMTP')
    def test_email_sent_successfully(self, mock_smtp):
        # Prepare mock SMTP server
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        # Create sample dataframes
        trading_advices_df = pd.DataFrame({
            'Symbol': ['AAPL', 'GOOG'],
            'Advice': ['Buy', 'Sell']
        })
        new_buys = pd.DataFrame({'Symbol': ['TSLA'], 'Advice': ['Buy']})
        sells = pd.DataFrame({'Symbol': ['MSFT'], 'Advice': ['Sell']})

        result = send_trading_advices_via_email(
            trading_advices_df=trading_advices_df,
            new_buys=new_buys,
            sells=sells,
            revenue_percentage=10,
            email_subject="Daily Trading Advices",
            sender_email="sender@example.com",
            sender_password="password123",
            recipient_emails=["recipient1@example.com", "recipient2@example.com"]
        )

        # Check SMTP connection and methods called correctly
        mock_smtp.assert_called_once_with('smtp.gmail.com', 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("sender@example.com", "password123")
        self.assertEqual(mock_server.sendmail.call_count, 2)  # two recipients

        self.assertEqual(result, "✅ Email sent successfully!")

    @patch('smtplib.SMTP')
    def test_email_send_failure(self, mock_smtp):
        # Simulate exception when connecting to SMTP server
        mock_smtp.side_effect = Exception("Connection error")

        result = send_trading_advices_via_email(
            trading_advices_df=pd.DataFrame(),
            new_buys=None,
            sells=None,
            revenue_percentage=0,
            email_subject="Subject",
            sender_email="sender@example.com",
            sender_password="password123",
            recipient_emails=["recipient@example.com"]
        )

        self.assertTrue(result.startswith("❌ Failed to send email"))
