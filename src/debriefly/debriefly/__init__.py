"""
This module exists solely to make `reflex run` work from the root
of the project, since reflex looks for the main `rx.App` object as
`<app_name>.<app_name>.app`
"""

from debriefly.reflex import app  # noqa: F401
