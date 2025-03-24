FORM_ENTRY = "/form/[form_code]"
FORM_ENTRY_CHAT = "/form/chat"
FORM_ENTRY_SUCCESS = "/form/success"
FORM_EDIT_NEW = "/edit/form/"
FORM_EDIT_ID = "/edit/form/[form_id]"
FIELD_EDIT_NEW = "/edit/form/[form_id]/field/"
FIELD_EDIT_ID = "/edit/form/[form_id]/field/[field_id]"
RESPONSES = "/responses/[form_id]"
RESPONSES_ANALYZE = "/responses/[form_id]/analyze"
FEEDBACK = "/feedback"
TERMS = "/terms"


def edit_form(form_id: int | str):
    return f"/edit/form/{form_id}"


def edit_field(form_id: int | str, field_id: int | str):
    return f"/edit/form/{form_id}/field/{field_id}"


def show_form(form_code: str):
    return f"/form/{form_code}"


def form_responses(form_id: int | str):
    return f"/responses/{form_id}"


def form_responses_analyze(form_id: int | str):
    return f"/responses/{form_id}/analyze"
