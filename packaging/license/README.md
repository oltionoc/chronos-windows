# Chronos licence keys

Chronos is time-limited by a signed licence. The app embeds only the **public**
key and can only **verify** a licence — it can never mint one — so a client can
never extend their own install. The **private** key that signs licences is held
by the vendor and is **not in this repository**.

## What ships in the app

- `backend/app/services/license.py` — the public key, the built-in default
  licence (beta, expires **2026-11-10**), verification (pure-Python RSA, no
  crypto dependency), and the effective-licence rule.
- The gate in `backend/app/main.py` — when the effective licence has expired,
  the user-facing API returns **402** and the frontend shows a lock screen with
  a "paste a new key" box. Login and the licence endpoints stay open, and the
  worker's ingestion path is never gated, so **punches keep being recorded
  while locked** and no attendance day is lost.

## Minting a licence (vendor only)

You need the private key file `chronos-license-key.json` (kept off-repo; a copy
was placed on the vendor's desktop at install time). Then:

    python sign_license.py --to "Client Name" --expires 2027-02-01

It prints one licence string. The client pastes it under **Settings > Licence**
(or on the lock screen once expired); it takes effect immediately, no reinstall.

Rules the app enforces:

- A pasted key must **verify** against the embedded public key, or it is rejected.
- A pasted key must not **shorten** the term below the built-in default, so a
  copy of an older key can never be used to roll the expiry backwards.

## Rotating the key

To issue from a fresh keypair, generate one, replace `_N`/`DEFAULT_LICENSE` in
`services/license.py`, and keep the new private key. Old keys stop verifying —
only do this deliberately.
