# VPN configs

This directory is a mount point for freshly generated Amnezia `.vpn` files.

Real `.vpn` files contain private client credentials. Never commit them to Git.
The bot reads files from this directory and sends each file only to the recipient
configured in `recipients.yml`.
