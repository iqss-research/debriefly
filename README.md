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

4. Modifying the code will automatically reload the application in the browser. As a trivial example, on the `Surveys` page (which should be available at [http://localhost:3000/edit/form](http://localhost:3000/edit/form),
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
