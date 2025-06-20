import gradio as gr
from fastapi import FastAPI

from app import nli
from app import nli_predict as np
from app import pipeline as mp
from app import semantic_mismatch as sm

app = FastAPI()

gr.mount_gradio_app(app, nli.demo, path="/nli", root_path="/nli")
gr.mount_gradio_app(app, sm.demo, path="/mismatch", root_path="/mismatch")
gr.mount_gradio_app(app, np.demo, path="/nli-predict", root_path="/nli-predict")

gr.mount_gradio_app(app, mp.demo, path="/", root_path="/")
