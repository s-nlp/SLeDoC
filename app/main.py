import gradio as gr
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import align_docs as ad
from app import convert_to_our_format as conv
from app import full_pipeline as fp
from app import full_pipeline_new as fp_new
from app import nli
from app import nli_predict as np
from app import pipeline as mp
from app import pipeline_llm as pll
from app import semantic_mismatch as sm

app = FastAPI()

gr.mount_gradio_app(app, nli.demo, path="/nli", root_path="/nli")
gr.mount_gradio_app(app, sm.demo, path="/mismatch", root_path="/mismatch")
gr.mount_gradio_app(app, np.demo, path="/nli-predict", root_path="/nli-predict")
gr.mount_gradio_app(app, conv.demo, path="/convert", root_path="/convert")
gr.mount_gradio_app(app, ad.demo, path="/align", root_path="/align")
gr.mount_gradio_app(app, fp.demo, path="/full_pipeline", root_path="/full_pipeline")
gr.mount_gradio_app(app, pll.demo, path="/pipeline-llm", root_path="/pipeline-llm")
gr.mount_gradio_app(app, mp.demo, path="/pipeline", root_path="/pipeline")
gr.mount_gradio_app(app, fp_new.demo, path="/", root_path="/pipeline-llm-new")


@app.get("/manifest.json")
def manifest():
    return JSONResponse(
        {
            "name": "Semantic Mismatch",
            "short_name": "Mismatch",
            "display": "standalone",
            "start_url": "/",
            "icons": [],
        }
    )
