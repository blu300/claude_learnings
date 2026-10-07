# Options Analysis: Blocking a Sub-Team from Specific Tables in Databricks

**Date:** 2026-10-07
**Status:** Draft for discussion

## 1. The problem

We grant read access at the catalog or schema level so that a broad group (e.g. `analysts`) can see every table inside, including tables created later. We then need to block a sub-team within that group (e.g. `contractors`) from reading a few dozen specific tables. The set of blocked tables changes roughly monthly.

Databricks does not provide a way to do this directly:

- A grant on a catalog or schema is inherited by every table inside it, now and in future. (Verified: Databricks Terraform provider docs.)
- `REVOKE` only removes a grant that was made directly on that object. It cannot cancel a grant inherited from the parent. (Search summary of Databricks docs; matches our own observation.)
- The old `DENY` command from the pre-Unity-Catalog days is not supported. Databricks' guidance is explicitly "do not grant broadly expecting to block underneath." (Search summary of Databricks docs.)

## 2. Requirements

| Requirement | Value |
|---|---|
| Number of restricted tables | Dozens |
| Rate of change | Monthly |
| Who is blocked | Sub-teams (groups), not named individuals |
| Acceptable outcome | Blocked user may see the table name; must not read its rows |
| New tables | Should still be covered by the broad grant without manual work |

## 3. What is not available yet

Databricks shipped two new label-driven rule types in September 2026. Neither solves this today, but both are worth tracking.

**Deny rule (Beta, 8 Sept 2026).** A rule attached at the catalog or schema that denies a permission on every table carrying a given label, overriding any grant. The catch: it currently supports only one permission, the right to manage other people's access. It cannot deny reading a table. If Databricks extends it to `SELECT`, this becomes the ideal answer with no restructuring.

**Grant rule (Beta).** A rule that grants a permission on labelled objects to a group, with a built-in "except these groups" list. The catch: it currently applies only to AI models and similar objects, not tables.

Both facts come from search summaries of the Databricks docs pages; the pages themselves could not be opened from this environment. Verified from Databricks' own code: the deny rule type was added to the Python SDK on 9 Sept 2026 (v0.137.0).

**Action:** re-check the deny-rule page quarterly.

## 4. Options

### Option A: Label-driven row filter that returns "no" for the blocked group — **Recommended**

A row filter is a small check attached to a table that decides, row by row, whether the person running the query may see it. If the check always answers "no" for the blocked group, that group sees the table exists but gets zero rows.

Databricks' label-driven rule system (generally available) lets one rule at the schema or catalog level attach a row filter to every table that carries a given label. Example shape:

```
Rule on schema `main.finance`:
  applies to:   group `contractors`
  when:         table has label restricted_from = 'contractors'
  row filter:   function that returns FALSE
```

| | |
|---|---|
| **Pros** | No restructuring. Broad grant stays. Monthly changes become "add or remove a label on a table", not permission edits. Databricks' best-practice page says to put the who-it-applies-to logic in the rule's "to / except" lists, which is exactly this shape. Switching to the deny rule later needs no relabelling. |
| **Cons** | Blocked users still see the table name and column names. Row filters add query-time cost. Row filters may not be supported on every table type or on data shared outside the account; the limitations page could not be opened and must be checked before committing. |
| **Effort** | Low. Define governed label, write one `FALSE` function, create one rule per schema or catalog, label the tables. |
| **Seen in practice** | Suggested on the Databricks community thread "How to grant all tables in schema except 1"; the asker there called it overkill for one table. For dozens of tables, the economics flip. |

### Option B: Permissions table driving row filters

Same mechanism as A, but the filter function looks up the current user's groups against a table that lists which group may read which table.

| | |
|---|---|
| **Pros** | Non-admins can manage exceptions by editing rows in a table. Full audit trail of who was blocked when. |
| **Cons** | Custom code to maintain. Every query on a filtered table does a lookup. More to get wrong than A. |
| **Effort** | Medium. |
| **Seen in practice** | Databricks SQL engineering team's own write-up on Medium ("Fine-grained Access Control with Permission Table"). |

### Option C: Move restricted tables into their own schema

Give the broad group the normal schemas. Grant the restricted schema only to a group that excludes the blocked sub-team.

| | |
|---|---|
| **Pros** | Databricks' own stated recommendation. Pure permissions, no rules or functions. Blocked users cannot see the table at all. |
| **Cons** | Tables physically move when their exception changes, which breaks any query or job that refers to them by name. With monthly changes, this becomes a steady stream of breakages. |
| **Effort** | Low to set up, high to live with. |

### Option D: Grant table-by-table from a config file

Stop granting at the schema level. A script or Terraform applies a per-table grant list.

| | |
|---|---|
| **Pros** | Exact control. Terraform's grants setting replaces whatever is on a table with what the file says (verified), so the file is the single source of truth and manual drift is undone. |
| **Cons** | New tables are blocked until someone adds them to the file, which defeats the "grant once at the top" goal. Dozens of tables becomes hundreds of lines. |
| **Effort** | Medium, ongoing. |
| **Seen in practice** | DZone article "Automate Databricks Unity Catalog Permissions at Table Level". |

### Option E: "Everyone except" groups in the identity provider

Create groups like `analysts_minus_contractors` and grant restricted tables to those.

| | |
|---|---|
| **Pros** | Simple to understand. Pure permissions. |
| **Cons** | Still needs table-level grants (Option D) to work, since the broad schema grant would otherwise cover the table. Group count grows with every distinct combination of exceptions. |
| **Effort** | Low per group, grows without bound. |

## 5. Comparison

| | A: Label + row filter | B: Permissions table | C: Separate schema | D: Per-table grants | E: Extra groups |
|---|---|---|---|---|---|
| Keeps broad grant | Yes | Yes | Yes | No | No |
| New tables auto-covered | Yes | Yes | Yes | No | No |
| Monthly change cost | Add/remove label | Edit a row | Move table, fix references | Edit file | Edit file + groups |
| Hides table name | No | No | Yes | Yes | Yes |
| Custom code | One `FALSE` function | Lookup function + table | None | Script | None |
| Query-time cost | Small | Small to medium | None | None | None |
| Needs verification | Row filter limitations | Row filter limitations | None | None | None |

## 6. Recommendation

Adopt **Option A**. It meets every requirement in section 2, needs no restructuring, and turns monthly changes into label edits. Before rollout, confirm in a test workspace that row filters work on the table types in use and that no restricted table is shared outside the account.

Keep **Option C** for any table where even the name is sensitive.

Re-check the deny rule each quarter. If it gains support for denying `SELECT`, migrate from A to it; the labels carry over unchanged.

## 7. Open questions

1. Do any restricted tables use a table type or sharing mode that row filters do not support? (Needs the Databricks "requirements, quotas, and limitations" page, which could not be opened.)
2. Is query-time cost of a row filter acceptable on the largest restricted tables?
3. Who owns applying labels: data owners or the platform team?

## 8. Sources

Opened and verified:
- Terraform provider, `policy_info` resource: https://raw.githubusercontent.com/databricks/terraform-provider-databricks/main/docs/resources/policy_info.md
- Terraform provider, `grants` resource: https://raw.githubusercontent.com/databricks/terraform-provider-databricks/main/docs/resources/grants.md
- Databricks Python SDK changelog, v0.137.0: https://raw.githubusercontent.com/databricks/databricks-sdk-py/main/CHANGELOG.md

Search-result summaries only (pages blocked from this environment; treat as unverified):
- ABAC DENY policies (Beta): https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/deny-policies
- ABAC GRANT policies: https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/grant-policies
- Best practices for ABAC policies: https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/abac/best-practices
- Manage privileges in Unity Catalog: https://docs.databricks.com/aws/en/data-governance/unity-catalog/manage-privileges/
- Release notes, September 2026: https://docs.databricks.com/aws/en/release-notes/product/2026/september
- Community: How to grant all tables in schema except 1: https://community.databricks.com/t5/data-engineering/how-to-grant-all-tables-in-schema-except-1/td-p/107872
- Fine-grained Access Control with Permission Table (Databricks SQL SME): https://medium.com/dbsql-sme-engineering/fine-grained-access-control-with-permission-table-in-databricks-sql-e6a24d1e1b6e
- Automate Unity Catalog Permissions at Table Level (DZone): https://dzone.com/articles/automate-databricks-unity-catalog-permissions-at-table-level
