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

1. Copy the file `.env.sample` as `.env` in the same folder. Change the values in the `.env` file that are marked as placeholders, with values as `XXXX..`.

   In particular, you will need the real values of `CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY`. Get these values from someone on the `debriefly` development team.
If you're comfortable with setting up a new project on [Clerk](https://www.clerk.dev/), you can create a new project and get the keys yourself.

    **Never commit the `.env` file to the repository**.


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

### Push image to DockerHub

Once your branch is merged to `main` and you want to do a new "release" on the server:

1. Pull the `main` branch and update the files `debriefly/src/debriefly/__init__.py` and `pyproject.toml` to update the version. Use the `X.Y.Z` syntax. Make sure you have identical versions specified in both these files. For bug fixes and minor changes, increment the patch version `Z`. For new features, increment the minor version `Y`. For breaking changes, increment the major version `X`.
   ```
   git pull origin main
   vi debriefly/src/debriefly/__init__.py (make changes)
   vi pyproject.toml (make changes)
   ```


2. Add the changes to the repository, commit them and tag the commit with the *same* version as in the step above.
   ```
   git add debriefly/src/debriefly/__init__.py
   git commit -m"Update version to 0.4.7"
   git tag 0.4.7
   ```

3. Push the commit and tags upstream.
   ```
   git push
   git push --tags
   ```

   This step triggers a `deploy` workflow on GitHub that builds and deploys a containerized version of the application to DockerHub. Check it out in the `Actions` tab of the repository.
   Make sure it completes successfully.


4. In the logs of the `deploy` workflow (click on the gear icon and then \"View raw logs\"), locate the string `containerimage.digest` and make a note of the sha256 value. You will need this later. For example, if the line says:
   ```
   2025-03-27T17:45:28.9415364Z   "containerimage.digest": "sha256:cd623290cea89e38f66a98526a243d4c8dea17c1d4e654003f5f2e392d11de19",
   ```
   Copy the part `sha256:cd623290cea89e38f66a98526a243d4c8dea17c1d4e654003f5f2e392d11de19` and save it for later.

### Pull images on Openshift

Note that there are technically [easier ways](https://crc.dev/docs/introducing/) to do the following, and ways to automate this process. However, the following instructions have been tested out and guaranteed to work.

1. Login to the [NERC Openshift Platform](https://console.apps.shift.nerc.mghpcc.org/)


2. One the left hand menu, go to `Project` and then click on `1 Deployment` on the right hand panel. The URL will look something like `https://console.apps.shift.nerc.mghpcc.org/../automated-cognitive-debriefing-6e6c7f/deployments`


3. Change the `/deployments` in the address bar to `/imagestreams` and hit enter. *If you find an easier way to get to this URL, please update these instructions.*


4. Go to the ImageStream called `debriefly-dockerhub` by click on it. Click on `YAML` to make tweaks to the YAML.


5. **Be very careful** at this point. This step involves editing a YAML file and you don't want to make mistakes and bring down the whole system!


6. Under `spec` -> `tags`, locate a section of the YAML that looks like follows. Navigate to last such section, which should correspond to the latest available version of the application on NERC. For example:
    ```
    - name: 0.4.6
      annotations: null
      from:
        kind: DockerImage
        name: 'docker.io/vineetbansal/debriefly:0.4.6'
      generation: 21
      importPolicy:
        importMode: Legacy
      referencePolicy:
        type: Source
    ```


7. Copy over the section and paste it right below it. Update the 2 `name` fields to point to the version of the application that you deployed on DockerHub. Increment the `generation` by 1. For the example above, it will now look like:
    ```
    - name: 0.4.6
      annotations: null
      from:
        kind: DockerImage
        name: 'docker.io/vineetbansal/debriefly:0.4.6'
      generation: 21
      importPolicy:
        importMode: Legacy
      referencePolicy:
        type: Source
    - name: 0.4.7
      annotations: null
      from:
        kind: DockerImage
        name: 'docker.io/vineetbansal/debriefly:0.4.7'
      generation: 22
      importPolicy:
        importMode: Legacy
      referencePolicy:
        type: Source
    ```


6. Under `status` -> `tags`, locate a section of the YAML that looks like follows. Navigate to last such section, which should correspond to the latest available version of the application on NERC. For example:
    ```
    - tag: 0.4.6
      items:
        - created: '2025-03-25T22:20:44Z'
          dockerImageReference: 'docker.io/vineetbansal/debriefly@sha256:739c7f0650c34b58ac51b79abc26e61f0aa1b8034f89481955b345cc333d7504'
          image: 'sha256:739c7f0650c34b58ac51b79abc26e61f0aa1b8034f89481955b345cc333d7504'
          generation: 21
    ```


7. Copy over the section and paste it right below it. Update the `tag` fields to point to the version of the application that you deployed on DockerHub. Update the 2 `sha256:..` occurrences to match the `sha256:..` string that you copied in the `Push image to DockerHub` section. Increment the `generation` so it matches the one you created a couple of steps ago. For the example above, it will now look like:
    ```
    - tag: 0.4.6
      items:
        - created: '2025-03-25T22:20:44Z'
          dockerImageReference: 'docker.io/vineetbansal/debriefly@sha256:739c7f0650c34b58ac51b79abc26e61f0aa1b8034f89481955b345cc333d7504'
          image: 'sha256:739c7f0650c34b58ac51b79abc26e61f0aa1b8034f89481955b345cc333d7504'
          generation: 21
    - tag: 0.4.7
      items:
        - created: '2025-03-25T22:20:44Z'
          dockerImageReference: 'docker.io/vineetbansal/debriefly@sha256:cd623290cea89e38f66a98526a243d4c8dea17c1d4e654003f5f2e392d11de19'
          image: 'sha256:cd623290cea89e38f66a98526a243d4c8dea17c1d4e654003f5f2e392d11de19'
          generation: 22
    ```


8. Hit `Save`.


9. Navigate to `Project` -> `1 Deployment` -> `debriefly-dockerhub`. Click on `Actions` -> `Edit Deployment`.


10. Under `Edit Deployment` -> `Images`, you should see the new tag under the `Tag` dropdown. Select the new tag and hit `Save`.


#### Tips

- Give the NERC Openshift Platform a few minutes to pull the new image and restart the application. You can monitor progress in the `Topology` page if you want.
- If the application doesn't behave like you expect, you can always rollback to the previous version by selecting the previous tag from the `Tag` dropdown and hitting `Save`.
