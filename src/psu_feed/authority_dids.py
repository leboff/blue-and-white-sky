"""
Authority accounts: beat reporters, official accounts, etc.
These DIDs get a fixed 2.0x multiplier so their posts rank higher.

Add entries as (DID, "Short label for maintainability").
To find a user's DID: visit their profile on Bluesky and check the URL or use a DID resolver.
"""

AUTHORITY_ACCOUNTS: list[tuple[str, str]] = [
    ("did:plc:x5ogzhccdzixduafk7za2arb", "Daniel Gallen"),
    ("did:plc:f7i33cd3b5n6en2iunk2mwkp", "Bill DiFilippo"),
    ("did:plc:rk7w4mhlnjr6paz7qjpn6fyt", "Thomas Frank Carr"),
    ("did:plc:mk6xp2py63mhfqsycqyoi56n", "Penn State Football (Official)"),
    ("did:plc:xy4gk3zyicyrohhydm76zkvi", "Roar Lions Roar"),
    ("did:plc:mrftqkimm2yrs4lqgelgxykd", "On3"),
    ("did:plc:kbrmj4uhmko7arfn7xiev4zu", "Jon Sauber"),
    # Example (replace with real DIDs and labels):
    # ("did:plc:abc123xyz", "On3 Penn State"),
    # ("did:plc:def456uvw", "247Sports PSU"),
    # ("did:plc:ghi789rst", "Daily Collegian Sports"),
]

# Set of DIDs used by the ingester (derived from the list above)
AUTHORITY_DIDS: set[str] = {did for did, _ in AUTHORITY_ACCOUNTS}
