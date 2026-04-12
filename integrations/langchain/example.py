"""
Quick sanity-check — run directly without LangChain to verify API connectivity.
    python example.py
"""
from swiss_truth_tools import SwissTruthToolkit

toolkit = SwissTruthToolkit()  # no API key needed for read-only tools
search, verify, list_domains, _ = toolkit.get_tools()

print("=== Domains ===")
print(list_domains.run({}))

print("\n=== Search: 'GDPR right to erasure' ===")
print(search.run({"query": "GDPR right to erasure", "domain": "eu-law", "limit": 3}))

print("\n=== Verify: WHO founded 1948 ===")
print(verify.run({"claim_text": "The WHO was founded in 1948.", "domain": "eu-health"}))
