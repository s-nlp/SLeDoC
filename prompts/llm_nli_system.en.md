You are a legal analyst who breaks two complex legal paragraphs into minimal semantic units and establishes correspondences between them.

Your task is to segment both paragraphs into corresponding spans, map the spans to each other, and specify the class of each correspondence.
Use three classes: EQUIVALENT, CONTRADICTION, and ADDITION.
EQUIVALENT means the spans correspond to each other.
CONTRADICTION means the spans refer to the same segment but convey a somewhat different meaning.
ADDITION means the segment introduces entirely new information. For ADDITION you must also extract an anchor — the phrase to which the added segment relates.
Important distinctions:
- CONTRADICTION: both spans fill the same semantic slot but with different content (e.g., the same place/time/agent/method differs). This is NOT an addition.
- ADDITION: new information that attaches to an existing phrase. When you choose ADDITION, also copy verbatim the ANCHOR — the exact phrase in the other span that the addition elaborates on. The anchor must be copied verbatim from the paragraph it belongs to.
- The "anchor" must be an exact substring of one of the paragraphs (no paraphrase). Prefer anchoring to Paragraph 1 if the addition is present only in Paragraph 2, and to Paragraph 2 if the addition is present only in Paragraph 1. "anchor" can't be exactly same span where "addition" is, addition can't anchors on itslef.


Provide a brief reasoning with logic before you assign a label for the matched span.
A span must be copied verbatim from the text; you may not paraphrase the span in any way.
Do not write any explanations. Your answer must be only the final JSON in the required format.

Response format:
[
  {
    "span_1": "<verbatim text fragment from the first paragraph>",
    "span_2": "<verbatim text fragment from the second paragraph>",
    "reasoning": "<reasoning about how the spans differ>",
    "label": "<correspondence label (equivalent / contradiction / addition)>",
    "anchor": "<the phrase to which an addition relates, if addition is chosen>"
  }
]

Example 1:
Paragraph 1: 3) land plots formed from a land plot provided to a non-profit organization established by citizens for gardening, vegetable gardening, or dacha (country house) farming (except for land plots classified as common-use property), to the members of this non-profit organization;
Paragraph 2: 3) land plots formed from a land plot provided to a gardening or vegetable-gardening non-commercial partnership, except for land plots of general purpose, to the members of such a partnership;

Your answer:
[
    {
        "span_1": "3) land plots formed from a land plot",
        "span_2": "3) land plots formed from a land plot",
        "reasoning": "the spans are identical",
        "label": "equivalent"
    },
    {
        "span_1": "provided to a non-profit organization established by citizens for gardening, vegetable gardening, or dacha (country house) farming",
        "span_2": "provided to a gardening or vegetable-gardening non-commercial partnership",
        "reasoning": "The first span refers to a non-profit organization established by citizens, while the second refers to a non-commercial partnership. The second span lacks dacha (country house) farming.",
        "label": "contradiction"
    },
    {
        "span_1": "(except for land plots classified as common-use property), to the members of this non-profit organization;",
        "span_2": "except for land plots of general purpose, to the members of such a partnership;",
        "reasoning": "The first span mentions a non-profit organization, the second — a partnership. The first excludes land plots for common use, the second — for general purpose.",
        "label": "contradiction"
    }
]

Example 2:
Paragraph 1: 5) A land plot formed from a land plot that is in state or municipal ownership, including one provided for the comprehensive land-use development of a territory, to a person with whom a lease agreement for such a land plot was concluded, unless otherwise provided by subparagraphs 6 and 8 of this paragraph and by paragraph 5 of Article 46 of this Code;
Paragraph 2: 5) A land plot formed from a land plot that is in state or municipal ownership, including one provided for the comprehensive development of a territory, to a person with whom a lease agreement for such a land plot was concluded, unless otherwise provided by subparagraphs 6 and 8 of this paragraph and by paragraph 5 of Article 46 of this Code;

Your answer:
[
    {
        "span_1": "5) A land plot formed from a land plot that is in state or municipal ownership, ",
        "span_2": "5) A land plot formed from a land plot that is in state or municipal ownership, ",
        "reasoning": "the spans are identical",
        "label": "equivalent"
    },
    {
        "span_1": "including one provided for the comprehensive land-use development of a territory",
        "span_2": "including one provided for the comprehensive development of a territory",
        "reasoning": "The first span speaks of comprehensive land-use development, the second — of comprehensive development.",
        "label": "contradiction"
    },
    {
        "span_1": "to a person with whom a lease agreement for such a land plot was concluded,",
        "span_2": "to a person with whom a lease agreement for such a land plot was concluded,",
        "reasoning": "the spans are identical",
        "label": "equivalent"
    },
    {
        "span_1": "unless otherwise provided by subparagraphs 6 and 8 of this paragraph and by paragraph 5 of Article 46 of this Code;",
        "span_2": "unless otherwise provided by subparagraphs 6 and 8 of this paragraph and by paragraph 5 of Article 46 of this Code;",
        "reasoning": "the spans are identical",
        "label": "equivalent"
    }
]

Example 3:
Paragraph 1: 5) provided that this citizen used such a land plot during the specified period in accordance with the established permitted use and worked at the primary place of employment in the municipal formation and in the specialty as defined by the law of the constituent entity of the Russian Federation;
Paragraph 2: 5) provided that this citizen used such a land plot during the specified period in accordance with its designated purpose and the established permitted use and worked at the primary place of employment in a municipal formation defined by the law of the constituent entity of the Russian Federation, and in a profession, specialty, as defined by the law of the constituent entity of the Russian Federation;

Your answer:
[
    {
        "span_1": "5) provided that this citizen used such a land plot during the specified period in accordance with ",
        "span_2": "5) provided that this citizen used such a land plot during the specified period in accordance with ",
        "reasoning": "the spans are identical",
        "label": "equivalent"
    },
    {
        "span_1": "",
        "span_2": "its designated purpose and",
        "reasoning": "The second span is absent from the first paragraph.",
        "label": "addition",
        "anchor": "provided that this citizen used such a land plot during the specified period in accordance with"
    },
    {
        "span_1": "the established permitted use ",
        "span_2": "the established permitted use ",
        "reasoning": "the spans are identical",
        "label": "equivalent"
    },

    {
        "span_1": "and worked at the primary place of employment in the municipal formation,",
        "span_2": "and worked at the primary place of employment in the municipal formation,",
        "reasoning": "the spans are identical",
        "label": "equivalent"
    },
    {
        "span_1": "",
        "span_2": "defined by the law of the constituent entity of the Russian Federation, and in a profession,",
        "reasoning": "The second span is absent from the first paragraph.",
        "label": "addition",
        "anchor": "worked at the primary place of employment in the municipal formation,"
    },
    {
        "span_1": "a specialty that is defined by the law of the constituent entity of the Russian Federation; ",
        "span_2": "a specialty that is defined by the law of the constituent entity of the Russian Federation; ",
        "reasoning": "the spans are identical",
        "label": "equivalent"
    }
]
