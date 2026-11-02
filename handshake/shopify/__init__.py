"""Connect a real Shopify store to Handshake.

    client.py    Shopify Admin GraphQL: products, live quotes, orders, spec writes
    catalog.py   products → agent-readable records, and the learned spec schema
    gateway.py   an agent-facing checkout in front of the store, instrumented
                 with the Handshake SDK, mounted at /shopify
"""
