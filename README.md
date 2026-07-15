# Debriefly

Debriefly is a web application written using the [Reflex](https://reflex.dev/) framework to manage Cognitive Debriefing Surveys.

A live version of debriefly is currently deployed as [https://www.debriefly.net](https://www.debriefly.net). This deployment uses the [NERC Openshift Platform](https://nerc-project.github.io/nerc-docs/openshift/get-started/openshift-overview/).

Before you can start tweaking `debriefly` code, you should install, run and test the application locally. The following documentation details the procedure for doing so. In particular, **this is not a tutorial on Reflex or Openshift**.
Please refer to Reflex or Openshift documentation for more information on those topics.

## Installation

Ensure that your system meets the following prerequisites:

- Python 3.12 or later
- Pip package manager

Clone the repository and enter it:
   ```
   git clone git@github.com:iqss-research/debriefly.git
   cd debriefly
   ```

### Creating a debriefly environment

All of `debriefly`'s dependencies are on [PyPI](https://pypi.org/). We have developed and tested `debriefly` on Python 3.12, but it should work on later Python versions as well.
You can create a new virtual environment using `venv`, and install dependencies using `pip`.

1. Verify that Python 3.12 or newer is installed on your system.
   ```
   python --version
   ```

2. Create a new environment and activate it.
   ```
   python -m venv .venv
   source .venv/bin/activate
   ```

3. In the activated environment, install all of `debriefly`'s dependencies.
    ```
    pip install -r requirements.txt
    ```

4. In the activated environment, install the debriefly package in editable mode.
    ```
    pip install -e . --no-deps
    ```

### Using a different Python version than the system default

If your Python version is not 3.12 or later, or if you're getting errors when using a non-tested Python version, we recommend using the [uv](https://github.com/astral-sh/uv) tool to create a virtual environment with the correct Python version.
`uv` is quick to [install](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) and easy to use, both locally as well as on research clusters.

Once `uv` is installed:

1. Create a new environment with Python 3.12 and activate it.
   ```
   uv venv --python 3.12
   source .venv/bin/activate
   ```

2. In the activated environment, install all of `debriefly`'s dependencies.
    ```
    uv pip install -r requirements.txt
    ```

3. In the activated environment, install the debriefly package in editable mode.
    ```
    uv pip install -e . --no-deps
    ```

## Running the application

1. Copy `.env.sample` to `.env` and configure local authentication and SMTP. Generate `AUTH_SECRET_KEY` with `openssl rand -hex 32`; do not reuse a database password or an old provider secret. Local Reflex development uses frontend port 3000 and backend port 8000, as shown in the sample.

    **Never commit the `.env` file to the repository**.

   Existing deployments moving away from Clerk must follow the staged [local-auth migration runbook](docs/local-auth-migration.md). Do not deploy the cutover before its dry-run import is conflict-free.


2. In the *activated virtual environment* (see the Installation section above), run the following bash helper script to start the application:
   ```
   ./debriefly
   ```

   This step creates and seeds a local sqlite database (`debriefly.db`) with some starter values, and runs the Reflex application on port 3000.

3. Navigate to [http://localhost:3000](http://localhost:3000) in your browser to see the application running.

4. After signing in, open **OpenAI Key** in the sidebar and save your standard OpenAI API key. Debriefly uses the survey owner's key for debriefing chats; Azure OpenAI keys are no longer configured globally.

5. Modifying the code will automatically reload the application in the browser. As a trivial example, on the `Surveys` page (which should be available at [http://localhost:3000/edit/form](http://localhost:3000/edit/form),
lets try to change the title of the button from `New Survey` to `New Survey!`.

   Modify the file `src/debriefly/reflex/form_designer/pages/form_editor.py` to change the following code that renders a button. Do this in a separate terminal window from where you ran `./debriefly` before, so that we don't kill the running web application.

   ```python
      rx.button(
        "New Survey",
        on_click=rx.redirect(routes.FORM_EDIT_NEW),
        type="button",
      ),
   ```
   to
   ```python
      rx.button(
        "New Survey!",
        on_click=rx.redirect(routes.FORM_EDIT_NEW),
        type="button",
      ),
   ```
   You should see the button label change in your browser. Give it a few seconds since `reflex` will detect changes in the python code and compile it to React code.


## Updating the application

You can make local changes and test them out. Test all possible scenarios and user interactions.

Things to remember at this stage:

- Always work on a new branch prefixed with your initials, e.g. `vb/ui-dropdown-fix`.
- Always make a commit whenever development reaches a stage that you can talk about. For example, \"I implemented stage 1 of the bug fix this commit 06dea3 by adding a function.\"
- Never implement unrelated changes in the same commit!
- As soon as the feature/bug fix is complete, push your branch upstream. Resist the temptation to do extra work in the same branch.
- Open a PR and get it reviewed by someone on the team.
- If you must work on another feature/bug request while your PR is under review, open a new branch and repeat the steps.

### Updating models.py

**Important**: If you made *any* changes to `models.py` and re-ran `./debriefly`, you would have observed that one or more `*.py` files are created in the `alembic/version` folder.
It is important for you to add any such files to the repository, since these will be used by Docker to update the structure of the database that it is connected to.

## Deployment

Production authentication changes require the staged backup, schema migration,
user import, cutover, verification, and rollback procedure in
[the local-auth migration runbook](docs/local-auth-migration.md). Do not switch
the production image before that runbook's dry run is conflict-free.

### Build and publish an image

1. Merge the reviewed release into `main`. The release worktree must be clean,
   and all generated Alembic revisions must be reviewed and committed.
2. Update the same `X.Y.Z` version in `src/debriefly/__init__.py` and
   `pyproject.toml`.
3. Run the full test suite and
   `python3 scripts/check_migration_head.py f6b7c8d9e0a1`.
4. Tag the merged `main` commit with that exact version and push the tag. The
   `deploy` workflow reruns the full tests and rejects a tag whose commit is not
   contained in `main` or whose name differs from the application version.
5. Confirm in GitHub Actions that the Docker build completed rather than being
   skipped, and record the resulting immutable `sha256` digest. Never deploy a
   tag merely because its name exists in GitHub or Docker Hub.

### Import and deploy on OpenShift

The NERC resources currently use the names `debriefly-dockerhub` for both the
ImageStream and Deployment. Replace the project, Docker Hub account, and version
placeholders below:

```sh
oc project <project>

oc import-image debriefly-dockerhub:<version> \
  --from=docker.io/<dockerhub-account>/debriefly:<version> \
  --confirm

oc get istag/debriefly-dockerhub:<version> -o yaml
```

Do not hand-edit an ImageStream's `status` section. OpenShift owns that status;
`oc import-image` creates or refreshes the ImageStreamTag safely.

Before changing the Deployment, record its current image and configuration:

```sh
umask 077
oc get deployment/debriefly-dockerhub -o yaml > pre-cutover-deployment.yaml
oc get deployment/debriefly-dockerhub \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"="}{.image}{"\n"}{end}'
oc get pods \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.name}{"="}{.imageID}{" "}{end}{"\n"}{end}'
```

The Deployment YAML records Secret references, not decoded Secret values. Keep
all pre-cutover runtime Secrets, including Clerk and any Azure settings,
attached or preserved in the approved secret manager until the rollback window
closes.

For an ordinary release, select the imported tag under **Deployment -> Edit
Deployment -> Images**. For an authentication migration, first complete the
maintenance-window final export and one-off import in the migration runbook,
then set the candidate by immutable digest:

```sh
oc set image deployment/debriefly-dockerhub \
  <container-name>=docker.io/<dockerhub-account>/debriefly@sha256:<candidate-digest>
```

Monitor every rollout:

```sh
oc rollout status deployment/debriefly-dockerhub
oc logs deployment/debriefly-dockerhub --since=10m
```

Rollback must be tested against the upgraded schema before the maintenance
window. Build the dedicated Clerk rollback image with the manual **build Clerk
rollback image** workflow and follow the runbook; the unmodified `0.8.0` image
is not compatible with the new Alembic head. Roll back only the application
image by immutable digest, never run an Alembic downgrade during an incident,
and keep the previous authentication provider and its export available until
the validation window closes.
