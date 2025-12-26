"""Mail.app account detection and management."""

from dataclasses import dataclass

from email_nurse.mail.applescript import run_applescript

# ASCII control characters for parsing AppleScript output
# These are virtually never found in account names, preventing parse errors
RECORD_SEP = "\x1e"  # ASCII 30 - Record Separator
UNIT_SEP = "\x1f"  # ASCII 31 - Unit Separator


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
    Retrieve all configured email accounts from Mail.app.

    Returns:
        List of MailAccount objects representing each account.
    """
    script = '''
    tell application "Mail"
        set output to ""
        repeat with acct in accounts
            set acctName to name of acct
            set acctId to id of acct
            set acctEmails to email addresses of acct
            set acctEnabled to enabled of acct
            set acctType to account type of acct as string
            set emailList to ""
            repeat with addr in acctEmails
                if emailList is not "" then set emailList to emailList & ","
                set emailList to emailList & addr
            end repeat
            -- Use ASCII control chars (RS=30, US=31) as delimiters to avoid collisions
            set RS to (ASCII character 30)
            set US to (ASCII character 31)
            if output is not "" then set output to output & RS
            set output to output & acctName & US & acctId & US & emailList & US & acctEnabled & US & acctType
        end repeat
        return output
    end tell
    '''

    result = run_applescript(script)
    if not result:
        return []

    accounts = []
    for account_str in result.split(RECORD_SEP):
        parts = account_str.split(UNIT_SEP)
        if len(parts) >= 5:
            accounts.append(
                MailAccount(
                    name=parts[0],
                    id=parts[1],
                    email_addresses=parts[2].split(",") if parts[2] else [],
                    enabled=parts[3].lower() == "true",
                    account_type=parts[4],
                )
            )

    return accounts


def sync_account(account_name: str) -> bool:
    """
    Trigger a sync/check for new mail on a specific account.

    Args:
        account_name: The name of the account to sync.

    Returns:
        True if sync was triggered successfully.
    """
    from email_nurse.mail.applescript import escape_applescript_string

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
