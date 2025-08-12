
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import gradio as gr
import torch
from docx import Document
from lxml import etree
from torch import Tensor
from transformers import AutoModel, AutoTokenizer

from .settings import nav_tag, side_bar


# -------------------- text extraction & segmentation --------------------
def get_paragraphs_from_docx(docx_path: str | Path) -> List[str]:
    """Extract visible paragraphs from a .docx using lxml for robustness."""
    doc = Document(docx_path)
    paragraphs = []

    for part in doc.part._package.parts:
        if part.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml":
            tree = etree.fromstring(part.blob)
            namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            for para in tree.xpath(".//w:p", namespaces=namespaces):
                texts = para.xpath(".//w:t", namespaces=namespaces)
                full_text = "".join([t.text for t in texts if t.text])
                if full_text and full_text.strip():
                    paragraphs.append(full_text.strip())
    return paragraphs


def merge_incomplete_sentences(lines: Iterable[str]) -> List[str]:
    merged: List[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not merged:
            merged.append(line)
            continue

        starts_lower = line[:1].lower() == line[:1]
        prev_ends_semicolon = merged[-1].strip().endswith(";")

        if starts_lower or prev_ends_semicolon:
            merged[-1] += " " + line
        else:
            merged.append(line)
    return merged


def separate_points(paragraphs: Iterable[str]) -> List[str]:
    results: List[str] = []
    pattern = r"(?:ГЛАВА\s+\d+\.|\d+(?:\.\d+){0,2}\.)(?=\s[А-ЯЁ]|[А-ЯЁ])"
    for paragraph in paragraphs:
        modified = re.sub(pattern, r"\n", paragraph)
        for segment in modified.split("\n"):
            cleaned = segment.strip()
            if cleaned:
                results.append(cleaned)
    return results


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
        tok = AutoTokenizer.from_pretrained(model_id)
        mdl = AutoModel.from_pretrained(model_id).to(device)
        return cls(tok, mdl, device)

    @torch.no_grad()
    def encode(self, texts: List[str], batch_size: int = 64, prefix: str = "query:") -> torch.Tensor:
        out = []
        for i in range(0, len(texts), batch_size):
            batch = [f"{prefix} {t}" for t in texts[i : i + batch_size]]
            enc = self.tok(batch, return_tensors="pt", padding=True, truncation=True, max_length=512).to(self.device)
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

    paragraphs_a = merge_incomplete_sentences(get_paragraphs_from_docx(p1))
    paragraphs_b = filter_non_russian(separate_points(merge_incomplete_sentences(get_paragraphs_from_docx(p2))))

    enc = Encoder.load(model_id=model_id, device=device)
    emb_a = enc.encode(paragraphs_a, batch_size=batch_size)
    emb_b = enc.encode(paragraphs_b, batch_size=batch_size)

    matches = find_best_matches_with_window(
        paragraphs_a, paragraphs_b, emb_a, emb_b, window_size=window_size, threshold=threshold
    )

    data = build_output_json(paragraphs_a, paragraphs_b, matches)
    out_path = Path("example_data") / "paragraphs_aligned.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Preview: show top 5
    preview = json.dumps(data[:5], ensure_ascii=False, indent=2)
    return str(out_path), preview

def build_demo():
    with gr.Blocks(title="Step‑0: Align documents", css=side_bar, theme=gr.themes.Soft()) as demo:
        gr.HTML(nav_tag)
        gr.Markdown("### Step‑0 · Align documents (.docx → pairs JSON)\n"
                    "Upload two DOCX files. We'll align their paragraphs using multilingual-e5 embeddings "
                    "and save a JSON list of `{paragraph_1, paragraph_2}` for Stage‑1 (Claims).")
        with gr.Row():
            doc1 = gr.File(label="Document A (.docx)", file_types=[".docx"])
            doc2 = gr.File(label="Document B (.docx)", file_types=[".docx"])
        with gr.Row():
            model_id = gr.Dropdown(
                choices=[
                    "intfloat/multilingual-e5-large",
                    "intfloat/multilingual-e5-base",
                ],
                value="intfloat/multilingual-e5-large",
                label="Embedding model",
            )
            device = gr.Dropdown(choices=["cpu", "cuda"], value="cpu", label="Device")
        with gr.Row():
            batch_size = gr.Slider(8, 128, value=64, step=8, label="Batch size")
            window_size = gr.Slider(5, 200, value=50, step=5, label="Window size")
            threshold = gr.Slider(0.5, 0.99, value=0.90, step=0.01, label="Similarity threshold")
        run_btn = gr.Button("Compute alignment", variant="primary")
        out_path = gr.Textbox(label="Saved JSON file", interactive=False)
        preview = gr.Code(label="Preview (first 5 pairs)", language="json")

        run_btn.click(_align, inputs=[doc1, doc2, model_id, device, batch_size, window_size, threshold], outputs=[out_path, preview])
    return demo

demo = build_demo()
