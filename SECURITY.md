# Security policy

PEL handles phone numbers and precise location data. Please report suspected security
or privacy issues privately through GitHub's private vulnerability reporting feature
when available, or contact the maintainer through the profile linked in this repository.

Do not open a public issue containing contact details, coordinates, SIM information,
device logs, credentials, or a working exploit. Include only the affected version,
impact, and the minimum reproduction material needed for investigation.

Before deployment, keep `config/contacts.json` outside version control, restrict its
filesystem permissions, redact logs before sharing them, and test alerts with consent.
