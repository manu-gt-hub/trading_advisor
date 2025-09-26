import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
    """
    Sends a trading advice report via email in HTML format, including:
    - Main trading dataframe
    - New recommended buys
    - Suggested sells (if target % is reached)
    """

    # Create base email message
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['Subject'] = email_subject

    # Start building the HTML body
    html_parts = ["<p>Here are the daily trading advices:</p>"]
    html_parts.append(trading_advices_df.to_html(index=False))

    # If there are new buy suggestions, add them
    if new_buys is not None and not new_buys.empty:
        html_parts.append("<br><p>The following stocks are worth buying:</p>")
        html_parts.append(new_buys.to_html(index=False))

    # If there are sell signals, add them
    if sells is not None and not sells.empty:
        html_parts.append(f"<br><p>The following stocks have reached the {revenue_percentage}% target and are recommended to sell:</p>")
        html_parts.append(sells.to_html(index=False))

    # Combine all HTML parts and attach to the email
    full_html_body = "<br>".join(html_parts)
    msg.attach(MIMEText(full_html_body, 'html'))

    try:
        # Connect to Gmail SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)

        # Send the email to each recipient
        for recipient_email in recipient_emails:
            msg['To'] = recipient_email
            server.sendmail(sender_email, recipient_email, msg.as_string())

        server.quit()
        return "✅ Email sent successfully!"
    
    except Exception as e:
        return f"❌ Failed to send email: {e}"
