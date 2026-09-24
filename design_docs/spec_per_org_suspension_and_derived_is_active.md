# Per-Org Suspension & Derived `is_active`

How user status and organization membership work.

---

## 1. Premise — the two tables and what their columns mean

A person is modelled in two places:

**`users`** — the *account*. One row per person, independent of any organization.

- **`status`** — the account's lifecycle. Exactly one of **`pending`**, **`active`**, **`rejected`**.
  - `pending` — signed up, waiting for approval.
  - `active` — approved; the person can authenticate.
  - `rejected` — signup was refused.
  - The database enforces these three values; nothing else can be stored.
- **`is_active`** — a convenience boolean the frontend reads. It is **derived by the database** as "the account is `active`". The application never writes it — it is always exactly `status = 'active'`, so it can never disagree with the lifecycle. It answers one question only: *can this account sign in at all?*

**`user_organizations`** — the *membership*. One row per (person, organization) pair. This is where a person's relationship with a specific organization lives.

- **`status`** — the membership's state in that one organization. Exactly one of **`active`** or **`suspended`** (database-enforced).
  - `active` — the person can operate in that organization.
  - `suspended` — the person is blocked in that organization only.
- **`role`** — the person's role *in that organization*.

The key idea: **the account says whether you can log in; each membership says what you can do inside a given organization.** Suspension is a property of a membership, never of the account.

---

## 2. Core principles

- **Suspension is per-organization.** Suspending someone in Organization A does not touch their access to Organization B. There is no account-wide ban.
- **`is_active` is derived, never set.** The database computes it from `status`, so it is always exactly "the account is active" and cannot disagree with the lifecycle.
- **Membership status is checked on every request**, not just at login — so a suspension takes effect immediately, including for tokens already issued.

---

## 3. How it behaves

**Signing in**

- Login is account-level: any linked method authenticates the one account.
- The account must be `active` to sign in at all.
- After authenticating, the person lands in an organization where their membership is `active`.
- Preference: their primary organization if active there, otherwise any other active membership.
- Active nowhere → login refused with a clear message.
- Suspended in their usual org but active elsewhere → still logs in, lands in the allowed org.

**Acting inside an organization**

- Every tenant operation checks the caller's membership status in that organization.
- Suspended membership → request denied (403), even with a previously valid token.
- Applies to both ordinary organization endpoints and platform (superadmin) endpoints.

**Seeing and switching organizations**

- Suspension in one org does not lock the person out of the product.
- They can still view their list of organizations.
- They can switch into any organization where their membership is `active`.
- Switching into a suspended (or otherwise non-active) membership is refused.

**Suspending / reactivating**

- An admin acts within their own organization; it flips that one membership.
- Suspend: `active` → `suspended`. Reactivate: `suspended` → `active`.
- You cannot suspend yourself.
- The membership must currently be in the opposite state, or the action is rejected.

**Status shown in the UI**

- Listing/viewing a user in an org shows the *effective* status.
- While the account is `pending` or `rejected`, that lifecycle status wins (approvals stay visible).
- Once the account is `active`, the per-org membership status is shown (suspension is visible).

**Dev bypass**

- With auth bypass on (local development only), the synthetic developer identity skips the membership check — it has no real membership rows.

---

## 4. API behaviour at a glance

| Endpoint / area | Behaviour |
|---|---|
| Login | Succeeds only for an `active` account; lands the caller in an organization where their membership is active; refused if they're active nowhere. |
| Token refresh | Re-issues a token scoped to an organization where the membership is active; a suspended membership no longer yields usable access there. |
| Any tenant (organization-scoped) endpoint | Denied (403) if the caller's membership in that organization is suspended. |
| Any platform (superadmin) endpoint | Same membership check applies against the platform organization. |
| Suspend / reactivate user | Flips the target's membership status in the acting admin's organization only; cannot target yourself; guarded by the current membership state. |
| List / get users (in an org) | Returns the *effective* status: account lifecycle while pending/rejected, otherwise the per-org membership status. |
| View my organizations / switch organization | Not blocked by suspension — you can always see and switch to organizations where you're active; switching into a non-active membership is refused. |

---

## 5. Out of scope

- A platform-wide account ban (suspension is always per-organization by design).
- Moving self-signup requests out of the `users` table.
