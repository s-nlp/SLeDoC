import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import gradio as gr
import torch
from docx import Document
from torch import Tensor
from transformers import AutoModel, AutoTokenizer

from .settings import SIDEBAR_CSS, nav_tag


# -------------------- text extraction & segmentation --------------------
def get_paragraphs_from_docx(docx_path: str | Path) -> List[str]:
    """
    Return one string per DOCX paragraph (no cross-paragraph merging).
    Empty paragraphs are skipped by default.
    """
    doc = Document(docx_path)
    out: List[str] = []
    for p in doc.paragraphs:
        # p.text already concatenates all runs in the paragraph
        text = re.sub(r"\s+", " ", (p.text or "")).strip()
        if text:  # keep this True if you want to drop blank lines
            out.append(text)
        # else: if you need to *preserve* blank separators, append "" here
    return out


def merge_incomplete_sentences(lines: Iterable[str]) -> List[str]:
    """
    Merge broken lines *within the same paragraph*, but never glue
    separate paragraphs together. This function expects `lines` to be
    paragraph strings already (i.e., output of get_paragraphs_from_docx).
    """
    merged: List[str] = []
    end_pat = re.compile(r'[.!?…»)"\]]\s*$')  # typical sentence closers

    for para in lines:
        para = para.strip()
        if not para:
            continue

        # If your upstream sometimes splits a single paragraph into several
        # lines, you can merge those here based on punctuation. If not needed,
        # simply append the paragraph.
        if merged and not end_pat.search(merged[-1]):
            merged[-1] = (merged[-1] + " " + para).strip()
        else:
            merged.append(para)

    return merged


def separate_points(paragraphs: Iterable[str]) -> List[str]:
    """
    Split bullet/numbered points but never join across paragraphs.
    """
    out: List[str] = []
    for p in paragraphs:
        # Example rule: split on "^\s*\d+\.\s+" or bullets — tweak to your docs.
        parts = re.split(r"(?:^|(?<=\n))\s*(?=\d+\.\s+|•\s+|- )", p)
        for part in parts:
            part = part.strip()
            if part:
                out.append(part)
    return out


def filter_non_russian(lines: Iterable[str]) -> List[str]:
    return [line for line in lines if re.search(r"[а-яА-ЯёЁ]", line)]


# -------------------- embeddings --------------------
def average_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
    last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
    return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]


@dataclass
class Encoder:
    tok: AutoTokenizer
    mdl: AutoModel
    device: str = "cpu"

    @classmethod
    def load(cls, model_id: str, device: str = "cpu") -> "Encoder":
        local_path = os.getenv("E5_MODEL_PATH", model_id)
        offline = os.getenv("TRANSFORMERS_OFFLINE", "0") == "1"
        kwargs = {"local_files_only": offline}
        tok = AutoTokenizer.from_pretrained(local_path, **kwargs)
        mdl = AutoModel.from_pretrained(local_path, **kwargs)
        mdl.eval()
        return cls(tok, mdl, device)

    @torch.no_grad()
    def encode(
        self, texts: List[str], batch_size: int = 64, prefix: str = "query:"
    ) -> torch.Tensor:
        out = []
        for i in range(0, len(texts), batch_size):
            batch = [f"{prefix} {t}" for t in texts[i : i + batch_size]]
            enc = self.tok(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            ).to(self.device)
            model_out = self.mdl(**enc)
            emb = average_pool(model_out.last_hidden_state, enc["attention_mask"])
            # normalize (cosine sim = dot product)
            emb = torch.nn.functional.normalize(emb, p=2, dim=1)
            out.append(emb.detach().cpu())
        return torch.cat(out, dim=0)


# -------------------- alignment --------------------
def find_best_matches_with_window(
    paragraphs: List[str],
    paragraphs_bi: List[str],
    paragraphs_embs: torch.Tensor,
    paragraphs_bi_embs: torch.Tensor,
    window_size: int = 50,
    threshold: float = 0.9,
) -> List[Tuple[int, int, float]]:
    n_a = len(paragraphs)
    n_b = len(paragraphs_bi)
    results: List[Tuple[int, int, float]] = []
    for i in range(n_a):
        estimated_j = int(i * n_b / n_a)
        start = max(0, estimated_j - window_size)
        end = min(n_b, estimated_j + window_size + 1)
        candidates = paragraphs_bi_embs[start:end]
        sim_scores = (paragraphs_embs[i].unsqueeze(0) @ candidates.T).squeeze(0)
        best_idx_in_window = int(sim_scores.argmax().item())
        best_sim = float(sim_scores[best_idx_in_window].item())
        if best_sim >= threshold:
            j = start + best_idx_in_window
            results.append((i, j, best_sim))
    return results


def build_output_json(
    paragraphs_a: List[str],
    paragraphs_b: List[str],
    matches: List[Tuple[int, int, float]],
) -> list:
    out = []
    for i, j, s in matches:
        out.append(
            {
                "paragraph_1": paragraphs_a[i],
                "paragraph_2": paragraphs_b[j],
                "score": s,
            }
        )
    return out


# -------------------- UI --------------------
def _align(doc1, doc2, model_id, device, batch_size, window_size, threshold):
    if not (doc1 and doc2):
        raise gr.Error("Please upload both .docx files.")
    p1 = Path(doc1.name if hasattr(doc1, "name") else doc1)
    p2 = Path(doc2.name if hasattr(doc2, "name") else doc2)

    paragraphs_a = separate_points(
        merge_incomplete_sentences(get_paragraphs_from_docx(p1))
    )
    paragraphs_b = separate_points(
        merge_incomplete_sentences(get_paragraphs_from_docx(p2))
    )

    enc = Encoder.load(model_id=model_id, device=device)
    emb_a = enc.encode(paragraphs_a, batch_size=batch_size)
    emb_b = enc.encode(paragraphs_b, batch_size=batch_size)

    matches = find_best_matches_with_window(
        paragraphs_a,
        paragraphs_b,
        emb_a,
        emb_b,
        window_size=window_size,
        threshold=threshold,
    )

    data = build_output_json(paragraphs_a, paragraphs_b, matches)
    # Write to a writable temp dir (mirrors the Convert step behavior)
    tmp_dir = Path(tempfile.mkdtemp(prefix="aligned_pairs_"))
    fname = f"aligned_{p1.stem}__{p2.stem}.json"
    out_path = tmp_dir / fname
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Preview: show top 5
    preview = json.dumps(data[:5], ensure_ascii=False, indent=2)
    # DownloadButton expects a *file path* and to be made visible
    return gr.update(value=str(out_path), visible=True), preview


def build_demo():
    with gr.Blocks(
        title="Step‑0: Align documents", css=SIDEBAR_CSS, theme=gr.themes.Soft()
    ) as demo:
        gr.HTML(nav_tag)
        gr.Markdown(
            "### Step‑0 · Align documents (.docx → pairs JSON)\n"
            "Upload two DOCX files. We'll align their paragraphs using multilingual-e5 embeddings "
            "and save a JSON list of `{paragraph_1, paragraph_2}` for Stage‑1 (Claims)."
        )
        with gr.Row():
            doc1 = gr.File(label="Document A (.docx)", file_types=[".docx"])
            doc2 = gr.File(label="Document B (.docx)", file_types=[".docx"])
        with gr.Row():
            model_id = gr.Dropdown(
                choices=[
                    "intfloat/multilingual-e5-large",
                    "intfloat/multilingual-e5-base",
                ],
                value="intfloat/multilingual-e5-base",
                label="Embedding model",
            )
            device = gr.Dropdown(choices=["cpu", "cuda"], value="cpu", label="Device")
        with gr.Row():
            batch_size = gr.Slider(8, 128, value=64, step=8, label="Batch size")
            window_size = gr.Slider(5, 200, value=50, step=5, label="Window size")
            threshold = gr.Slider(
                0.5, 0.99, value=0.90, step=0.01, label="Similarity threshold"
            )
        run_btn = gr.Button("Compute alignment", variant="primary")
        download = gr.DownloadButton(label="Download aligned JSON", visible=False)
        preview = gr.Code(label="Preview (first 5 pairs)", language="json")

        run_btn.click(
            _align,
            inputs=[doc1, doc2, model_id, device, batch_size, window_size, threshold],
            outputs=[download, preview],
        )
    return demo


demo = build_demo()
