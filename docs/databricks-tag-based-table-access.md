# Tag-based table access in Databricks: design notes

**Date:** 2026-10-08
**Status:** Draft for review. Supersedes Option A in `databricks-table-exclusion-options.md`.

---

## Background

### The problem

We grant read access at the catalog or schema level so that a broad group (e.g. `analysts`) can see every table inside, including tables created later. We then need to block a sub-team within that group from reading specific tables, and conversely to open a table to several teams at once. The set of restricted tables changes roughly monthly.

Databricks does not provide a way to do this directly:

- A grant on a catalog or schema is inherited by every table inside it, now and in future.
- `REVOKE` only removes a grant that was made directly on that object. It cannot cancel a grant inherited from the parent.
- The old `DENY` command from the pre-Unity-Catalog days is not supported. Databricks' guidance is explicitly "do not grant broadly expecting to block underneath."

### Requirements

| Requirement | Value |
|---|---|
| Number of restricted tables | Dozens |
| Rate of change | Monthly |
| Who is blocked / admitted | Sub-teams (groups), not named individuals; a table may be readable by several groups at once |
| Default for a new table | Locked. A table can't be read until someone with the right to tag it has tagged it |
| Who may tag | Only stewards. Ordinary users hold APPLY TAG for other tags, so the access tags must be governed and gated separately |
| Acceptable outcome | Blocked user may see the table name; must not read its rows |
| New tables | Must still be covered without manual permission work |

### Why a row filter

Databricks' own "common patterns" page documents a `block_all()` function with a tag condition as the way to block a whole table, and its "secure new tables by default" tutorial documents the born-locked / steward-unlocks flow. A row filter is a small check attached to a table that decides, row by row, whether the person running the query may see it. If the check always answers "no" for a user, that user sees the table exists but gets zero rows. We use the mechanism slightly off-label: our check function doesn't look at the row at all, it only looks at the table's tags and the user's groups, so its answer is the same for every row.

Databricks calls the label-driven rule system ABAC (attribute-based access control): a *policy* attached to a catalog applies to every table in it, including tables created next year, and decides per table and per user whether to attach the row filter.

### Feature status and dates

- Row-filter and column-mask policies: generally available, April 2026.
- `get_tag_value()`, the function that feeds a table's tag value into a filter function: added September 2026. Creating a policy that uses it needs Runtime 18 LTS or above; querying the tables needs serverless or Runtime 16.4 or above.
- Policies on views, and policies attached at the metastore (every catalog at once): Beta.
- Since 28 April 2026, a query through a view is evaluated as the *querying* user, so a view can't be used to leak around a filter.

### Who does what

| Role | Needs | Day-to-day action |
|---|---|---|
| Account admin | account-level CREATE on governed tags | creates the governed tags once |
| Governance / platform | MANAGE on the catalog (or owner); EXECUTE on the filter function; metastore admin for the metastore-wide Beta form | creates and edits the policy, function and lookup table |
| Data steward | ASSIGN on the governed tags + APPLY TAG on the catalog | sets a table's tags (this *is* the grant) |
| Reader | ordinary SELECT grant | nothing new |

---

## What we ruled out and why

**We can't have a governed tag, `domain`, with a dropdown list and apply it multiple times to a table with a different value per instance.** A tag key holds one value per object. In Databricks' own SDK the tag-assignment API is `get(entity, tag_key)`, `update(entity, tag_key, ...)`, `delete(entity, tag_key)`: there is no way to address a second value under the same key. Setting `domain=hr` on a table that already has `domain=finance` replaces it.

**We can't then have a value for each combination of groups.** With 3 groups that's already 7 labels (a, b, c, ab, ac, bc, abc) and 4 groups gives 15; the formula is 2ⁿ − 1. A set-based tag only needs the combinations *actually in use*, not all of them, which is why Databricks' own patterns lean that way; we rejected it because combinations are unpredictable and stewards need to say "finance and hr" directly rather than pick a named set. See Option 2 for the full comparison.

**So we use boolean tags: `is_finance`, `is_hr`, each with the single allowed value `'yes'`.** They must carry a value, because a key-only governed tag reads back as `NULL` whether present or not. They must be governed, with ASSIGN restricted to stewards, because our users hold APPLY TAG for other tags.

**We can't call `has_tag` inside a row-filter function.** `has_tag()` and `has_tag_value()` are *policy conditions*: the metadata service (Databricks calls it the control plane) evaluates them when deciding whether a policy applies to a table, in the policy's `WHEN` and `MATCH COLUMNS` clauses. The filter function is ordinary SQL run by the query engine with no table in scope, so there is nothing for `has_tag` to test against. There is no "current table" function either, so the function can't query `information_schema.table_tags` for itself.

**But the policy can fetch named tags off the table and pass their values to the function.** `get_tag_value('is_hr')` in the policy's `USING COLUMNS` list hands the function the table's value for that tag (direct or inherited from schema/catalog), or `NULL` if absent. The policy can't discover which tags a table has; it can only fetch tags it names explicitly, one `get_tag_value('is_x')` per group. That's why adding a group means editing the policy. (`USING COLUMNS` is a misleading clause name: it is just "the argument list passed to the function". No column is tagged or read.)

**We can't use one policy per group with `has_tag` in `WHEN`.** Tag tables `is_finance=yes`, write one policy per group that blocks that group when its tag is absent; no function arguments, no lookup table. It fails for anyone in two groups: every applicable policy's filter must pass, so a user in `finance` and `hr` querying a finance-only table is blocked by the hr policy. Two *different* filters on one table for one user is an outright error. "Any of my groups" can only be expressed inside a single function.

**We can't use the Databricks regional example as a template.** The documented example

```sql
CREATE POLICY regional_access_emea
ON CATALOG sales
ROW FILTER filter_by_region
TO `emea team`
FOR TABLES
MATCH COLUMNS has_tag('region') AS rgn
USING COLUMNS (rgn, 'EMEA');
```

finds a **column** tagged `region` and passes that column's value, row by row, to the function: EMEA rows for the EMEA team. Our tables have no column that says who may read them, so there's nothing for `MATCH COLUMNS` to find. And the `'EMEA'` constant with `TO emea team` is one policy per team, which is the multi-group trap again.

**We can't use the new DENY or GRANT policy types.** DENY policies are in Beta and can only deny the *manage access* permission, not reads. GRANT policies only cover AI models and similar objects, not tables. Worth re-checking quarterly: either becoming table-capable would replace everything below with no restructuring.

**We can't use an ungoverned free-text tag with a comma-separated group list.** Policies require governed tags, governed tags can't take free-form values, and an ungoverned tag could be set by any user with APPLY TAG, letting them grant themselves access.

---

## Option 1: the boolean tag approach (chosen)

### Why this shape

1. One governed tag per group (`is_finance=yes`), so a steward can stack any combination on a table.
2. One policy, attached at the catalog, with no `WHEN` clause, so it applies to every table including untagged ones: a new table is born locked.
3. The policy names every group tag with `get_tag_value()` and passes the values into one function; the function returns true if *any* tagged group contains the user. This is the only shape that gives "any of my groups".
4. A lookup table maps argument positions to groups, so the function body never contains group names and never changes when groups are added. The policy still changes once per group, and that edit should be generated from the lookup table.
5. Default-deny falls out naturally: an untagged table yields `NULL` for every argument, nothing matches, zero rows.
6. Governance is gated by ASSIGN on the governed tags, which ordinary users don't hold.

### The code

Three groups to start (`finance`, `hr`, `sales`), ten slots so you can add seven more groups without touching the function. Everything is SQL; the one step that has no SQL form (granting ASSIGN on a governed tag) is shown as Terraform.

```sql
-- =====================================================================
-- 0. PREREQUISITES (one-time, platform team)
-- =====================================================================
-- Compute: serverless, or Runtime 16.4+ to query; Runtime 18 LTS+ to run
--          CREATE POLICY with get_tag_value (per the core-concepts page).
-- Groups:  account-level groups `finance`, `hr`, `sales`, `data_stewards`
--          and a service principal `etl_sp` must already exist.
-- Catalog: `sales_cat` already has its ordinary broad grant, e.g.
--   GRANT USE CATALOG, USE SCHEMA, SELECT ON CATALOG sales_cat TO `account users`;
-- Home for governance objects:
CREATE SCHEMA IF NOT EXISTS gov.policy;


-- =====================================================================
-- 1. GOVERNED TAGS, one per readable group  (account admin; DBR 18.1+)
-- =====================================================================
-- Value list is deliberately a single word so a table either has the tag
-- with value 'yes' or doesn't have it. Don't make these key-only: a
-- key-only tag reads back as NULL whether present or not.
CREATE GOVERNED TAG is_finance DESCRIPTION 'Members of group finance may read' VALUES ('yes');
CREATE GOVERNED TAG is_hr      DESCRIPTION 'Members of group hr may read'      VALUES ('yes');
CREATE GOVERNED TAG is_sales   DESCRIPTION 'Members of group sales may read'   VALUES ('yes');
-- Below Runtime 18.1 there is no SQL for this: use Terraform
-- databricks_tag_policy or POST /api/2.1/tag-policies instead.


-- =====================================================================
-- 2. WHO MAY APPLY THOSE TAGS  (account admin)
-- =====================================================================
-- Two permissions are needed to put is_<group>=yes on a table:
--   (a) ASSIGN on the governed tag  -> only data_stewards get this
--   (b) APPLY TAG on the table      -> grant once at catalog level
-- (b) is SQL:
GRANT APPLY TAG ON CATALOG sales_cat TO `data_stewards`;
-- (a) has no SQL form. Account console: Governed Tags > is_finance >
--     Permissions > add data_stewards with ASSIGN. Or Terraform:
```

```hcl
resource "databricks_access_control_rule_set" "is_finance_assign" {
  name = "accounts/${var.account_id}/tagPolicies/${databricks_tag_policy.is_finance.id}/ruleSets/default"
  grant_rules {
    principals = [data.databricks_group.data_stewards.acl_principal_id]
    role       = "roles/tagPolicy.assigner"
  }
}
```

```sql
-- Ordinary users keep whatever APPLY TAG rights they have for other tags,
-- but cannot set is_* tags because they lack ASSIGN on them.


-- =====================================================================
-- 3. LOOKUP TABLE: which argument slot carries which group's tag
-- =====================================================================
-- Readers never need access to this table; the function reads it with
-- its owner's rights. Only governance should be able to write to it.
CREATE TABLE gov.policy.slot_groups (
  slot       INT    NOT NULL,   -- position in the policy's USING COLUMNS list
  tag_key    STRING NOT NULL,   -- governed tag name, for documentation
  group_name STRING NOT NULL    -- account group that the tag admits
);
INSERT INTO gov.policy.slot_groups VALUES
  (1, 'is_finance', 'finance'),
  (2, 'is_hr',      'hr'),
  (3, 'is_sales',   'sales');


-- =====================================================================
-- 4. THE ROW FILTER FUNCTION  (written once, never edited for new groups)
-- =====================================================================
-- Returns TRUE if, for any slot, the table's tag value is 'yes' AND the
-- querying user is a (direct or nested) member of that slot's group.
-- Rows where it returns FALSE are dropped, so the result is all-or-nothing.
--
-- Example input (s1=is_finance, s2=is_hr, s3=is_sales, rest '-'):
--   ('yes','yes','-',...)  user in `hr`           -> TRUE   (all rows)
--   ('yes','yes','-',...)  user in `sales` only   -> FALSE  (0 rows)
--   ('-','-','-',...)      any user, untagged tbl -> FALSE  (0 rows: locked)
--   (NULL,NULL,NULL,...)   same as above          -> FALSE
CREATE OR REPLACE FUNCTION gov.policy.any_group_tag_allows(
  s1 STRING, s2 STRING, s3 STRING, s4 STRING, s5 STRING,
  s6 STRING, s7 STRING, s8 STRING, s9 STRING, s10 STRING)
RETURNS BOOLEAN
RETURN EXISTS (
  SELECT 1
  FROM gov.policy.slot_groups g
  WHERE is_account_group_member(g.group_name)
    AND CASE g.slot
          WHEN 1 THEN s1  WHEN 2 THEN s2  WHEN 3 THEN s3  WHEN 4 THEN s4  WHEN 5 THEN s5
          WHEN 6 THEN s6  WHEN 7 THEN s7  WHEN 8 THEN s8  WHEN 9 THEN s9  WHEN 10 THEN s10
        END = 'yes'
);
-- The policy creator needs EXECUTE on this function; readers do not.


-- =====================================================================
-- 5. THE POLICY  (one per catalog; or ON METASTORE, Beta, for all catalogs)
-- =====================================================================
-- No WHEN clause, so it applies to every table in the catalog, tagged or
-- not. Each get_tag_value() fetches that tag off the table being queried
-- (direct or inherited) and returns NULL if absent. Unused slots are
-- padded with the constant '-' (constants are documented as allowed).
-- EXCEPT lists the identities that must always see everything:
-- stewards, and the service principal that runs pipelines/clones/backups.
-- Cap: 20 principals across TO + EXCEPT.
CREATE OR REPLACE POLICY read_by_group_tags
ON CATALOG sales_cat
ROW FILTER gov.policy.any_group_tag_allows
TO `account users` EXCEPT `data_stewards`, `etl_sp`
FOR TABLES
USING COLUMNS (
  get_tag_value('is_finance'),
  get_tag_value('is_hr'),
  get_tag_value('is_sales'),
  '-', '-', '-', '-', '-', '-', '-'
);


-- =====================================================================
-- 6. DAY-TO-DAY: steward opens / changes / closes a table
-- =====================================================================
-- Table X readable by finance and hr:
SET TAG ON TABLE sales_cat.ops.table_x is_finance = 'yes';
SET TAG ON TABLE sales_cat.ops.table_x is_hr      = 'yes';
-- Table Y readable by finance only:
SET TAG ON TABLE sales_cat.ops.table_y is_finance = 'yes';
-- Revoke hr from X:
UNSET TAG ON TABLE sales_cat.ops.table_x is_hr;
-- Open a whole schema to sales (inherited by every table in it, including
-- future ones). Whether a table-level UNSET can remove an inherited tag is
-- inferred from the inheritance model, not documented: test it.
SET TAG ON SCHEMA sales_cat.commercial is_sales = 'yes';
-- Tag changes take "a few minutes" to be enforced.


-- =====================================================================
-- 7. ADDING A GROUP LATER  (e.g. `ops` into slot 4)
-- =====================================================================
CREATE GOVERNED TAG is_ops VALUES ('yes');          -- + ASSIGN to data_stewards
INSERT INTO gov.policy.slot_groups VALUES (4, 'is_ops', 'ops');
CREATE OR REPLACE POLICY read_by_group_tags        -- same as §5, slot 4 filled
ON CATALOG sales_cat
ROW FILTER gov.policy.any_group_tag_allows
TO `account users` EXCEPT `data_stewards`, `etl_sp`
FOR TABLES
USING COLUMNS (
  get_tag_value('is_finance'), get_tag_value('is_hr'),
  get_tag_value('is_sales'),   get_tag_value('is_ops'),
  '-', '-', '-', '-', '-', '-'
);
-- Function untouched. Past slot 10: re-create the function with more
-- parameters once (it's a mechanical edit), then continue as above.


-- =====================================================================
-- 8. VERIFY
-- =====================================================================
-- Which policies hit a given table:
SHOW EFFECTIVE POLICIES ON TABLE sales_cat.ops.table_x;
-- What a table is tagged with (direct tags only; inherited ones show on the
-- parent schema/catalog):
SELECT * FROM sales_cat.information_schema.table_tags
WHERE schema_name = 'ops' AND table_name = 'table_x';
-- Report: tables with no is_* tag at all (i.e. locked for everyone):
SELECT t.table_schema, t.table_name
FROM   sales_cat.information_schema.tables t
LEFT JOIN sales_cat.information_schema.table_tags tt
       ON tt.schema_name = t.table_schema AND tt.table_name = t.table_name
      AND tt.tag_name LIKE 'is\_%'
WHERE  tt.tag_name IS NULL AND t.table_schema <> 'information_schema';
-- Behaviour test: as a member of `hr` only, SELECT from table_x -> rows;
-- from table_y -> zero rows, no error.
```

### Walking through one query

Priya is in group `hr` only. She runs `SELECT * FROM sales_cat.ops.table_x`, and `table_x` is tagged `is_finance=yes` and `is_hr=yes`.

**Before the query runs: Databricks decides whether the policy applies**

- Databricks sees the table is inside `sales_cat`, and the policy `read_by_group_tags` is attached to that catalog, so the policy is a candidate.
- It checks Priya against the policy's `TO` list (`account users`: yes, she's in it) and `EXCEPT` list (`data_stewards`, `etl_sp`: no, she isn't). So the policy applies to her.
- There's no `WHEN` clause, so there's no tag condition to pass or fail. The policy applies to this table.

**Databricks gathers the function's arguments from the table's tags**

- The policy's `USING COLUMNS` list has ten entries. Databricks evaluates each one *for this table*:
  - `get_tag_value('is_finance')` → looks on `table_x` (and its schema and catalog) for a tag called `is_finance`. Finds it. Value: `'yes'`.
  - `get_tag_value('is_hr')` → finds it. `'yes'`.
  - `get_tag_value('is_sales')` → not on the table or its parents. `NULL`.
  - The seven `'-'` entries are just the literal text `'-'`.
- Result: ten values, in order: `'yes', 'yes', NULL, '-', '-', '-', '-', '-', '-', '-'`.

**Databricks calls the function with those ten values**

- `any_group_tag_allows(s1='yes', s2='yes', s3=NULL, s4='-', ..., s10='-')`.
- The function never knows which table it's filtering or what the tags are called. All it has is ten positional values. The lookup table is what gives those positions meaning.

**Inside the function**

- It reads `gov.policy.slot_groups`, which has three rows:

  | slot | tag_key | group_name |
  |---|---|---|
  | 1 | is_finance | finance |
  | 2 | is_hr | hr |
  | 3 | is_sales | sales |

- The `CASE` is the bridge between ten anonymous arguments and rows numbered 1, 2, 3: "given this row's slot number, give me the matching argument." For the row with `slot = 1` it yields `s1`; for `slot = 2` it yields `s2`; and so on. It's a lookup-by-position, nothing more.
- For each row it asks two questions and both must be true:
  - *Is Priya in this row's group?* `is_account_group_member(group_name)`.
  - *Is the argument in this row's slot equal to `'yes'`?*
- Row by row:
  - slot 1, `finance`: Priya isn't in `finance` → fails. (The tag value `s1='yes'` doesn't matter.)
  - slot 2, `hr`: Priya is in `hr` → true. Slot 2's argument is `s2='yes'` → true. **Both true.**
  - slot 3, `sales`: Priya isn't in `sales` → fails.
- `EXISTS (...)` asks "did at least one row pass?" Yes, slot 2 did. The function returns `TRUE`.

**Databricks applies the answer to the rows**

- A row filter keeps rows where the function returns `TRUE`. Our function ignores the row's contents, so the answer is the same for every row: `TRUE`. (The group-membership check is resolved once per query, not per row.)
- Priya gets the whole table.

**Same query, different person**

- Ravi is in `sales` only. Same table, same ten arguments (`'yes', 'yes', NULL, '-', ...`), because the arguments come from the table, not the user.
- Inside the function: slot 1 → Ravi not in `finance`. Slot 2 → not in `hr`. Slot 3 → Ravi *is* in `sales`, but slot 3's argument is `s3=NULL`, and `NULL = 'yes'` is not true. Fails.
- No row passes. Function returns `FALSE` for every row. Ravi gets zero rows, no error.

**Someone in two groups, only one of which is allowed**

`table_x` is now tagged `is_finance = yes` only. Person A is in `finance` and `hr`; person B is in `hr` only.

| row | group | A in group? | `CASE` picks | value | `= 'yes'`? | row counts? |
|---|---|---|---|---|---|---|
| 1 | finance | yes | `s1` | `'yes'` | yes | **yes** |
| 2 | hr | yes | `s2` | `NULL` | no | no |
| 3 | sales | no | `s3` | `NULL` | no | no |

Row 1 counts, so A sees every row. Row 2 fails because the table has no `is_hr` tag; it doesn't matter, A only needs one row to pass. Being in an extra group never hurts.

| row | group | B in group? | `CASE` picks | value | `= 'yes'`? | row counts? |
|---|---|---|---|---|---|---|
| 1 | finance | **no** | `s1` | `'yes'` | yes | no (first test failed) |
| 2 | hr | yes | `s2` | `NULL` | **no** | no (second test failed) |
| 3 | sales | no | `s3` | `NULL` | no | no |

No row counts → B gets zero rows. The table *is* open to finance, but B isn't in finance; B is in hr, but the table isn't open to hr. Each row needs both halves, and B never has both on the same row.

**Same person, untagged table**

- Priya queries a brand-new table with no tags. All three `get_tag_value` calls return `NULL`. Nothing can equal `'yes'`. Function returns `FALSE`. Zero rows: the table is locked until a steward tags it.

**Why the function never changes when you add a group**

- The function body says "for every row in `slot_groups`, check the argument in that slot." It has no group names in it.
- Adding `ops` means: a new governed tag, a new row `(4, 'is_ops', 'ops')`, and putting `get_tag_value('is_ops')` into position 4 of the policy's list where a `'-'` used to be. The function already handles slot 4 via `WHEN 4 THEN s4`; it just never had a row for it before.

**Two things worth noticing**

- The exempt identities (`data_stewards`, `etl_sp`) never reach the function. The policy skips them at the very first step, so they see every row of every table.
- The slot-to-group mapping has to agree in two places: the lookup table's `slot` column and the position of `get_tag_value('is_x')` in the policy. If those drift apart, the wrong group opens the wrong tables. That's why it's worth generating the policy text from the lookup table with a small script rather than editing both by hand.

### Downsides

**It's a filter pretending to be a permission**
- Blocked users still see the table in the catalog browser, its column names, comments, lineage and schema. They get an empty result, not an error. Nothing tells them "you're not allowed"; they'll assume the table is empty and raise tickets.
- Nothing in `SHOW GRANTS` or the Permissions tab reflects it. "Who can read table X?" is answered only by joining tags to the lookup table yourself. Auditors won't find it where they look.

**It takes the only row-filter slot on every table in the catalog**
- Databricks allows one row filter per table per user; two different ones is an error. This design spends that slot on every table in scope. If any table later needs real row-level filtering (regions, cost centres), it can't have its own policy; the logic has to be merged into this one function.
- Any table that already has a hand-applied row filter will break the moment the policy is created.

**Writers get hurt**
- The filter applies to anyone not in `EXCEPT`, including engineers and jobs that *write*. Their `UPDATE`/`DELETE` only see the rows the filter shows them (possibly none). `MERGE` is documented as unsupported on tables whose filter contains a subquery, and this function has one. So every writing identity must be exempt.
- A user who creates a table in the catalog can't read it back until a steward tags it, because a new table inherits no `is_*` tag. Either creators are exempt, or every working schema carries a schema-level tag so its tables are born open to that team.

**Exemption is all-or-nothing, and capped**
- `EXCEPT` is catalog-wide: an exempt identity sees every row of every table. There's no "exempt for this schema only" without a second policy, which would conflict.
- `TO` + `EXCEPT` is capped at 20 principals. Stewards, every ETL identity, every writing team: it fills fast. Nesting groups is the escape hatch, and nested-group matching in `EXCEPT` is one of the things not verified.

**Blast radius**
- The design fails closed, which is correct, but "closed" means the whole catalog. Drop or rename the lookup table, delete a governed tag the policy references, break the function, or lose `EXECUTE` on it, and every query on every table in the catalog errors until it's fixed.
- `CREATE OR REPLACE POLICY` is the only way to change it. Whether there's a window during the replace where the policy is absent (tables briefly open) or doubled (tables briefly erroring) isn't documented.

**Two places must agree**
- Slot numbers in the lookup table and argument positions in the policy are maintained separately. If they drift, the wrong group opens the wrong tables and nothing errors. This needs a generator script, not hand edits.

**Tags have their own quirks**
- Governed tag keys are account-global and unique: `is_finance` means the same thing in every catalog, and a steward with ASSIGN on it can open any table they have APPLY TAG on, in any catalog. ASSIGN isn't scoped per catalog.
- A tag set on a schema is inherited by every table in it, including future ones, and a table can't opt out (there's no "not this one" tag). Convenient, and a footgun.
- Changes take "a few minutes" to be enforced. Revocation isn't instant.

**Platform constraints**
- Readers need serverless or Runtime 16.4+; older clusters are refused. Creating the policy needs Runtime 18 LTS+.
- Clones, time travel, pipeline refreshes and backups fail for non-exempt identities. Materialized views and streaming tables refreshed by a non-exempt identity permanently contain zero rows.
- `get_tag_value` shipped in September 2026. It has a few weeks of production history, not years.

### What hasn't been checked

**No Databricks doc page was opened directly.** Every claim about docs.databricks.com in this document comes from search-engine summaries of those pages, cross-checked where possible against the SDK and Terraform sources that could be opened. The summaries were consistent with each other and with the code, but the pages themselves have not been read.

**Specific behaviours with no written answer, all cheap to test:**
- `get_tag_value` in `USING COLUMNS` on a policy with no `WHEN`. The docs say it "reads from the table that satisfies the WHEN condition"; an omitted `WHEN` defaults to true, so it should bind to every table.
- An absent tag arrives as `NULL` (documented) and the untagged-table report in §8 agrees with what users actually see.
- A constant `'-'` mixed with `get_tag_value` arguments; and any cap on argument count. If the parser objects, fall back to declaring exactly as many parameters as groups and regenerating function and policy together.
- A function containing an `EXISTS` subquery accepted as an ABAC row filter (the mapping-tables page implies yes).
- Nested group membership honoured by `is_account_group_member` inside a policy function (documented as "direct or indirect"), and by `EXCEPT`.
- Whether the lookup table is read with the function owner's rights (inferred from a limitations note, not stated).
- What happens to in-flight queries during `CREATE OR REPLACE POLICY`.
- What a non-exempt user's `INSERT`/`UPDATE`/`DELETE` does on a filtered table.
- Whether a table-level `UNSET TAG` reverts to an inherited schema/catalog value.

**Things not researched at all:**
- Dashboards, scheduled queries, alerts and Genie spaces that run with the *owner's* credentials. If a steward publishes a dashboard with embedded credentials, viewers may see data the filter would hide from them. This is the most likely real-world bypass.
- Delta Sharing, external engines reading through the Iceberg/Unity REST interfaces, and Lakehouse Federation: whether the filter is enforced, ignored, or the read is refused.
- Differences between AWS, Azure and GCP availability of `get_tag_value` and metastore-level policies.
- Query-time cost on the largest tables. The function is evaluated once per query, not per row, and the lookup is tiny, but there are no numbers.
- Limits on governed tags per account.

---

## Option 2: the domain-set approach, compared

### The idea

A single governed tag, `access_set`, whose allowed values are *names of reader groups-of-groups*. A table carries one value. A small table maps each value to the account groups it admits. One function reads that mapping; one policy feeds the function the table's value.

```sql
CREATE GOVERNED TAG access_set
  VALUES ('finance_only', 'finance_hr', 'commercial', 'all_staff');

CREATE TABLE gov.policy.access_set_groups (access_set STRING, group_name STRING);
INSERT INTO gov.policy.access_set_groups VALUES
  ('finance_only', 'finance'),
  ('finance_hr',   'finance'), ('finance_hr', 'hr'),
  ('commercial',   'sales'),   ('commercial', 'marketing'),
  ('all_staff',    'account users');

-- TRUE if the user is in any group mapped to the table's access set.
-- ('finance_hr', user in hr)       -> TRUE
-- ('finance_only', user in hr)     -> FALSE
-- (NULL, anyone)  untagged table   -> FALSE
CREATE FUNCTION gov.policy.in_access_set(s STRING) RETURNS BOOLEAN
RETURN s IS NOT NULL AND EXISTS (
  SELECT 1 FROM gov.policy.access_set_groups g
  WHERE g.access_set = s AND is_account_group_member(g.group_name));

CREATE POLICY read_by_access_set
ON CATALOG sales_cat
ROW FILTER gov.policy.in_access_set
TO `account users` EXCEPT `data_stewards`, `etl_sp`
FOR TABLES
USING COLUMNS (get_tag_value('access_set'));

SET TAG ON TABLE sales_cat.ops.table_x access_set = 'finance_hr';
```

**How a query runs.** Identical to Option 1 up to the function call, except the policy passes one value instead of ten. The function looks up that value's rows and asks "am I in any of these groups?" A user in `hr` querying a `finance_hr` table: row (`finance_hr`, `hr`) matches, all rows returned. Same user on a `finance_only` table: no matching row, zero rows.

### What changes versus Option 1

| | Boolean tags (Option 1) | Access set (Option 2) |
|---|---|---|
| Steward says | "finance, and hr" (two `SET TAG`s) | "finance_hr" (one `SET TAG`) |
| New group joins existing readership | new governed tag + lookup row + **policy edit** | one `INSERT` |
| New combination of groups | nothing | one allowed value added + its rows |
| Policy ever edited again? | yes, once per group | no |
| Function ever edited again? | past 10 groups | no |
| Slot/position drift risk | yes (two places must agree) | none |
| Governed tags to manage | one per group | one |
| ASSIGN grants to manage | one per group | one |
| Untested bits | `'-'` padding, argument cap | neither |

### The combination argument, examined

The allowed-values list only needs the sets *in use*, not 2ⁿ − 1. With 4 groups there are 15 possible sets; in practice a data estate uses perhaps 4 to 8 of them, because readership follows organisational lines ("commercial", "finance and risk"), not arbitrary subsets. The question is empirical: list the dozens of tables and their intended readers today. If they fall into fewer than ~10 distinct sets, Option 2 is less work in every row of the table above. If they genuinely scatter, Option 1 is right.

### Adding a set, concretely

`ALTER GOVERNED TAG access_set SET VALUES ('finance_only', 'finance_hr', 'commercial', 'all_staff', 'finance_risk')` (the list is replaced whole, so you resend all of it; needs MANAGE on the tag), then `INSERT` the rows. Terraform makes both a one-line change. Not documented: what happens to tables already tagged with a value you *remove* from the list. Treat removal as a test item or never remove, only add.

### Hybrids worth knowing

- Name sets after real things, not combinations: `commercial`, `finance_confidential`, `hr_restricted`, `all_staff`. Then "finance and hr both read it" is a property of the set, and a new combination is a governance decision ("we now have a finance-and-hr tier") rather than a steward's ad-hoc choice. Some organisations prefer that control.
- Sets can nest via the lookup table: `('finance_hr', 'finance')`, `('finance_hr', 'hr')` is just rows. No limit on groups per set, unlike `EXCEPT`'s cap of 20.
- Starting with Option 2 and moving to Option 1 later is a real migration (different tags, different function, different policy), so pick once.

### Downsides specific to Option 2

- Stewards must know the set names; the dropdown is the whole vocabulary. If the set they need doesn't exist, they wait on governance.
- The lookup table is now the entire access model. A wrong `INSERT` opens tables; lock its write access down and audit it.
- Everything in Option 1's shared downsides list still applies: empty results not errors, one row-filter slot per table, catalog-wide exemptions, fail-closed blast radius, few-minute tag propagation, Runtime 16.4+/18 LTS.

### Which to choose

Option 1 if stewards must compose readership per table and combinations are unpredictable. Option 2 if readership clusters into a stable vocabulary and you'd rather never touch the policy again. Only the table inventory can settle it.

---

## Auditability (both options)

`SHOW GRANTS` won't show it. It reports only real grants, so every table in the catalog shows the same broad `SELECT`, inherited. The tag-based restriction and the policy are invisible there, and in the Catalog Explorer permissions tab.

`SHOW EFFECTIVE POLICIES ON TABLE x` tells you the policy applies, not which groups it admits. `DESCRIBE POLICY` shows the `EXCEPT` list, which is the only place the exempt identities appear.

"Which groups can read which table" has to be built from the system tables: `information_schema.table_tags` (direct tags only), unioned with `schema_tags` and `catalog_tags` for inherited ones, joined to the lookup table (`slot_groups` or `access_set_groups`). Wrap that in a view in `gov.policy`; a second view listing tables with no match is the "locked tables" report. Append the `EXCEPT` principals to every row or the view under-counts.

Group → people is not in `information_schema`; it comes from the account console or SCIM.

Not checked: whether `system.access.audit` records `SET TAG` / `UNSET TAG`, i.e. whether "who opened this table, and when" is recoverable. `table_tags` has no history. If the audit log doesn't cover it, snapshot the view on a schedule.

---

## Other options

Each option, what it costs, and the single reason it lost.

**Separate schema for restricted tables.** Put every table with special readership in its own schema and grant that schema only to the right groups. Databricks' own recommendation; pure permissions, no policies, and blocked users can't even see the table. Loses because the exception set changes monthly and each change is a physical table move that breaks every query and job referring to the old name. Also still needs one schema per group combination.

**Per-table grants from a config file.** Stop granting at the schema level; a script or Terraform applies `GRANT SELECT` table by table from a list. Exact, auditable in `SHOW GRANTS`, and Terraform's grants resource overwrites manual drift. Loses because new tables are invisible until someone adds them to the file, which is the opposite of "grant once at the top", and dozens of tables becomes hundreds of lines.

**"Everyone except" groups in the identity provider.** Create `analysts_minus_contractors` style groups and grant to those. Simple to understand and pure permissions. Loses because it still needs per-table grants to beat the inherited schema grant, and the group count grows with every combination.

**Databricks' DENY and GRANT policies.** The newest label-driven rule types, both with built-in "except these groups" lists. DENY is in Beta and can only deny the *manage access* permission, not reads; GRANT only covers AI models, not tables. Loses because neither can touch table reads today; worth re-checking quarterly since either becoming table-capable would replace everything above with no restructuring.

**One policy per group using `has_tag` in `WHEN`.** Tag tables `is_finance=yes`, write one policy per group that blocks that group when its tag is absent; no function arguments, no lookup table. Loses because every applicable policy must pass, so a user in `finance` and `hr` querying a finance-only table is blocked by the hr policy; it only works if nobody is in two groups.

**Ungoverned free-text tag with a comma-separated group list.** One plain tag `readers = 'finance,hr'`, a function that splits and checks each. Simplest possible shape, nothing enumerated. Loses because policies require governed tags, governed tags can't take free-form values, and an ungoverned tag could be set by any user with APPLY TAG, letting them grant themselves access.

---

## Sources and verification level

**Opened and read (primary):**
- Databricks Python SDK, `databricks/sdk/service/catalog.py`: `EntityTagAssignment`, `EntityTagAssignmentsAPI`, `PolicyInfo`, `TagIntrospectionExpression`, `TagValueExtraction` (docstring: `get_tag_value("tagKey")`), `Privilege.APPLY_TAG`; and its changelog (`function_arg_expression` added v0.134.0, 2026-09-03; `POLICY_TYPE_DENY` added v0.137.0, 2026-09-09). https://raw.githubusercontent.com/databricks/databricks-sdk-py/main/databricks/sdk/service/catalog.py
- Terraform provider docs: `policy_info`, `tag_policy`, `entity_tag_assignment`, `access_control_rule_set` (`roles/tagPolicy.assigner`), `group_member` (nested groups), `grants`. https://github.com/databricks/terraform-provider-databricks/tree/main/docs/resources
- AbhiDatabricks/DatabricksABACExamples: README and Tutorial 1 notebook (tested `TO account users EXCEPT g1, g2, g3` policies with a `RETURN FALSE` filter). https://github.com/AbhiDatabricks/DatabricksABACExamples
- ryan-rabold-databricks/databricks-control-table-abac: README (governed tags required; one row filter per table; lookup tables read at query time). https://github.com/ryan-rabold-databricks/databricks-control-table-abac

**Official Databricks docs, seen only as search-engine summaries (not opened):**
- ABAC overview: https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/
- Governed tags: https://docs.databricks.com/aws/en/admin/governed-tags/
- Core concepts (incl. `get_tag_value`): https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/core-concepts
- Create and manage policies: https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/policies
- Common patterns (`block_all`, lookup tables): https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/common-patterns
- Mapping tables: https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/mapping-tables
- Secure new tables by default: https://docs.databricks.com/gcp/en/data-governance/unity-catalog/abac/secure-by-default
- Requirements, quotas, limitations: https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/requirements
- Policy evaluation: https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/policy-evaluation
- Best practices: https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/abac/best-practices
- DENY policies: https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/deny-policies
- GRANT policies: https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/grant-policies
- CREATE POLICY: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-policy
- CREATE GOVERNED TAG: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-governed-tag
- ALTER GOVERNED TAG: https://learn.microsoft.com/fil-ph/azure/databricks/sql/language-manual/sql-ref-syntax-ddl-alter-governed-tag
- SET TAG / UNSET TAG: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-set-tag
- SHOW POLICIES: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-show-policies
- Apply tags: https://docs.databricks.com/aws/en/database-objects/tags
- Manage governed-tag permissions: https://learn.microsoft.com/en-us/azure/databricks/admin/governed-tags/manage-permissions
- is_account_group_member: https://docs.databricks.com/aws/en/sql/language-manual/functions/is_account_group_member
- Manage privileges (inheritance, no DENY): https://docs.databricks.com/aws/en/data-governance/unity-catalog/manage-privileges/
- Release notes April 2026 (ABAC GA, view identity change) and September 2026 (DENY Beta, metastore-level policies): https://docs.databricks.com/aws/en/release-notes/product/2026/april , https://docs.databricks.com/aws/en/release-notes/product/2026/september

**Community (unofficial):**
- How to grant all tables in schema except 1: https://community.databricks.com/t5/data-engineering/how-to-grant-all-tables-in-schema-except-1/td-p/107872
- How to override ABAC policies (`WHEN NOT has_tag` pattern): https://community.databricks.com/t5/data-governance/how-to-override-abac-policies/td-p/169705
