# Roles and groups

ConfigGen has a three-role permission model and group-based visibility
scoping, built for teams — and entirely invisible if you're using it
alone. See [Solo user mode](#solo-user-mode) if that's you; everything
else here is for when a second person joins in.

## The three roles

| | Admin | Template Engineer | Config Engineer |
|---|:---:|:---:|:---:|
| **Users & groups** | | | |
| Create/delete users, assign roles | ✓ | | |
| Create/manage groups, assign users | ✓ | | |
| Generate/revoke API keys | ✓ | | |
| **Templates & schemas** | | | |
| Create/edit schema + template | ✓ | ✓ | |
| Delete schema + template | ✓ | | |
| Publish / unpublish / deprecate | ✓ | ✓ | |
| Extract variables, version history, restore | ✓ | ✓ | |
| **Config generation** | | | |
| See draft / deprecated templates | ✓ | ✓ | |
| See published templates | ✓ | ✓ | ✓ |
| Generate (single or bulk), preview, diff | ✓ | ✓ | ✓ |
| **History & audit** | | | |
| View own generation history | ✓ | ✓ | ✓ |
| View group generation history | ✓ | ✓ | |
| View all generation history | ✓ | | |
| **Sharing** | | | |
| Export config pack | ✓ | ✓ | |
| Import config pack | ✓ | | |

Config Engineer is the daily-use role: fill in forms, generate configs,
see your own history. Template Engineer adds template authoring on top.
Admin adds user/group management and the two operations everyone else is
explicitly locked out of — deleting templates, and importing config
packs (importing can add executable code via a hook, so it's
never delegated).

## Groups

Groups scope **what a user can see and generate** — not what they're
allowed to do (that's the role's job). A schema declares its group with
`group: "Acme Corp"` at the top level:

```text
Group: "Acme Corp"
├── Templates: acme_router_base, acme_switch_vlan
├── Members:
│   ├── alice (Admin)             -> sees all groups automatically
│   ├── bob (Template Engineer)   -> sees only Acme Corp templates
│   └── carol (Config Engineer)   -> sees only *published* Acme Corp templates
```

- **Admins see every group automatically** — they're never assigned to
  one, they have implicit access to everything.
- Template Engineers and Config Engineers see only the groups they're
  explicitly assigned to (a user can belong to more than one).
- A schema with **no `group:`** is visible to everyone, regardless of
  group membership — the right choice for shared/generic templates.
- Dashboard tiles, the bulk-generation schema picker, and output folders
  are all filtered by the same group assignment.

## Template lifecycle

```text
Template Engineer creates          Config Engineer uses

  DRAFT  --publish-->  PUBLISHED  --generate-->  CONFIG OUTPUT
    ^                      |
    |<-----unpublish-------|
    |                      |
    |                  deprecate
    |                      v
    |                 DEPRECATED  (hidden from Config Engineers)
    |
  delete (Admin only)
    v
 [removed]
```

- **`draft`** — visible to Admins and Template Engineers only. For
  work in progress; Config Engineers never see it.
- **`published`** — visible to everyone in the group. What Config
  Engineers use day to day.
- **`deprecated`** — hidden from Config Engineers, still visible to
  Admins/Template Engineers for reference or restoring. Configs already
  generated from it stay in history regardless.
- **Delete** — Admin only, removes the schema/template/hook files.
  Generation history referencing it is preserved on purpose: the log
  records a schema ID and version, never a live reference to a file
  that might not exist anymore.

Flip a schema's `status:` from the GUI's template editor
(**Publish**/**Unpublish**/**Deprecate** buttons), or by hand.

## Generation log

Every generated config is logged automatically: who generated it, which
group/schema (with schema version), the full form inputs as JSON, when,
what file was written, and — for bulk runs — a shared batch ID linking
every row together.

**Who can see what:**

| | Admin | Template Engineer | Config Engineer |
|---|:---:|:---:|:---:|
| Own history | ✓ | ✓ | ✓ |
| Group history (all users in their groups) | ✓ | ✓ | |
| Everyone's history, every group | ✓ | | |

The GUI's **Generation Log** panel filters by user/group/schema/date
range; clicking an entry shows the exact inputs and offers
**Regenerate**, which reopens the generator pre-filled — the fastest way
to reproduce a config after a template update. On the CLI:

```bash
configgen log list --as-username bob --as-password ...
```

## Security

- Passwords: PBKDF2-SHA256, salted, 8-character minimum.
- 5 failed login attempts locks the account for 15 minutes.
- First login after account creation forces a password change.
- Usernames are restricted to `[a-z0-9_-]` — a username doubles as the
  output folder name.
- API keys are stored as a SHA256 hash (never recoverable in plaintext
  after creation), labeled for whoever's using them ("CI pipeline"),
  and individually revocable.
- No session tokens: the desktop app just holds the authenticated user
  in memory for as long as it's open.

## Setting up a team

Everything below is the CLI equivalent of the GUI's User Admin panel
(Admin-only). First launch bootstraps `admin`/`admin` — change that
password immediately (`configgen user passwd admin <new password>
--as-username admin --as-password admin`).

```bash
# A group for one team's templates
configgen group create "Acme Corp" --description "Acme's network templates" \
  --as-username admin --as-password admin

# A Template Engineer and a Config Engineer
configgen user create bob "a real password" --role template_engineer \
  --as-username admin --as-password admin
configgen user create carol "a real password" --role config_engineer \
  --as-username admin --as-password admin

# Both see Acme Corp's templates (bob can also edit them; carol only generates from published ones)
configgen group assign bob "Acme Corp" --as-username admin --as-password admin
configgen group assign carol "Acme Corp" --as-username admin --as-password admin

# An API key for an automated pipeline running as bob
configgen apikey create bob --label "CI pipeline" --as-username admin --as-password admin
```

`configgen user list`/`group list`/`apikey list` (same `--as-username`/
`--as-password` or `--as-api-key` auth) confirm the result. Every one of
these commands requires an authenticated Admin actor — there's no
unauthenticated path to user/group/API-key management, on the CLI or in
the GUI.

## Solo user mode

None of this is mandatory. Clone the repo, run ConfigGen, log in as
`admin` — you're the only user, you see every template regardless of
`group:`, and the role/group system simply never comes up unless you
choose to create a second account. The complexity is there for teams; it
stays out of the way for one person.
