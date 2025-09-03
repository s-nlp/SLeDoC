# app/pipeline_llm.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import gradio as gr
import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.convert_to_our_format import LABEL_MAP_DEFAULT
from app.openai_client import make_client
from app.settings import nav_tag, side_bar

# ─────────────────────────────────────────────────────────────────────────────
# Твой системный промпт (без изменений)
SYSTEM_PROMPT = """Ты — юридический аналитик, который разбивает два сложных юридических параграфа на минимальные смысловые единицы и проводит соответствия между ними.

Твоя задача – сегментировать оба параграфа на соответствующие спаны, провести между ними соответствия и указать класс этого соответствия.
Используй три класса: EQUIVALENT, CONTRADICTION и ADDITION.
EQUIVALENT означает, что спаны соответствуют друг дургу.
CONTRADICTION означает, что спаны относятся к одному сегменту, но имеют немного разный смысл.
ADDITION означает, что сегмент представляет собой совсем новую информацию. Для ADDITION нужно дополнительно извлечь anchor – фраза, к которой относится дополненный сегмент.
Не путай CONTRADICTION и ADDITION: CONTRADICTION изменяет существующую в сегменте информацию, а ADDITION добавляет совсем новую.

Предоставь небольшой ризонинг с логикой перед тем как указать лейбл для совпадающего спана.
Спан обязательно должен быть скопирован из текста, ты не можешь никак переписать полученный спан.
Не пиши никаикх объяснений. В качестве ответа выдай только готовый JSON в нужном формате.

Формат ответа:
[
  {
    "span_1": "<исходный кусок текста из первого параграфа>",
    "span_2": "<исходный кусок текста из второго параграфа>",
    "reasoning": "<рассуждения о том, в чем отличаются спаны>"
    "label": "<лейбл соответствия (equivalent / contradiction / addition)>",
    "anchor": "<фраза, к которой относится addition, если он выбран>"
  }
]

Пример 1:
Параграф 1: 3) земельных участков, образованных из земельного участка, предоставленного некоммерческой организации, созданной гражданами, для ведения садоводства, огородничества, дачного хозяйства (за исключением земельных участков, отнесенных к имуществу общего пользования), членам этой некоммерческой организации;
Параграф 2: 3) земельных участков, образованных из земельного участка, предоставленного садоводческому или огородническому некоммерческому товариществу, за исключением земельных участков общего назначения, членам такого товарищества;

Твой ответ:
[
    {
        "span_1": "3) земельных участков, образованных из земельного участка",
        "span_2": "3) земельных участков, образованных из земельного участка",
        "reasoning": "спаны идентичны",
        "label": "equivalent"
    },
    {
        "span_1": "предоставленного некоммерческой организации, созданной гражданами, для ведения садоводства, огородничества, дачного хозяйства",
        "span_2": "предоставленного садоводческому или огородническому некоммерческому товариществу",
        "reasoning": "Первый спан говорит о некоммерческой организации, созданной гражданами, а второй – о некоммерческом товариществе.\nВо втором спане отсутствует дачное хозяйство. ",
        "label": "contradiction"
    },
    {
        "span_1": "(за исключением земельных участков, отнесенных к имуществу общего пользования), членам этой некоммерческой организации;",
        "span_2": "за исключением земельных участков общего назначения, членам такого товарищества;",
        "reasoning": "В первом спане упоминается некоммерческая организация, а во втором – товарищество.\nПервый спан исключает земельные участки общего пользования, а второй – общего назначения.",
        "label": "contradiction"
    }
]

Пример 2:
Параграф 1: 5) Земельного участка, образованного из земельного участка, находящегося в государственной или муниципальной собственности, в том числе предоставленного для комплексного освоения территории, лицу, с которым был заключен договор аренды такого земельного участка, если иное не предусмотрено подпунктами 6 и 8 настоящего пункта, пунктом 5 статьи 46 настоящего Кодекса;
Параграф 2: 5) Земельного участка, образованного из земельного участка, находящегося в государственной или муниципальной собственности, в том числе предоставленного для комплексного развития территории, лицу, с которым был заключен договор аренды такого земельного участка, если иное не предусмотрено подпунктами 6 и 8 настоящего пункта, пунктом 5 статьи 46 настоящего Кодекса;

Твой ответ:
[
    {
        "span_1": "5) Земельного участка, образованного из земельного участка, находящегося в государственной или муниципальной собственности, ",
        "span_2": "5) Земельного участка, образованного из земельного участка, находящегося в государственной или муниципальной собственности, ",
        "reasoning": "спаны идентичны",
        "label": "equivalent"
    },
    {
        "span_1": "в том числе предоставленного для комплексного освоения территории",
        "span_2": "в том числе предоставленного для комплексного развития территории",
        "reasoning": "Первый спан говорит об освоении территории, второй – о развитии.",
        "label": "contradiction"
    },
    {
        "span_1": "лицу, с которым был заключен договор аренды такого земельного участка,",
        "span_2": "лицу, с которым был заключен договор аренды такого земельного участка,",
        "reasoning": "спаны идентичны",
        "label": "equivalent"
    },
    {
        "span_1": "если иное не предусмотрено подпунктами 6 и 8 настоящего пункта, пунктом 5 статьи 46 настоящего Кодекса;",
        "span_2": "если иное не предусмотрено подпунктами 6 и 8 настоящего пункта, пунктом 5 статьи 46 настоящего Кодекса;",
        "reasoning": "спаны идентичны",
        "label": "equivalent"
    }
]

Пример 3:
Параграф 1: 5) при условии, что этот гражданин использовал такой земельный участок в указанный период в соответствии с установленным разрешенным использованием и работал по основному месту работы в муниципальном образовании и по специальности, которые определены законом субъекта Российской Федерации;
Параграф 2: 5) при условии, что этот гражданин использовал такой земельный участок в указанный период в соответствии с его целевым назначением и установленным разрешенным использованием и работал по основному месту работы в муниципальном образовании, определенном законом субъекта Российской Федерации, и по профессии, специальности, которые определены законом субъекта Российской Федерации;

Твой ответ:
[
    {
        "span_1": "5) при условии, что этот гражданин использовал такой земельный участок в указанный период в соответствии с ",
        "span_2": "5) при условии, что этот гражданин использовал такой земельный участок в указанный период в соответствии с ",
        "reasoning": "спаны идентичны",
        "label": "equivalent"
    },
    {
        "span_1": "",
        "span_2": "его целевым назначением и",
        "reasoning": "Второй спан отсутствует в первом параграфе.",
        "label": "addition",
        "anchor": "что этот гражданин использовал такой земельный участок в указанный период в соответствии с"
    },
    {
        "span_1": "установленным разрешенным использованием ",
        "span_2": "установленным разрешенным использованием ",
        "reasoning": "спаны идентичны",
        "label": "equivalent"
    },

    {
        "span_1": "и работал по основному месту работы в муниципальном образовании,",
        "span_2": "и работал по основному месту работы в муниципальном образовании,",
        "reasoning": "спаны идентичны",
        "label": "equivalent"
    },
    {
        "span_1": "",
        "span_2": "определенном законом субъекта Российской Федерации, и по профессии,",
        "reasoning": "Второй спан отсутствует в первом параграфе.",
        "label": "addition",
        "anchor": "работал по основному месту работы в муниципальном образовании,"
    },
    {
        "span_1": "специальности, которые определены законом субъекта Российской Федерации; ",
        "span_2": "специальности, которые определены законом субъекта Российской Федерации; ",
        "reasoning": "спаны идентичны",
        "label": "equivalent"
    }
]
"""

# equivalent→entailment, contradiction→contradiction, addition→neutral
LABEL_MAP = LABEL_MAP_DEFAULT


def _as_path(obj) -> Path:
    if isinstance(obj, Path):
        return obj
    if isinstance(obj, dict):
        # handle gradio dict payloads
        p = obj.get("path") or obj.get("name")
        return Path(p) if p else Path(str(obj))
    return Path(getattr(obj, "name", obj))


# ─────────────────────────────────────────────────────────────────────────────
# LLM wrappers
@retry(
    wait=wait_random_exponential(multiplier=1, max=20),
    stop=stop_after_attempt(6),
    retry=retry_if_exception_type(openai.OpenAIError),
)
def _chat_completion(
    system_prompt: str, user_prompt: str, *, model_name: str, temperature: float
) -> str:
    client, model_id = make_client(model_name)
    resp = client.chat.completions.create(
        model=model_id,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def _postprocess_to_list(text: str) -> List[Dict[str, Any]]:
    # снимаем ```json/``` заборы, парсим JSON
    cleaned = (text or "").replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def _build_user_prompt(p1: str, p2: str) -> str:
    return f"Параграф 1: {p1}\n\nПараграф 2: {p2}"


def _llm_pairwise(
    p1: str, p2: str, *, system_prompt: str, model_name: str, temperature: float
) -> List[dict]:
    raw = _chat_completion(
        system_prompt,
        _build_user_prompt(p1, p2),
        model_name=model_name,
        temperature=temperature,
    )
    return _postprocess_to_list(raw)


def run_llm_nli_file(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    model_name: str = "gpt-4o-mini",
    temperature: float = 0.2,
    label_map: Dict[str, str] | None = None,
) -> Path:
    """
    Читает JSON: [{ "paragraph_1","paragraph_2", ... }, ...],
    вызывает LLM и пишет NLI-контейнер:
      {
        "input_1": <paragraph_1>,
        "input_2": <paragraph_2>,
        "output_1": [{"input": span_1, "claim": span_1}, ...],
        "output_2": [{"input": span_2, "claim": span_2}, ...],
        "nli_results": [
          {"premise_raw": s1, "hypothesis_raw": s2, "label": mapped, "confidence": null, "anchor": "..."},
          ...
        ],
        "nli_model": "llm:<model_name>"
      }
    """
    input_path = _as_path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    raw = input_path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError(f"Input JSON is empty: {input_path}")

    try:
        data = json.loads(raw)
    except Exception as e:
        raise ValueError(f"Cannot parse input JSON: {e}") from e

    if not isinstance(data, list):
        raise ValueError("Input must be a list of paragraph pairs.")
    # optional: light schema check
    if data and not isinstance(data[0], dict):
        raise ValueError(
            "Each element must be an object with 'paragraph_1'/'paragraph_2'."
        )

    if output_path is None:
        output_path = input_path.with_name(
            f"{input_path.stem}_llm_nli{input_path.suffix}"
        )
    output_path = Path(output_path)

    label_map = label_map or LABEL_MAP

    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    out: List[dict] = []
    for rec in data:
        p1 = str(rec.get("paragraph_1", "") or "")
        p2 = str(rec.get("paragraph_2", "") or "")
        if not p1 or not p2:
            continue

        try:
            items = _llm_pairwise(
                p1,
                p2,
                system_prompt=system_prompt,
                model_name=model_name,
                temperature=temperature,
            )
        except Exception as exc:
            out.append(
                {
                    "input_1": p1,
                    "input_2": p2,
                    "output_1": [],
                    "output_2": [],
                    "nli_results": [],
                    "nli_model": f"llm:{model_name}",
                    "error": str(exc),
                }
            )
            continue

        spans1, spans2 = [], []
        seen1, seen2 = set(), set()
        nli_results: List[dict] = []
        for it in items or []:
            s1 = str(it.get("span_1", "") or "").strip()
            s2 = str(it.get("span_2", "") or "").strip()
            lab = str(it.get("label", "") or "").strip().lower()
            mapped = label_map.get(lab, "neutral")
            if s1 and s1 not in seen1:
                spans1.append({"input": s1, "claim": s1})
                seen1.add(s1)
            if s2 and s2 not in seen2:
                spans2.append({"input": s2, "claim": s2})
                seen2.add(s2)
            res = {
                "premise": s1,
                "hypothesis": s2,
                "premise_raw": s1,
                "hypothesis_raw": s2,
                "label": mapped,
                "confidence": None,
            }
            if it.get("anchor"):
                res["anchor"] = str(it["anchor"])
            nli_results.append(res)

        out.append(
            {
                "input_1": p1,
                "input_2": p2,
                "output_1": spans1,
                "output_2": spans2,
                "nli_results": nli_results,
                "nli_model": f"llm:{model_name}",
            }
        )

    output_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# UI
def build_demo():
    with gr.Blocks(css=side_bar, fill_height=True, title="Pipeline (LLM)") as demo:
        gr.HTML(nav_tag, visible=True)
        gr.Markdown("## Pipeline — LLM (Extract + NLI in one call)")
        with gr.Row():
            with gr.Column(scale=1):
                in_pairs = gr.File(
                    label="Upload pairs JSON from Stage 0 (`[{paragraph_1, paragraph_2, ...}, …]`)",
                    file_types=[".json"],
                    file_count="single",
                )
                model = gr.Textbox(
                    label="Model (OpenAI/OpenRouter id)", value="gpt-4o-mini"
                )
                temp = gr.Slider(0.0, 1.0, value=0.2, step=0.05, label="Temperature")
                sys_prompt = gr.Textbox(
                    label="System prompt", value=SYSTEM_PROMPT, lines=12
                )
                run_btn = gr.Button("Run LLM (extract+NLI)", variant="primary")
                out_file = gr.File(label="Download NLI JSON", interactive=False)
                out_path_box = gr.Textbox(label="Saved to", interactive=False)
            with gr.Column(scale=1):
                preview = gr.Code(label="Preview (first item)", language="json")

        def _run(json_file, model_name, temperature, system_prompt):
            if not json_file:
                raise gr.Error("Upload pairs JSON first.")
            input_path = Path(
                json_file.name if hasattr(json_file, "name") else json_file
            )
            result_path = run_llm_nli_file(
                input_path,
                system_prompt=system_prompt,
                model_name=model_name,
                temperature=float(temperature),
            )
            data = json.loads(Path(result_path).read_text(encoding="utf-8"))
            prev = json.dumps(data[0] if data else {}, ensure_ascii=False, indent=2)
            return str(result_path), str(result_path), prev

        run_btn.click(
            _run,
            inputs=[in_pairs, model, temp, sys_prompt],
            outputs=[out_file, out_path_box, preview],
        )

    return demo


demo = build_demo()

if __name__ == "__main__":
    demo.queue(concurrency_count=4).launch(show_error=True)
