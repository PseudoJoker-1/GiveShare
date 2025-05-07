from background_task import background
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from .models import Message
from django.db.models import Q

def count_and_send_email_notification(recipient_id, sender_id):
    User = get_user_model()  # Dynamically get the User model (e.g., CustomUser)
    
    try:
        user = User.objects.get(id=recipient_id)  # Use recipient_id for clarity
        sender = User.objects.get(id=sender_id)
    except User.DoesNotExist:
        logger.error(f"User not found for recipient_id={recipient_id} or sender_id={sender_id}")
        return  # Exit if user or sender doesn’t exist

    # Calculate the time window (last 5 minutes)
    time_threshold = timezone.now() - timedelta(minutes=5)
    
    # Count the messages from sender to the user within the last 5 minutes
    message_count = Message.objects.filter(
        chat__participants=user,
        sender=sender,
        timestamp__gte=time_threshold
    ).count()

    if message_count > 0 and user.profile.email_notifications_enabled:  # Check if email notifications are enabled
        # Prepare the email content
        subject = 'New Messages Notification'
        message = f"You have received {message_count} new message(s) from {sender.username} in the last 5 minutes."
        recipient_list = [user.email]
        try:
            send_mail(subject, message, 'no-reply@yourapp.com', recipient_list)
            logger.info(f"Email notification sent to {user.email} for {message_count} messages from {sender.username}")
        except Exception as e:
            logger.error(f"Failed to send email notification to {user.email}: {e}")
