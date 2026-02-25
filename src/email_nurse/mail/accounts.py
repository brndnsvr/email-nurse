"""Mail.app account detection and management.

Uses sysm CLI for account listing. AppleScript is only used for
sync_account() and sync_all_accounts() (sysm gaps).
"""

from dataclasses import dataclass

from email_nurse.mail.applescript import escape_applescript_string, run_applescript
from email_nurse.mail.sysm import get_accounts_sysm


@dataclass
class MailAccount:
    """Represents a Mail.app email account."""

    name: str
    id: str
    email_addresses: list[str]
    enabled: bool
    account_type: str


def get_accounts() -> list[MailAccount]:
    """
    Retrieve all configured email accounts from Mail.app via sysm.

    Returns:
        List of MailAccount objects representing each account.
    """
    data = get_accounts_sysm()

    accounts = []
    for acct in data:
        # sysm JSON fields may vary - map to our dataclass
        name = acct.get("name", "")
        acct_id = acct.get("id", name)

        # email addresses may be a list or comma-separated string
        emails_raw = acct.get("emailAddresses", acct.get("email", []))
        if isinstance(emails_raw, str):
            email_addresses = [e.strip() for e in emails_raw.split(",") if e.strip()]
        elif isinstance(emails_raw, list):
            email_addresses = emails_raw
        else:
            email_addresses = []

        enabled = acct.get("enabled", True)
        account_type = acct.get("accountType", acct.get("type", "unknown"))

        accounts.append(
            MailAccount(
                name=name,
                id=str(acct_id),
                email_addresses=email_addresses,
                enabled=bool(enabled),
                account_type=str(account_type),
            )
        )

    return accounts


# --- AppleScript-only operations (sysm gaps) ---


def sync_account(account_name: str) -> bool:
    """
    Trigger a sync/check for new mail on a specific account.

    Uses AppleScript (sysm has no sync trigger).

    Args:
        account_name: The name of the account to sync.

    Returns:
        True if sync was triggered successfully.
    """
    escaped_name = escape_applescript_string(account_name)
    script = f'''
    tell application "Mail"
        check for new mail for account "{escaped_name}"
    end tell
    '''

    run_applescript(script)
    return True


def sync_all_accounts() -> bool:
    """
    Trigger a sync/check for new mail on all accounts.

    Uses AppleScript (sysm has no sync trigger).

    Returns:
        True if sync was triggered successfully.
    """
    script = '''
    tell application "Mail"
        check for new mail
    end tell
    '''

    run_applescript(script)
    return True
