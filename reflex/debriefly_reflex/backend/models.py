from typing import Optional
import reflex as rx


class Profile(rx.Model, table=True):
    user_id: str
    qualtrics_api_token: Optional[str] = None
    qualtrics_client_id: Optional[str] = None
    qualtrics_client_secret: Optional[str] = None
    qualtrics_data_center: Optional[str] = None


class Question(rx.Model, table=True):
    user_id: str
    question_text: str
