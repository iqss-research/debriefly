# Local authentication migration runbook

Debriefly now owns its email/password authentication. Existing survey ownership
continues to use the original opaque `user.user_id`; the migration must never
rewrite that key or the `form.user_id` and `user_openai_settings.user_id`
foreign keys that refer to it.

## Before the maintenance window

1. Take and verify a restorable production database backup.
2. Export the Clerk users. A normalized CSV is preferred:

   ```csv
   clerk_user_id,primary_email,email_verified,email_verified_at
   user_abc,person@example.org,true,2026-07-14T12:00:00Z
   ```

   Only a verified primary email can become a local login. Never infer
   verification from the presence of an address.
3. Create a separate OpenShift Secret for local authentication and email. Do
   not replace or delete the existing Clerk or PostgreSQL Secrets during
   cutover. The current NERC Deployment already supplies PostgreSQL as:

   ```text
   DB_HOST=postgresql
   DB_NAME  <- Secret/postgresql key database-name
   DB_USER  <- Secret/postgresql key database-user
   DB_PASS  <- Secret/postgresql key database-password
   ```

   Preserve those references; do not decode or copy the database password into
   the new local-auth Secret. For the new Secret use:

   ```sh
   AUTH_SECRET_KEY="$(openssl rand -hex 32)"
   AUTH_PUBLIC_URL="https://www.debriefly.net"
   AUTH_API_PUBLIC_URL=""
   AUTH_ALLOWED_ORIGINS="https://www.debriefly.net"
   AUTH_COOKIE_SECURE="true"
   AUTH_ALLOW_REGISTRATION="false"
   AUTH_SESSION_HOURS="168"
   AUTH_TOKEN_HOURS="48"
   AUTH_PASSWORD_HASH_CONCURRENCY="2"
   SMTP_HOST="smtp.example.org"
   SMTP_PORT="587"
   SMTP_STARTTLS="true"
   SMTP_SSL="false"
   SMTP_FROM="Debriefly <no-reply@example.org>"
   ```

   These SMTP values must come from a real production mail relay. The local
   development catcher at `127.0.0.1:1025` does not deliver email and must
   never be copied into OpenShift. Do not create the production Secret with
   placeholder SMTP values.

   `AUTH_SECRET_KEY` must remain stable after launch: changing it invalidates
   sessions and outstanding one-time links. Do not log or commit it. Leave
   registration disabled until the Clerk import and ownership checks pass; this
   prevents a new local account from claiming a migrated email during cutover.
   Both production images require PostgreSQL and accept either an explicit
   PostgreSQL `DB_URL` or the complete four-variable configuration above. They
   refuse missing, incomplete, or SQLite production configuration; local
   `./debriefly` development can still use SQLite. Add `SMTP_USERNAME` and
   `SMTP_PASSWORD` to the Secret only when the relay requires authentication.
4. Confirm the public proxy sends `/_event/*` to port 8000 and everything else
   to port 3000. This is already how the application websocket is routed. Keep
   authentication on the same HTTPS origin.
5. Record the Deployment's replica count, container names, and every existing
   runtime Secret reference. Keep the pre-cutover Secrets—including Clerk and
   any Azure configuration—attached alongside the new local-auth Secret until
   the rollback window closes. If policy requires separate rollback Secrets,
   copy them through the approved secret manager, never through this worktree,
   and rehearse restoring them before production cutover.

## Prepare and prove the rollback image

The original `0.8.0` container is not a safe rollback after the schema upgrade:
it does not know the new Alembic head, and its startup command masks migration
failures. Before touching production:

1. Read the image ID from the running pod; do not resolve its mutable tag again:

   ```sh
   oc get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.name}{"="}{.imageID}{" "}{end}{"\n"}{end}'
   ```

   Identify the Debriefly container and record its `@sha256:` reference. Convert
   a `docker-pullable://` prefix to the equivalent `docker.io/` reference if
   needed, while preserving the digest exactly.
2. In GitHub Actions, run **build Clerk rollback image**. Set `release_tag` to
   `0.9.0`, supply the running image's immutable reference as
   `clerk_base_image`, and use `0.9.0-clerk-rollback` as `output_tag`. The
   workflow pins the reviewed release tag, asserts the sole Alembic head, and
   refuses a base that is not the Clerk-backed `0.8.0` application.
3. Record the new rollback image's immutable digest and confirm its
   `debriefly.rollback.base-image` label contains the exact running-pod digest.
   A tag alone is not a rollback artifact.
4. Restore a recent production backup into an isolated staging PostgreSQL
   database. Upgrade it with the `0.9.0` candidate, then start the prepared
   Clerk rollback image with the retained Clerk Secret against that upgraded
   database. Verify that startup succeeds, a Clerk test user can sign in, and
   its existing survey opens.

Do not continue until this rehearsal passes. Do not use the unmodified `0.8.0`
image as the rollback target.

## Add schema while the old application remains live

Run the exact new image digest as a one-off migration job against production,
with the same database environment references as the Deployment, but without
switching web traffic to it. For the current NERC PostgreSQL service, add this
to the migration Job container:

```yaml
env:
  - name: DB_HOST
    value: postgresql
  - name: DB_NAME
    valueFrom:
      secretKeyRef:
        name: postgresql
        key: database-name
  - name: DB_USER
    valueFrom:
      secretKeyRef:
        name: postgresql
        key: database-user
  - name: DB_PASS
    valueFrom:
      secretKeyRef:
        name: postgresql
        key: database-password
```

Then run:

```sh
python3 scripts/apply_schema_migrations.py
```

The `0.9.0` candidate includes both the reviewed human-interview revision
`a3f2b1c4d5e6` and local-auth revision `f6b7c8d9e0a1`; rehearse both features as
one release. The command fails unless the database reaches the code's sole head
and prints `Database schema is current at f6b7c8d9e0a1.` on success. The
revisions after the currently deployed `dc22fdc7aa86` head are additive. The
old Clerk-backed release can keep serving while the new tables exist.

## Final maintenance-window export and import

The earlier Clerk export is for rehearsal only. Before the authoritative import,
prevent the old application from creating users or researcher-owned data. The
safest simple procedure is a short maintenance window:

1. Record the current replica count, scale the Deployment to zero, and confirm
   that its application pods have stopped:

   ```sh
   oc get deployment/debriefly-dockerhub -o jsonpath='{.spec.replicas}{"\n"}'
   oc scale deployment/debriefly-dockerhub --replicas=0
   ```

2. With writes quiesced, take another verified database backup and make a fresh
   Clerk export. Use this final CSV for both the dry run and commit.
3. Create a short-lived Secret for the CSV. The `.dockerignore` deliberately
   excludes CSV files; never add the export to either web image:

   ```sh
   oc create secret generic debriefly-clerk-import \
     --from-file=clerk-users.csv=./clerk-users.csv
   ```

4. Run the importer in a one-off Job using the exact candidate digest. Mount
   `debriefly-clerk-import` read-only at `/var/run/debriefly-import`, and load
   the unchanged production PostgreSQL references. A minimal dry-run container
   is:

   ```yaml
   containers:
     - name: clerk-import
       image: docker.io/<account>/debriefly@sha256:<candidate-digest>
       command: ["python3", "scripts/import_clerk_users.py"]
       args:
         - /var/run/debriefly-import/clerk-users.csv
         - --issuer
         - https://<exact-clerk-issuer>
       env:
         - name: DB_HOST
           value: postgresql
         - name: DB_NAME
           valueFrom:
             secretKeyRef:
               name: postgresql
               key: database-name
         - name: DB_USER
           valueFrom:
             secretKeyRef:
               name: postgresql
               key: database-user
         - name: DB_PASS
           valueFrom:
             secretKeyRef:
               name: postgresql
               key: database-password
       envFrom:
         - secretRef:
             name: debriefly-local-auth
       volumeMounts:
         - name: clerk-export
           mountPath: /var/run/debriefly-import
           readOnly: true
   volumes:
     - name: clerk-export
       secret:
         secretName: debriefly-clerk-import
         defaultMode: 0440
   restartPolicy: Never
   ```

   Place that container and volume spec in a `batch/v1` Job with
   `backoffLimit: 0`. Review `oc logs job/<dry-run-job>` and require a successful
   exit. Delete the completed dry-run Job before creating the commit Job.

Use the exact Clerk issuer from the old project. The importer defaults to a dry
run and refuses ambiguous email/identity mappings, missing database owners, and
orphaned ownership references. The equivalent command inside the dry-run Job
is:

```sh
python scripts/import_clerk_users.py \
  /var/run/debriefly-import/clerk-users.csv \
  --issuer 'https://your-clerk-issuer.example'
```

Do not proceed unless the dry run reports no conflicts and every existing form
or OpenAI-settings owner is covered. Reconcile any reported orphan against the
final backup and source records; never assign it to a guessed user.

Create a second one-off Job from the same reviewed manifest and candidate
digest, adding `--commit` and `--skip-setup-tokens` to its `args`. Because SMTP
is configured, this avoids creating a file of raw one-time tokens. The equivalent
container command is:

```sh
python scripts/import_clerk_users.py \
  /var/run/debriefly-import/clerk-users.csv \
  --issuer 'https://your-clerk-issuer.example' \
  --commit \
  --skip-setup-tokens
```

Imported users then choose **Set up or reset password** on `/signin`; Debriefly
emails the one-time link. Test SMTP from the production namespace before the
maintenance window and verify that the link opens the public frontend URL.

If SMTP is unavailable during an explicitly approved emergency procedure, use
`--setup-token-output /secure/path/password-setup.csv` instead of
`--skip-setup-tokens`. The new output file has mode `0600`; it contains
one-time, expiring raw tokens, while the database stores only keyed digests.
Deliver links through an approved private channel as:

```text
https://www.debriefly.net/reset-password?token=<setup_token>
```

Then securely delete the file. Re-running the same import is supported and does
not change ownership.

After the committed Job succeeds, delete both import Jobs and the short-lived
`debriefly-clerk-import` Secret. Retain the master export only in approved,
encrypted storage for the rollback window; do not leave a copy in a pod, image,
or repository.

Users present in Clerk who never created data in Debriefly are skipped by
default and may register locally. Use `--create-missing-users` only if retaining
those unused accounts is an explicit requirement.

## Assign the first administrator

The CSV cannot grant administrator access. After import, explicitly promote one
verified account using a reviewed database statement:

```sql
UPDATE "user"
SET role = 'admin', updated_at = CURRENT_TIMESTAMP
WHERE email_normalized = 'admin@example.org'
  AND email_verified_at IS NOT NULL
  AND status = 'active';
```

Require exactly one affected row and record who approved the change. The server
checks this role for `/admin`, `/config`, and global-configuration mutations.

## Cut over and verify

1. Attach the new local-auth/SMTP Secret without removing the retained Clerk
   Secret or the existing `postgresql` references. Set the candidate image by
   immutable digest, restore the saved replica count, and wait for rollout:

   ```sh
   oc set image deployment/debriefly-dockerhub \
     <container-name>=docker.io/<account>/debriefly@sha256:<candidate-digest>
   oc scale deployment/debriefly-dockerhub --replicas=<saved-replica-count>
   oc rollout status deployment/debriefly-dockerhub
   ```

   Keep `AUTH_ALLOW_REGISTRATION=false` initially.
2. Verify a migrated account can request a setup link, set a password, sign in,
   see its original surveys, and sign out.
3. Verify a second account cannot open the first account's form, field,
   response, export, analysis, or interview-session URLs.
4. Verify registration is blocked while `AUTH_ALLOW_REGISTRATION=false`, and
   verify forgotten-password, expiration, one-time token replay rejection,
   account lockout, and session revocation.
5. Verify public respondent form, chat, success, and Qualtrics embed routes work
   without signing in.
6. Verify cookies in production are named `__Host-debriefly_session` and have
   `Secure`, `HttpOnly`, `SameSite=Lax`, and `Path=/`.
7. Monitor authentication failures, SMTP delivery, and database load before
   inviting the wider user population.
8. Keep registration disabled throughout the rollback window: a local-only new
   account cannot sign into the Clerk rollback application. After that window
   closes, set `AUTH_ALLOW_REGISTRATION=true` only if public self-registration
   is desired, start a new rollout, and verify registration plus email
   verification. Leave it false for an invitation-only deployment.

Schedule periodic cleanup after reviewing its dry run:

```sh
python scripts/prune_auth_data.py --retention-days 30
python scripts/prune_auth_data.py --retention-days 30 --commit
```

Use PostgreSQL rather than the SQLite development fallback for a multi-replica
or high-concurrency production deployment. Session and token lookups are indexed;
account lockouts and session revocation are stored in the shared database.

Do not delete the old Clerk project or the encrypted master export during the
validation window.

## Rollback

First restore or reattach all retained pre-cutover runtime Secrets, including
the Clerk and any Azure settings, and confirm that both Clerk keys are available
to the pod. Then roll back only the application image to the prepared Clerk
rollback image's immutable digest; do not select the original `0.8.0` tag. For
example:

```sh
oc set image deployment/debriefly-dockerhub \
  <container-name>=docker.io/<account>/debriefly@sha256:<rollback-digest>
oc scale deployment/debriefly-dockerhub --replicas=<saved-replica-count>
oc rollout status deployment/debriefly-dockerhub
oc logs deployment/debriefly-dockerhub --since=10m
```

Keep the additive auth tables and columns in place; do not run an Alembic
downgrade during an incident. Because ownership IDs were preserved, the Clerk
rollback application will find the same users and surveys. Local passwords
cannot be used while it is active, but no survey ownership is lost. Keep the
Clerk tenant enabled until the validation window closes.
