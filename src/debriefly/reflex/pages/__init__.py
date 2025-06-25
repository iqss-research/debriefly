import reflex as rx

# Add these dynamic route vars early, so they can be referenced in the titles.
if "form_id" not in rx.State.__fields__:
    rx.State.add_var("form_id", str, "")
if "field_id" not in rx.State.__fields__:
    rx.State.add_var("field_id", str, "")


from debriefly.reflex.pages.index import index
from debriefly.reflex.pages.user import user
from debriefly.reflex.pages.config import config
from debriefly.reflex.pages.chat import chat
from debriefly.reflex.pages.form_designer import (
    _field_edit_id,
    _field_edit_new,
    _form_edit_id,
    _form_edit_new,
    _form_entry,
    _form_entry_chat,
    _form_entry_success,
    _responses,
)

from debriefly.reflex.pages.feedback import feedback_page

from debriefly.reflex.pages.terms import terms_of_service

from debriefly.reflex.pages.privacy import privacy_statement

from debriefly.reflex.pages.admin import admin

from debriefly.reflex.pages.consent import consent

# specify pages that are loaded by default
__all__ = [
    "index",
    "user",
    "config",
    "chat",
    "_field_edit_id",
    "_field_edit_new",
    "_form_edit_id",
    "_form_edit_new",
    "_form_entry",
    "_form_entry_chat",
    "_form_entry_success",
    "_responses",
    "terms_of_service",
    "privacy_statement",
    "feedback_page",
    "admin",
    "consent",
]
