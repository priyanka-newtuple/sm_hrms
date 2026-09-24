# Connectors and the outbound SSRF guard — internal IP allowlist

**Ticket:** FT-0210 · **Branch:** `feat/FT-0210` · **Status:** implemented, in review

Why a self-hosted deployment could not call its own co-located backend, and what
replaced the on/off switch that was first proposed.

---

## 1. What a connector is

A **connector** is a reusable, organization-scoped outbound HTTP call, stored as
configuration rather than written as code. An admin describes an external API once — URL,
method, auth, body shape, how to read the response — and the platform can then invoke it
from several places without anyone touching Python.

Defined in `connectors/`, following the standard module layering
(`controller.py` → `manager.py` → `db_models.py`).

### What is stored

`ConnectorContract` ([connectors/models/interface.py](../backend/connectors/models/interface.py))
is the immutable view of a stored connector. The fields that matter here:

| Field | Purpose |
|---|---|
| `base_url`, `path`, `method` | Where and how to call. **Supplied by the tenant.** |
| `headers`, `query_params` | Static request metadata |
| `content_type`, `body_template` | `application/json`, form, or raw; body with placeholders |
| `auth_type`, `auth_config` | `none`, `api_key`, `bearer`, `basic`, `custom` |
| `secret_hints` | Masked display only — the contract **never** carries a raw secret |
| `response_mapping` | Entity field → dotted path in the response JSON |
| `success_when` | Optional success rule beyond the default 2xx |
| `expose_as_tool` | Whether an AI agent may call it |
| `entity_types` | Which entity types the connector is bound to |

Secrets live encrypted and are decrypted only at call time
(`db_model_service.get_decrypted_secrets`), used, and never returned to the caller.

Placeholders are filled at call time in two styles: `{{field}}` from caller-supplied input,
and `$entity.field` from the bound record.

### How it is invoked

Everything funnels through one function, `run_connector_call`
([connectors/manager.py:343](../backend/connectors/manager.py#L343)), which builds, guards,
sends and interprets the call. Five paths reach it:

| # | Path | Entry point |
|---|---|---|
| 1 | Test a saved connector | `POST /v1/api/connectors/{id}/test` |
| 2 | Test an unsaved draft | `POST /v1/api/connectors/test-inline` |
| 3 | Run against a record | `run_for_entity` |
| 4 | AI agent tool | [tools/manager.py:2040](../backend/tools/manager.py#L2040) |
| 5 | `webhook.http` workflow action | [executor/executors/http_webhook.py:74](../backend/executor/executors/http_webhook.py#L74) |

Paths 1–4 run in the `modular-backend` container; path 5 runs in `modular-worker`. Both
load the same `backend/etc/.env`, so configuration reaches all five.

Managing connectors requires the `connector:write` permission
([connectors/controller.py:36](../backend/connectors/controller.py#L36)).

---

## 2. The SSRF guard

Because `base_url` is tenant-supplied, a connector is by construction a request to an
address the platform did not choose. Left unchecked that is a textbook
**Server-Side Request Forgery** primitive: a tenant writes an internal address and the
server dutifully fetches it from inside the trust boundary.

[common/outbound_http.py](../backend/common/outbound_http.py) is the shared guard every
such call must pass through. It does three things:

1. **Scheme check** — only `http` and `https`. `file://`, `gopher://`, `redis://` rejected.
2. **Address filtering** — the host is resolved and every returned address checked. Private,
   loopback, link-local, reserved, multicast and unspecified space is refused. If a host
   resolves to *both* a public and an internal address, the whole host is refused, so an
   attacker cannot win the race by having the resolver hand back the internal one.
3. **IP pinning** — the validated IP is written into the request URL, while the original
   hostname is kept in the `Host` header and TLS SNI so certificate validation still passes.

Point 3 is the subtle one and matters later. Without it there is a gap between *checking*
an address and *sending* to it, and a second DNS lookup can return something different in
between — **DNS rebinding**. Pinning closes that gap. Callers must also disable redirects,
since a 3xx would otherwise reach a host the guard never saw.

---

## 3. The problem

State Machine's AI agents need data from **ResolverIQ**, a backend that runs on the same
internal network. It is only reachable at a private address — `10.252.5.4` on the dev
server, and a Docker-assigned address such as `172.18.0.3` between containers.

Rule 2 blocks exactly that. Every attempt failed with:

```json
{
  "success": false,
  "message": "host bot-api-service-dev resolves to a blocked address 172.18.0.3"
}
```

Using a hostname does not help, because the guard validates the **resolved IP**, not the
name, and the internal hostname resolves into private space too. The same call with the
same token succeeds from a shell on the same box, which is what made this read as a bug.

The guard was not wrong. It had no way to express "this one address is fine."

---

## 4. Two designs, and why the second won

### Rejected: a boolean off-switch

The first implementation added `CONNECTORS_ALLOW_PRIVATE_HOSTS=true`, wired to the guard's
pre-existing `allow_private_hosts` bypass. It worked, and it was rejected in review. The
objection was correct, for a reason worth recording:

**The bypass disables two defences, not one.** Looking at `resolve_safe_target`, the
`allow_private_hosts` path returns the URL untouched — so it skips the address check *and*
the IP pinning. Pinning is the DNS-rebinding defence. Turning the switch on to reach one
known internal service also removes protection that had nothing to do with private
addresses.

It is also **deployment-wide and unbounded**. It applies to every connector call in the
process, and `base_url` is tenant-supplied, so any tenant can then dial any internal
address. Worst case is the cloud metadata endpoint `169.254.169.254`, which hands instance
credentials to anything that can reach it — the mechanism behind the 2019 Capital One
breach. This system makes that worse than usual: `response_mapping` writes response bodies
into entity fields, so a blind SSRF becomes a *readable* one.

### Adopted: an allowlist

Instead of switching the check off, narrow it. The operator names the addresses the
deployment may reach; everything else stays blocked, and the rest of the guard keeps
running.

The difference is not just "smaller blast radius" — allowlisted hosts are **still resolved
and still pinned**, so the DNS-rebinding defence survives. That is the property the boolean
threw away.

| | Boolean switch | Allowlist |
|---|---|---|
| Private-address check | off for everything | narrowed to listed blocks |
| IP pinning | **off** | **on** |
| Reach | any internal address | only what was written down |
| Metadata endpoint | exposed | refused unconditionally |
| Failure mode of a typo | silently permissive | stays blocked |

---

## 5. What changed

One file of logic: [common/outbound_http.py](../backend/common/outbound_http.py).

```
OUTBOUND_HTTP_ALLOWED_INTERNAL_IPS=10.252.5.4/32,172.18.0.0/16
```

Unset — the state of every existing deployment — is byte-identical to previous behaviour.

**The check lives inside the guard**, so `is_blocked_ip` consults the allowlist before
classifying an address:

```python
def is_blocked_ip(address):
    if is_allowlisted_ip(address):
        return False
    return address.is_private or address.is_loopback or ...
```

Consequently **no call site changed**. Connectors, the agent tool, the `webhook.http`
executor and remote-file fetches all pick it up unmodified, and there is exactly one place
that decides — no second switch to keep in sync.

### Design decisions worth knowing

**Environment, not database.** These addresses describe the network the process runs in,
not tenant configuration. Putting them in the database would mean a tenant-facing screen
could widen the SSRF guard. No migration, no settings UI.

**Link-local can never be allowlisted**, however it is spelled — including a wider block
that merely overlaps it, such as `169.254.0.0/15`. No co-located service is ever addressed
on link-local, so the exclusion costs nothing legitimate and removes the worst outcome even
from a misconfigured allowlist.

**Bad entries are dropped, not raised.** A typo in deployment config must not take every
outbound call down. Dropping also fails in the safe direction: the address stays blocked.
A warning is logged naming the offending entry.

**Prefer CIDR for container networks.** Docker reassigns service IPs when a container is
recreated, so a bare `172.18.0.3` silently stops matching while `172.18.0.0/16` keeps
working.

**The error now names the fix, addressed to the operator.** Previously the message read as
a platform bug to anyone deploying alongside an internal service:

```
host modular-backend resolves to a blocked address 172.22.0.6; a trusted internal
service must be allowlisted by the deployment operator via OUTBOUND_HTTP_ALLOWED_INTERNAL_IPS
```

Phrased as what an operator must do rather than as an instruction to the caller: on SaaS
the allowlist is never set, and this text surfaces to a tenant who cannot edit deployment
environment variables.

### Files touched

| File | Change |
|---|---|
| [backend/common/outbound_http.py](../backend/common/outbound_http.py) | Allowlist parsing, matching, link-local exclusion; `is_blocked_ip` consults it |
| [backend/tests/test_outbound_http.py](../backend/tests/test_outbound_http.py) | +35 tests; autouse fixture isolating the env var and parse cache |
| [backend/etc/.env.example](../backend/etc/.env.example) | Documented, empty by default |
| [README.md](../README.md) | New *Outbound HTTP / SSRF* subsection |

No database change, no migration, no request/response contract change, no new route, no
frontend change.

---

## 6. Configuring it

Add to `backend/etc/.env` — shared by `modular-backend` and `modular-worker`, so both
processes get it — and restart both:

```bash
OUTBOUND_HTTP_ALLOWED_INTERNAL_IPS=10.252.5.4/32,172.18.0.0/16
```

Accepted: any number of comma-separated entries; bare IPs (read as `/32`) or CIDR blocks;
IPv4 and IPv6 mixed; surrounding whitespace tolerated. Unparseable entries are dropped
individually with a warning, leaving valid ones in force.

**Do not set this on SaaS or any multi-tenant deployment.** `base_url` is tenant-supplied,
so whatever is listed becomes reachable by every tenant in that deployment. It is intended
for single-tenant self-hosted installs and local development.

---

## 7. Verification

| Check | Result |
|---|---|
| Guard unit tests | 69 passed (34 existing + 35 new) |
| Mutation — allowlist ignored | 4 tests fail (caught) |
| Mutation — link-local exclusion removed | 7 tests fail (caught) |
| Full backend suite vs clean `main` | 255 = 255, failure lists byte-identical |
| ruff / pyright, whole backend | unchanged (1431 / 933 errors, all pre-existing) |
| Public hosts, allowlist set and unset | resolved and pinned exactly as before |
| Real HTTPS call to a public API | `ok=True, 200` both ways |
| Live: co-located service, allowlist unset | blocked, error names the variable |
| Live: same, allowlist set | `ok=True, 200`, pinned to `172.22.0.6` with `Host` preserved |
| Live: metadata endpoint explicitly listed | still blocked |

---

## 8. Open items

- **The allowlist applies to every guard user**, including redirect-following in
  [remote_files/manager.py:69](../backend/remote_files/manager.py#L69). Intentional — one
  source of truth, blast radius bounded by what the operator listed. If it should be
  connector-only, that is a parameter on `resolve_safe_target` and a one-line change.
- **The `webhook.http` worker path is unverified by execution.** It needs a real workflow
  transition rather than an HTTP call. The shared `env_file` means it should work, but that
  is reasoning, not a test.
- **A per-connector allowlist** (rather than deployment-wide) would be tighter still, at the
  cost of a schema change and a settings UI. Not justified by this ticket.
