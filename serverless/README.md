# Debriefly on Lambda: local review

This implementation keeps the existing Reflex pages, components, styles, survey
logic, authentication, OpenAI interviews, analysis, exports, and Qualtrics
integration. It changes how the browser sends events and how temporary browser
state survives between requests. No deployment or AWS resource change is part of
building or reviewing these files.

The proposed AWS architecture is:

```text
Browser → CloudFront → S3 static Reflex frontend
                   → API Gateway streaming REST API → Lambda
                                                        ├─ PostgreSQL
                                                        ├─ OpenAI
                                                        └─ SMTP
```

Lambda runs the original Python event handlers through AWS Lambda Web Adapter.
Each browser action opens a short-lived HTTP response stream. Existing Reflex
state updates, including streamed AI answers and browser actions such as
downloads, redirects, and Qualtrics `postMessage` events, travel through that
stream. There is no persistent WebSocket connection or waiting interview timer
invocation. The timer uses brief followup requests while an interview is open.

PostgreSQL continues to hold users, credentials, surveys, responses, transcripts,
model/prompt provenance, and OpenAI settings. A separate `lambda_reflex_state`
table holds signed temporary UI snapshots with a 24-hour inactivity lifetime.
Snapshots preserve the complete Reflex parent/child state graph and use
PostgreSQL advisory locks to serialize a browser tab's requests. Changing the
state version starts fresh UI sessions; it does not delete survey records.

This removes the need for continuously running frontend/backend application
containers in a future Lambda deployment. Lambda is also billed by usage.
PostgreSQL, network egress infrastructure, storage, logs, email, and OpenAI can
still incur charges, including baseline charges for resources kept running.
See the [infrastructure proposal](../../debriefly-infra/lambda/README.md) for
the AWS prerequisites and cost considerations.

## Build and open the local review

Run these commands from the `debriefly` directory with the existing pinned
Python dependencies installed. See the main [installation guide](../README.md#install)
if the virtual environment is not ready.

```sh
source .venv/bin/activate
python serverless/build_frontend.py
python -m debriefly.serverless.preview --frontend serverless/dist
```

Open the `http://localhost:8080` address printed by the review server. Sign in as
`reviewer@example.test` using the randomly generated password printed in the
terminal. The account is a local administrator so both researcher and admin
screens can be inspected. The server listens only on the local machine.

Startup prints three progress stages while loading dependencies, preparing the
review database, and starting the server. Wait until `Uvicorn running on ...`
appears before opening the URL. The Alembic plugin `INFO` messages during loading
are normal. Pressing Ctrl+C stops startup or the running server.

The review server creates a new temporary SQLite database by default. It
overrides inherited deployment database, secret-manager, and SMTP settings, and
does not load the project's `.env`. Registration email, verification email,
password-reset email, and feedback delivery are disabled in this local preview.
Use **OpenAI Key** to enter your own key if you want to exercise actual AI
interviews and analysis; those calls use your normal OpenAI account.

To keep local review surveys across restarts, explicitly select a separate
database file:

```sh
python -m debriefly.serverless.preview \
  --frontend serverless/dist \
  --database /tmp/debriefly-lambda-review.db
```

Use the newly printed password after each restart. Do not point `--database` at
an existing application database. To use another port, add `--port 8081` and open
the exact localhost URL printed by the server.

The frontend build modifies generated `.web` files and copies the static result
to `serverless/dist`. It does not modify page designs, upload files, or contact
AWS. Rebuild after changing Python pages or the browser transport. The adapter
deliberately requires the pinned `reflex==0.5.10` runtime; review the integration
before upgrading Reflex.

If the frontend dependencies are already installed in `.web/node_modules`, use
`python serverless/build_frontend.py --skip-install` to rebuild without running
the dependency installer again.

The preview serves a compiled export and does not automatically rebuild source
changes. After editing the version number, pages, styles, or assets, run:

```sh
.venv/bin/python serverless/build_frontend.py --skip-install
```

Then refresh the browser. The running preview reads the rebuilt files directly,
so this keeps its current review database and login. If you also change backend
Python handlers, restart the preview; pass the database path printed by the
previous run with `--database` to keep your review surveys and responses.

## Functionality and appearance review

Compare the local preview with the current application at the same browser
width. Use a new local survey containing the field types used by your actual
studies.

| Area | Review |
| --- | --- |
| Appearance | Landing page, sidebar, logos, fonts, colors, responsive widths, dialogs, field editor, chat bubbles, and action bars. |
| Researcher access | Sign in, sign out, protected-page redirects, OpenAI model/key settings, and admin pages. |
| Survey design | Create, rename, copy, reorder, edit, and delete a survey; edit options, required fields, bundled items, page breaks, prompts, timer limits, and submission-code settings. |
| Participant flow | Open a survey through its direct `/form/<code>` link; check validation, page navigation/back rules, preview mode, debriefing transitions, completion, and submission codes. |
| AI interviews | Initial/custom prompts, streamed answers, loading states, minimum/maximum interview time, inactivity pause/resume, End Chat, and missing/invalid API-key messages. |
| Responses | Saved answers and transcripts, bundled fields, interview model/prompt provenance, response deletion, CSV download, transcript download, and AI analysis. |
| Qualtrics | Embedded single-question interview and full-survey workflow, original response/question IDs, optional interview resume, iframe sizing, and ready/error/complete messages to the parent survey. |
| Navigation | Paste and refresh dynamic form, editor, response, and analysis URLs; navigate between them and use browser back/forward. |
| Continuity | Refresh during normal editing, restart the review server with the same review database, and confirm saved surveys/responses remain available. Temporary UI state and saved study data have separate lifetimes. |

Email flows require an isolated staging environment configured with test SMTP
and a PostgreSQL copy. Local preview deliberately reports unavailable delivery
instead of sending mail. Likewise, actual AWS cold-start latency, PostgreSQL
concurrency, internet egress, and streaming through API Gateway/CloudFront must
be verified in a separately approved staging deployment. Local checks do not
establish production behavior for those services.

The interview timer retains five-second accounting and the existing
120-second inactivity threshold. Existing activity tracking refreshes on answer
submission. A late timer request accounts for eligible elapsed ticks using
server time. Closing or leaving the interview stops browser timer requests.
Once the inactivity warning appears, polling stops until the next answer is
submitted, so an abandoned open tab does not keep invoking Lambda.

## Automated checks

Use Node.js 22 or newer for the JavaScript test harness. This does not change
the Node version used by the existing Reflex frontend build.

```sh
python -m pytest tests/test_lambda_runtime.py
node --test serverless/frontend/request_transport.test.mjs
```

The backend tests exercise real Reflex generators, streamed state/client
events, snapshots across fresh runtimes, parent/child state restoration, token
isolation, trusted cookie/origin handling, protected-event authorization,
snapshot signatures/expiry/versioning, and timer behavior. The frontend tests
cover the browser transport's stream handling and lifecycle behavior. Run the
existing application suite as well when changing application handlers.

## Validation completed

Local validation completed on October 15, 2026: the production static export,
Python application tests, browser-transport tests, infrastructure tests, and SAM
schema/lint validation passed. A headless browser exercised sign-in, consent,
survey creation, question editing/saving, copying the survey URL, anonymous
submission, viewing persisted results, downloading a CSV with the submitted
answer, and opening account settings and legal pages without JavaScript errors.
The Qualtrics embed route was also checked for its missing-configuration state;
a real embedded Qualtrics study still needs the acceptance checks above.

The Docker image was not built because no Docker daemon was running. No AWS
deployment, real OpenAI completion, or SMTP delivery was performed. PostgreSQL
locking/concurrency and AWS request streaming need a later staging check.

## Files and future database preparation

| File | Purpose |
| --- | --- |
| `Dockerfile.lambda` | Backend Lambda image using the pinned Web Adapter; no frontend server or startup migrations. |
| `src/debriefly/serverless/runtime.py` | Runtime configuration and existing application entry point. |
| `src/debriefly/serverless/transport.py` | Request authorization, streamed Reflex events, and short timer requests. |
| `src/debriefly/serverless/state.py` | Signed temporary state snapshots and transactional locks. |
| `src/debriefly/serverless/preview.py` | Isolated local review server and static dynamic-route handling. |
| `serverless/build_frontend.py` | Export the existing frontend with the request transport. |
| `serverless/prepare_database.py` | Explicit schema preparation or expired-snapshot cleanup for a configured database. |
| `../debriefly-infra/lambda/` | Separate, undeployed infrastructure proposal. |

`prepare_database.py --apply` writes migrations, seed configuration, and the
temporary snapshot table to the configured database. `--cleanup` deletes expired
UI snapshots. Neither operation runs automatically on a Lambda cold start.
These are operator commands for a future approved environment; they are not
needed for local preview and must not be run against the current live database
during review.

Before any future cutover, back up the current database, test with a staging
copy, verify every relevant review item, and plan how to stop new interviews
during the switch. Keep the current hosting available for rollback until the
replacement is accepted. The new static frontend and backend must be released
together, and UI state should be versioned when handler/state structures change.
