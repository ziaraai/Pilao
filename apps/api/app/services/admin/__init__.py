"""Platform administration (back-office): access, sign-in, audit log and supervision.

These services run on an *unscoped* session: they see every company. Supervision only reads
(see ``core.admin_deps.read_only``); the access and sign-in services write platform tables.
"""
