FROM python:3.10

EXPOSE 7860

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user . /app

RUN pip install -e .[dev]

ENV GRADIO_SERVER_NAME="0.0.0.0"
CMD ["python", "app.py"]
