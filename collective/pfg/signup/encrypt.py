"""
Make tkt auth from Plone Session available to PlominoUtils.
"""
import time
import base64
from plone.session import tktauth


def encode(secret_key, email):
    """
    Encode email with secret key and current timestamp
    Return url safe string
    """
    timestamp = time.time()
    ticket = tktauth.createTicket(secret_key, email, timestamp=timestamp)
    urlsafe_string = base64.urlsafe_b64encode(ticket)
    return urlsafe_string


def decode(secret_key, urlsafe_string, timeout):
    """
    Decode the url safe string and validate with secret key and timeout
    Return tuple of email address and true if it is validate
    """
    now = time.time()
    try:
        ticket = base64.urlsafe_b64decode(urlsafe_string)
        (digest, email, tokens, user_data, timestamp) = tktauth.splitTicket(
            ticket)
        is_validate = tktauth.validateTicket(secret_key, ticket,
                                             timeout=timeout, now=now)
    except (ValueError, TypeError) as e:
        email = None
        is_validate = None
    return email, is_validate is not None
